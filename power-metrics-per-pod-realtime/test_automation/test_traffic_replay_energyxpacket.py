import os
import subprocess
import threading
import time
import csv
from utils import collect_metrics, load_uid_pod_map, plot_metrics, run_iperf, get_pod_info, get_all_pod_names, create_uid_pod_mapping, check_ping, download_tcpdump
import logging

logging.basicConfig(level=logging.INFO)

# Constants and paths
WORK_DIR = os.getcwd()
PROMETHEUS_URL = "http://192.168.122.115:32181"
CORE_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-core/oai-5g-basic")
FLEXRIC_CHART_PATH = os.path.expanduser("~/bp-flexric/oai-flexric")
CU_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-cu")
DU_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-du")
UE_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-nr-ue")
CORE_NAMESPACE = "core"
RAN_NAMESPACE = "ran"
MBPS_FILE_PATH = "/home/ubuntu/power-consumption-tool/power-metrics-per-pod-realtime/dataset/testing_dat_1.csv"

def run_command(command):
    try:
        print(f"Running: {' '.join(command)}")
        subprocess.run(command, check=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")

def wait_for_pods(namespace):
    print(f"Waiting for all pods in {namespace} to be ready...")
    run_command(["kubectl", "wait", "--for=condition=Ready", "--all", "pods", "-n", namespace, "--timeout=180s"])

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
    run_command(["kubectl", "exec", upf_pod, "-n", CORE_NAMESPACE, "--", "apt", "install", "-y", "iputils-ping", "iperf"])

def uninstall_all_releases(namespace):
    try:
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

def load_mbps_from_file(file_path):
    mbps_values = []
    with open(file_path, mode="r") as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            try:
                mbps = round(float(row[0]))  # Round to the nearest integer
                mbps_values.append(mbps)
            except ValueError:
                print(f"Skipping invalid value: {row[0]}")
    return mbps_values

def run_experiments(index):
    packet_length = 700
    duration_baseline = 100
    tcpdump = False
    mbps_values = load_mbps_from_file(MBPS_FILE_PATH)

    print("\n------------------------------NEW EXPERIMENT------------------------------")
    oai_upf_pod = ""
    oai_nr_ue_pod = ""
    deployment_succeeded = False
    while not deployment_succeeded:
        deploy_bp3(tcpdump=tcpdump)
        install_iperf_on_upf()

        oai_upf_pod, _ = get_pod_info("oai-upf")
        oai_nr_ue_pod, _ = get_pod_info("oai-nr-ue")
        oai_cu, oai_cu_namespace = get_pod_info("oai-cu")

        deployment_succeeded = check_ping(oai_nr_ue_pod, RAN_NAMESPACE, "12.1.1.100")

    experiment_dir = f"experiment_packet_energy_{index}"
    os.makedirs(experiment_dir, exist_ok=True)

    try:
        SAVE_FILE_PATH_DATA_ENERGY = os.path.join(experiment_dir, "metrics_energy.json")
        SAVE_FILE_PATH_PLOT_ENERGY = os.path.join(experiment_dir, "metrics_energy.png")
        UID_POD_MAPPING_PATH = os.path.join(experiment_dir, "uid_pod_mapping.csv")
        POD_DATA = os.path.join(experiment_dir, "all_pod_metrics.json")

        metrics_energy_thread = threading.Thread(
            target=collect_metrics,
            args=(duration_baseline + len(mbps_values) * 3, SAVE_FILE_PATH_DATA_ENERGY, PROMETHEUS_URL, "energy", None)
        )

        metrics_energy_thread.start()
        time.sleep(duration_baseline)

        for i, mbps in enumerate(mbps_values):
            print(f"Running iperf with {mbps} Mbps...")
            run_iperf(oai_upf_pod, CORE_NAMESPACE, "client", experiment_dir, 3, "12.1.1.100", mbps, packet_length)
            time.sleep(3)  # Wait for the next 3-second interval

        metrics_energy_thread.join()

    except Exception as e:
        print(f"Experiment failed: {e}")

    get_all_pod_names(POD_DATA)
    create_uid_pod_mapping(UID_POD_MAPPING_PATH, POD_DATA)
    uid_pod_map = load_uid_pod_map(UID_POD_MAPPING_PATH)

    if tcpdump:
        download_tcpdump(pod=oai_cu, namespace=oai_cu_namespace, download_to_dir=experiment_dir)

    plot_metrics(SAVE_FILE_PATH_DATA_ENERGY, SAVE_FILE_PATH_PLOT_ENERGY, uid_pod_map)
    return True

if __name__ == "__main__":
    for i in range(21, 22):
        finished = False
        while not finished:
            finished = run_experiments(index=i)

    print("All the experiments are done. Hurray.")
