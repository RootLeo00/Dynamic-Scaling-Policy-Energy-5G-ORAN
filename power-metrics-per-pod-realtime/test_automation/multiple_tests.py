import os
import subprocess
import threading
import time
from utils import collect_metrics, load_uid_pod_map, plot_metrics, run_iperf, get_pod_info, get_all_pod_names, create_uid_pod_mapping,check_ping
import logging

logging.basicConfig(level=logging.INFO)

# get current directory
WORK_DIR = os.getcwd()
print("Working directory:", WORK_DIR)

# Prometheus server URL
PROMETHEUS_URL = "http://192.168.122.115:32181"
# Prometheus query to fetch the metric in watts if greater than 0.01
QUERY = 'scaph_process_power_consumption_microwatts{container_scheduler="docker"} / 1000000 > 0.001'
# SAVE_FILE_PATH_DATA = f"{WORK_DIR}/data/pc-time-containers.json"
POD_DATA=f"{WORK_DIR}/data/all_pod_metrics.json"
UID_POD_MAPPING_PATH=f"{WORK_DIR}/data/uid_pod_mapping.csv"


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
def deploy_bp3(cpu_mi="500m",memory_mi='2Gi'):
    print(f"Redeploying pods with CPU resources set to {cpu_mi}m...")

    resource_set_flags = [
        f"resources.define=true",
        f"resources.limits.nf.cpu={cpu_mi}m",
        f"resources.limits.nf.memory={memory_mi}",
        f"resources.limits.tcpdump.cpu={cpu_mi}m",
        f"resources.limits.tcpdump.memory=128Mi",
        f"resources.requests.nf.cpu={cpu_mi}m",
        f"resources.requests.nf.memory={memory_mi}",
        f"resources.requests.tcpdump.cpu={cpu_mi}m",
        f"resources.requests.tcpdump.memory=128Mi",
    ]
    
    # Uninstall all Helm releases in core and ran namespaces
    uninstall_all_releases("core")
    uninstall_all_releases("ran")

    run_command(["helm", "install", "oai-5g-core", CORE_CHART_PATH, "-n", CORE_NAMESPACE])
    wait_for_pods(CORE_NAMESPACE)

    # Install remaining charts
    run_command(["helm", "install", "oai-flexric", FLEXRIC_CHART_PATH, "-n", CORE_NAMESPACE])
    wait_for_pods(CORE_NAMESPACE)

    run_command(["helm", "install", "oai-cu", CU_CHART_PATH, "-n", RAN_NAMESPACE, "--set", ",".join(resource_set_flags)])
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

def run_experiments():
    cpu_resources = [75,125,150,175,200]  # CPU in m
    packet_lengths = [700, 1300]
    mb_values = [40, 70]
    duration = 60  # seconds


    for cpu in cpu_resources:
        print("\n------------------------------NEW EXPERIMENT------------------------------")
        oai_upf_pod=""
        oai_nr_ue_pod=""
        deployment_succeded=False
        while not deployment_succeded:
            deploy_bp3(cpu)
            install_iperf_on_upf()

            # Get real pod names
            oai_upf_pod, _ = get_pod_info("oai-upf")
            oai_nr_ue_pod, _ = get_pod_info("oai-nr-ue")

            deployment_succeded=check_ping(oai_nr_ue_pod, RAN_NAMESPACE, "12.1.1.100")

        for packet_length in packet_lengths:
            for mb in mb_values:
                description = f"{cpu}mi_at_cu"
                experiment_dir = f"data/{mb}_{duration}_{packet_length}_{description}"
                os.makedirs(experiment_dir, exist_ok=True)

                # Run experiment
                try:
                    SAVE_FILE_PATH_DATA_ENERGY = os.path.join(experiment_dir, "metrics_energy.json")
                    SAVE_FILE_PATH_PLOT_ENERGY = os.path.join(experiment_dir, "metrics_energy.png")
                    SAVE_FILE_PATH_DATA_CPU = os.path.join(experiment_dir, "metrics_cpu.json")
                    
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
                        args=(duration, SAVE_FILE_PATH_DATA_ENERGY, PROMETHEUS_URL, "energy")
                    )
                    metrics_cpu_thread = threading.Thread(
                        target=collect_metrics,
                        args=(duration, SAVE_FILE_PATH_DATA_CPU, PROMETHEUS_URL, "cpu")
                    )
                    

                    # Start threads
                    iperf_thread_server.start()
                    iperf_thread_client.start()
                    metrics_energy_thread.start()
                    metrics_cpu_thread.start()

                    # Wait for the experiment duration
                    time.sleep(duration)

                    # Wait for threads to finish
                    iperf_thread_client.join()
                    iperf_thread_server.join()
                    metrics_energy_thread.join()
                    metrics_cpu_thread.join()

                except Exception as e:
                    print(f"Experiment failed: {e}")

                # Load UID to pod mapping
                get_all_pod_names(POD_DATA)
                create_uid_pod_mapping(UID_POD_MAPPING_PATH, POD_DATA)
                uid_pod_map = load_uid_pod_map(UID_POD_MAPPING_PATH)

                # Plot results for energy
                plot_metrics(SAVE_FILE_PATH_DATA_ENERGY, SAVE_FILE_PATH_PLOT_ENERGY, uid_pod_map)
                
    return True

if __name__ == "__main__":
    finished=False
    while not finished:
        finished=run_experiments()

    print("All the experiments are done. Hurray.")
