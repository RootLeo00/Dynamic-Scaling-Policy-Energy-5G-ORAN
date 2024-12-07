import os
import subprocess
import threading
import time
from utils import collect_metrics, load_uid_pod_map, plot_metrics, run_iperf, get_pod_info, get_all_pod_names, create_uid_pod_mapping,check_ping,download_tcpdump
import logging

logging.basicConfig(level=logging.INFO)

# get current directory
WORK_DIR = os.getcwd()
print("Working directory:", WORK_DIR)

# Prometheus server URL
PROMETHEUS_URL = "http://192.168.122.115:32181"
# SAVE_FILE_PATH_DATA = f"{WORK_DIR}/data/pc-time-containers.json"


# Constants for Helm chart paths
CORE_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-core/oai-5g-basic")
FLEXRIC_CHART_PATH =  os.path.expanduser("~/bp-flexric/oai-flexric")
CU_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-cu")
DU_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-du")
UE_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-nr-ue")

# Namespace constants
CORE_NAMESPACE = "core"
RAN_NAMESPACE = "ran"

# Function to run shell commands
def run_command(command):
    try:
        print(f"Running: {' '.join(command)}")
        subprocess.run(command, check=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")

# Function to check pod readiness
def wait_for_pods(namespace):
    print(f"Waiting for all pods in {namespace} to be ready...")
    run_command(["kubectl", "wait", "--for=condition=Ready", "--all","pods", "-n", namespace, "--timeout=180s"])

# Helm uninstall and redeploy with updated resources
def deploy_bp3(cpu_mi=None,memory_mi='2Gi', tcpdump=False):
    print(f"Redeploying pods with CPU resources set to {cpu_mi}m...")

    # Uninstall all Helm releases in core and ran namespaces
    uninstall_all_releases("core")
    uninstall_all_releases("ran")

    run_command(["helm", "install", "oai-5g-core", CORE_CHART_PATH, "-n", CORE_NAMESPACE])
    wait_for_pods(CORE_NAMESPACE)

    # Install remaining charts
    run_command(["helm", "install", "oai-flexric", FLEXRIC_CHART_PATH, "-n", CORE_NAMESPACE])
    wait_for_pods(CORE_NAMESPACE)

    if cpu_mi:
        resource_set_flags = [
            f"start.tcpdump={tcpdump}",
            f"includeTcpDumpContainer={tcpdump}",
            f"resources.define=true",
            f"resources.limits.nf.cpu={cpu_mi}m",
            f"resources.limits.nf.memory={memory_mi}",
            # f"resources.limits.tcpdump.cpu={cpu_mi}m",
            # f"resources.limits.tcpdump.memory=128Mi",
            f"resources.requests.nf.cpu={cpu_mi}m",
            f"resources.requests.nf.memory={memory_mi}",
            # f"resources.requests.tcpdump.cpu={cpu_mi}m",
            # f"resources.requests.tcpdump.memory=128Mi",
        ]
        run_command(["helm", "install", "oai-cu", CU_CHART_PATH, "-n", RAN_NAMESPACE, "--set", ",".join(resource_set_flags)])
    else:
        run_command(["helm", "install", "oai-cu", CU_CHART_PATH, "-n", RAN_NAMESPACE])
    run_command(["helm", "install", "oai-du", DU_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)
    time.sleep(5)
    run_command(["helm", "install", "oai-nr-ue", UE_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)

# Install iperf on the oai-upf pod
def install_iperf_on_upf():
    print("Installing iperf on oai-upf...")
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", CORE_NAMESPACE],
        capture_output=True,
        text=True,
        check=True
    )
    for line in result.stdout.splitlines():
        if "oai-upf" in line:
            upf_pod = line.split()[0]
            break
    else:
        raise Exception("oai-upf pod not found.")

    run_command(["kubectl", "exec", upf_pod, "-n", CORE_NAMESPACE, "--", "apt", "update"])
    run_command(["kubectl", "exec", upf_pod, "-n", CORE_NAMESPACE, "--", "apt", "install", "-y", "iputils-ping"])
    run_command(["kubectl", "exec", upf_pod, "-n", CORE_NAMESPACE, "--", "apt", "install", "-y", "iperf"])


def uninstall_all_releases(namespace):
    try:
        # List all releases in the namespace
        result = subprocess.run(
            ["helm", "list", "-n", namespace, "-q"],
            capture_output=True,
            text=True,
            check=True
        )
        releases = result.stdout.strip().splitlines()
        for release in releases:
            print(f"Uninstalling release: {release}")
            subprocess.run(["helm", "uninstall", release, "-n", namespace], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to uninstall releases in {namespace}: {e}")

def run_experiments(index): 
    packet_lengths = [300]
    mb_values = [10,20,30,40,50,60] 
    duration = 100  # seconds
    duration_baseline=100
    tcpdump=False

    print("\n------------------------------NEW EXPERIMENT------------------------------")
    oai_upf_pod=""
    oai_nr_ue_pod=""
    deployment_succeded=False
    while not deployment_succeded:
        deploy_bp3( tcpdump=tcpdump)
        install_iperf_on_upf()

        # Get real pod names
        oai_upf_pod, _ = get_pod_info("oai-upf")
        oai_nr_ue_pod, _ = get_pod_info("oai-nr-ue")
        oai_cu,oai_cu_namespace=get_pod_info("oai-cu")

        deployment_succeded=check_ping(oai_nr_ue_pod, RAN_NAMESPACE, "12.1.1.100")

    for packet_length in packet_lengths:
        for mb in mb_values:
            experiment_dir = f"experiment_packet_energy_{index}/{mb}_{duration}_{packet_length}"

            # Check if the directory exists
            if os.path.exists(experiment_dir):
                # Delete all files and subdirectories inside the folder (without deleting the folder itself)
                for filename in os.listdir(experiment_dir):
                    file_path = os.path.join(experiment_dir, filename)
                    try:
                        os.remove(file_path)  # Remove file
                    except Exception as e:
                        print(f"Failed to delete {file_path}. Reason: {e}")
            os.makedirs(experiment_dir, exist_ok=True)

            # Run experiment
            try:
                SAVE_FILE_PATH_DATA_ENERGY = os.path.join(experiment_dir, "metrics_energy.json")
                SAVE_FILE_PATH_DATA_HOST_ENERGY = os.path.join(experiment_dir, "metrics_host_energy.json")
                SAVE_FILE_PATH_PLOT_ENERGY = os.path.join(experiment_dir, "metrics_energy.png")
                SAVE_FILE_PATH_DATA_CPU = os.path.join(experiment_dir, "metrics_cpu.json")
                UID_POD_MAPPING_PATH=os.path.join(experiment_dir, "uid_pod_mapping.csv")
                POD_DATA=os.path.join(experiment_dir, "all_pod_metrics.json")
                
                iperf_thread_server = threading.Thread(
                    target=run_iperf,
                    args=(oai_nr_ue_pod, RAN_NAMESPACE, "server", experiment_dir, duration)
                )
                iperf_thread_client = threading.Thread(
                    target=run_iperf,
                    args=(oai_upf_pod, CORE_NAMESPACE, "client", experiment_dir, duration, "12.1.1.100", mb, packet_length)
                )
                metrics_energy_thread = threading.Thread(
                    target=collect_metrics,
                    args=(duration_baseline+duration, SAVE_FILE_PATH_DATA_ENERGY, PROMETHEUS_URL, "energy", None)
                )
                metrics_host_energy_thread = threading.Thread(
                    target=collect_metrics,
                    args=(duration_baseline+duration, SAVE_FILE_PATH_DATA_HOST_ENERGY, PROMETHEUS_URL, "host_energy", None)
                )

                metrics_energy_thread.start()
                metrics_host_energy_thread.start()

                # wait to get baseline energy
                time.sleep(duration_baseline)

                # Start threads
                iperf_thread_server.start()
                iperf_thread_client.start()
                # wait for 20s (for prometheus lag)
                time.sleep(duration)
                collect_metrics(duration-20, SAVE_FILE_PATH_DATA_CPU, PROMETHEUS_URL, "cpu", oai_cu) # remove the 20 seconds of lag

                # Wait for threads to finish
                metrics_energy_thread.join() #blocking
                metrics_host_energy_thread.join() #blocking
                iperf_thread_client.join() #blocking
                iperf_thread_server.join() #blocking

            except Exception as e:
                print(f"Experiment failed: {e}")

            # Load UID to pod mapping
            get_all_pod_names(POD_DATA)
            create_uid_pod_mapping(UID_POD_MAPPING_PATH, POD_DATA)
            uid_pod_map = load_uid_pod_map(UID_POD_MAPPING_PATH)

            if tcpdump:
                download_tcpdump(pod=oai_cu,namespace=oai_cu_namespace, download_to_dir=experiment_dir)

            # Plot results for energy
            plot_metrics(SAVE_FILE_PATH_DATA_ENERGY, SAVE_FILE_PATH_PLOT_ENERGY, uid_pod_map)
            
    return True

if __name__ == "__main__":
    for i in range(25,30):
        finished=False
        while not finished:
            finished=run_experiments(index=i)

    print("All the experiments are done. Hurray.")
