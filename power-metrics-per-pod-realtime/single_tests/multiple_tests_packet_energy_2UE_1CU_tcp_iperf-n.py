import os
import subprocess
import sys
import threading
import time
from utils import collect_metrics_with_stop_event, load_uid_pod_map, plot_metrics, run_iperf_tcp_number_packets, get_pod_info, get_all_pod_names, create_uid_pod_mapping, check_ping, download_tcpdump
import logging
from threading import Event

logging.basicConfig(level=logging.INFO)

# Get current directory
WORK_DIR = os.getcwd()
print("Working directory:", WORK_DIR)

# Prometheus server URL
PROMETHEUS_URL = "http://132.227.122.122:31894"

# Constants for Helm chart paths
CORE_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-core/oai-5g-basic")
FLEXRIC_CHART_PATH = os.path.expanduser("~/bp-flexric/oai-flexric")
CU_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-cu")
DU_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-du")
UE_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-nr-ue")
DU2_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-du2")
DU3_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-du3")
UE2_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-nr-ue2")
UE3_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-nr-ue3")

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
    run_command(["kubectl", "wait", "--for=condition=Ready", "--all", "pods", "-n", namespace, "--timeout=180s"])
def deploy_bp3_with_second_du_and_ue(cpu_mi=None, memory_mi='2Gi', tcpdump=False):
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
            # f"resources.limits.nf.memory={memory_mi}",
            f"resources.requests.nf.cpu={cpu_mi}m",
            # f"resources.requests.nf.memory={memory_mi}",
        ]
        run_command(["helm", "install", "oai-cu", CU_CHART_PATH, "-n", RAN_NAMESPACE, "--set", ",".join(resource_set_flags)])
    else:
        run_command(["helm", "install", "oai-cu", CU_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)

    # Install the first DU and UE
    # from https://gitlab.eurecom.fr/oai/openairinterface5g/-/blob/ffc3799476fc402a7e2ac363ba307e3664df697f/doc/handover-tutorial.md
    # It is important that you start DU0, UE, DU1 in order, and having UE connect to DU0 before starting DU1.
    run_command(["helm", "install", "oai-du", DU_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)
    run_command(["helm", "install", "oai-nr-ue", UE_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)
    time.sleep(5) # ensure connectivity between du and ue is already established

    # Install the second DU and UE
    resource_set_flags_du = [
        f"config.cuHost=oai-cu.ran.svc.cluster.local",  # Set cuHost for DU dynamically
    ]

    run_command(["helm", "install", "oai-du2", DU2_CHART_PATH, "-n", RAN_NAMESPACE,"--set", ",".join(resource_set_flags_du)])
    wait_for_pods(RAN_NAMESPACE)
    run_command(["helm", "install", "oai-nr-ue2", UE2_CHART_PATH, "-n", RAN_NAMESPACE,])
    wait_for_pods(RAN_NAMESPACE)
    # time.sleep(5)

    # run_command(["helm", "install", "oai-du3", DU3_CHART_PATH, "-n", RAN_NAMESPACE,"--set", ",".join(resource_set_flags_du)])
    # wait_for_pods(RAN_NAMESPACE)
    # run_command(["helm", "install", "oai-nr-ue3", UE3_CHART_PATH, "-n", RAN_NAMESPACE,])
    # wait_for_pods(RAN_NAMESPACE)
    

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

def apply_tc_rule_to_cu(max_rate=None):
    print("Applying tc rule to CU pod...")
    try:
        # Get the CU pod name
        cu_pod, _ = get_pod_info("oai-cu")
        
        # Apply the tc command
        run_command([
            "kubectl", "exec", cu_pod, "-n", RAN_NAMESPACE, "--", 
            "tc", "qdisc", "add", "dev", "eth0", "root", "tbf", 
            "rate", f"{max_rate}mbit", "burst", "50kbit", "latency", "100ms"
        ])
        print("tc rule successfully applied to CU pod.")
    except Exception as e:
        print(f"Failed to apply tc rule to CU pod: {e}")



class StoppableThread(threading.Thread):
    """
    A thread class that stops gracefully using a stop event.
    """
    def __init__(self, *args, stop_event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_event = stop_event or Event()

    def run(self):
        if hasattr(self, "_target") and self._target:
            try:
                self._target(*self._args, **self._kwargs)
            except Exception as e:
                print(f"Exception in thread {self.name}: {e}")
            finally:
                self.stop_event.set()

                
def run_experiments_with_multiple_ues(index):
    packet_lengths = [500]
    ue1_mb_values = [10,50,150,250,500,1000]#range(100,400,100)# [10,50,100,200]#[10,30,50,70,90,110,130,]#[10,30,50,100,200]
    ue2_mb_values = [10,50,150,250,500,1000]#range(100,400,100)# [10,50,100,200]#[10,30,50,70,90,110,130,]#[10,20,50,100,200]

    duration_baseline = 25
    tcpdump = False

    for packet_length in packet_lengths:
        for ue1_mb, ue2_mb in zip(ue1_mb_values, ue2_mb_values):
            print("\n------------------------------NEW EXPERIMENT------------------------------")
            deployment_succeeded = False
            while not deployment_succeeded:
                deploy_bp3_with_second_du_and_ue(tcpdump=tcpdump)
                install_iperf_on_upf()

                oai_nr_ue1_pod, _ = get_pod_info("oai-nr-ue")
                oai_nr_ue2_pod, _ = get_pod_info("oai-nr-ue2")
                oai_upf_pod, _ = get_pod_info("oai-upf")
                deployment_succeeded = (
                    check_ping(oai_nr_ue1_pod, RAN_NAMESPACE, "12.1.1.100") and
                    check_ping(oai_nr_ue2_pod, RAN_NAMESPACE, "12.1.1.101")
                )

            apply_tc_rule_to_cu(max_rate=50)

            total_mb = ue1_mb + ue2_mb
            experiment_dir = f"experiment_packet_energy_2UE_1CU_iperf-n_{index}/{total_mb}_{packet_length}"
            os.makedirs(experiment_dir, exist_ok=True)

            try:
                SAVE_FILE_PATH_DATA_ENERGY = os.path.join(experiment_dir, "metrics_energy.json")
                SAVE_FILE_PATH_PLOT_ENERGY = os.path.join(experiment_dir, "metrics_energy.png")
                UID_POD_MAPPING_PATH = os.path.join(experiment_dir, "uid_pod_mapping.csv")
                POD_DATA = os.path.join(experiment_dir, "all_pod_metrics.json")

                # Start metrics collection
                stop_event = Event()
                metrics_energy_thread = StoppableThread(
                    target=collect_metrics_with_stop_event,
                    args=(SAVE_FILE_PATH_DATA_ENERGY, PROMETHEUS_URL, "energy", None, stop_event),
                    stop_event=stop_event
                )

                # Start iPerf sessions
                iperf_thread_ue1 = threading.Thread(
                    target=run_iperf_tcp_number_packets,
                    args=(oai_nr_ue1_pod, RAN_NAMESPACE, "server", experiment_dir, "12.1.1.100", ue1_mb, packet_length),
                )
                iperf_thread_ue2 = threading.Thread(
                    target=run_iperf_tcp_number_packets,
                    args=(oai_nr_ue2_pod, RAN_NAMESPACE, "server", experiment_dir, "12.1.1.101", ue2_mb, packet_length),
                )
                iperf_thread_upf = threading.Thread(
                    target=run_iperf_tcp_number_packets,
                    args=(oai_upf_pod, CORE_NAMESPACE, "client", experiment_dir, "12.1.1.100", ue1_mb, packet_length),
                )
                iperf_thread_upf_ue2 = threading.Thread(
                    target=run_iperf_tcp_number_packets,
                    args=(oai_upf_pod, CORE_NAMESPACE, "client", experiment_dir, "12.1.1.101", ue2_mb, packet_length),
                )

                print("Start baseline collection")
                metrics_energy_thread.start()
                time.sleep(duration_baseline)  # Baseline collection time
                # Start threads
                iperf_thread_ue1.start()
                iperf_thread_ue2.start()
                time.sleep(5)
                iperf_thread_upf.start()
                iperf_thread_upf_ue2.start()

                # Stop metrics collection
                # Join threads
                iperf_thread_ue1.join()
                iperf_thread_ue2.join()
                iperf_thread_upf_ue2.join()
                iperf_thread_upf.join()
                
                print("Sleep to get last 10 seconds metrics")
                time.sleep(15)
                stop_event.set()
                metrics_energy_thread.join()

            except Exception as e:
                print(f"Experiment failed: {e}")
                stop_event.set()  # Ensure all threads are signaled to stop

            # Map pod metrics and plot results
            get_all_pod_names(POD_DATA)
            create_uid_pod_mapping(UID_POD_MAPPING_PATH, POD_DATA)
            uid_pod_map = load_uid_pod_map(UID_POD_MAPPING_PATH)

            if tcpdump:
                download_tcpdump(pod="oai-cu", namespace="ran", download_to_dir=experiment_dir)

            plot_metrics(SAVE_FILE_PATH_DATA_ENERGY, SAVE_FILE_PATH_PLOT_ENERGY, uid_pod_map)

    return True

if __name__ == "__main__":
    for i in range(1, 10):
        finished = False
        while not finished:
            finished = run_experiments_with_multiple_ues(index=i)

    print("All the experiments are done. Hurray.")
    # Force a successful exit
    sys.exit(0)