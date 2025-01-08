import csv
import os
import subprocess
import sys
import threading
import time
import logging
from threading import Event

logging.basicConfig(level=logging.INFO)

# get current directory
WORK_DIR = os.getcwd()
print("Working directory:", WORK_DIR)

# Prometheus server URL
PROMETHEUS_URL = "http://132.227.122.122:31894"
# SAVE_FILE_PATH_DATA = f"{WORK_DIR}/data/pc-time-containers.json"


# Constants for Helm chart paths
CORE_CHART_PATH = os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-core/oai-5g-basic")
FLEXRIC_CHART_PATH =  os.path.expanduser("~/bp-flexric/oai-flexric")
CU_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-cu")
CU2_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-cu2")
DU_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-du")
UE_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-nr-ue")
DU2_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-du2")
UE2_CHART_PATH =  os.path.expanduser("~/oai-cn5g-fed/charts/oai-5g-ran/oai-nr-ue2")

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
        # sys.exit(1)

# Function to check pod readiness
def wait_for_pods(namespace):
    print(f"Waiting for all pods in {namespace} to be ready...")
    run_command(["kubectl", "wait", "--for=condition=Ready", "--all","pods", "-n", namespace, "--timeout=180s"])

def deploy_bp3_with_second_du_and_ue(cpu_mi=None, memory_mi='2Gi', tcpdump=False, log_file_path=None):
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
            f"resources.requests.nf.cpu={cpu_mi}m",
        ]
        run_command(["helm", "install", "oai-cu", CU_CHART_PATH, "-n", RAN_NAMESPACE, "--set", ",".join(resource_set_flags)])
    else:
        run_command(["helm", "install", "oai-cu", CU_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)

    # Install the first DU and UE
    time.sleep(3)
    run_command(["helm", "install", "oai-du", DU_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)
    # time.sleep(2)
    run_command(["helm", "install", "oai-nr-ue", UE_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)
    time.sleep(5) # ensure connectivity between du and ue is already established


    # Install the second DU and UE
    # Capture the start time
    start_time = time.time()
    start_timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))

    # Install oai-cu2
    run_command(["helm", "install", "oai-cu2", CU2_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)

    # Install oai-du2
    run_command(["helm", "install", "oai-du2", DU2_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)

    # Install oai-nr-ue2
    run_command(["helm", "install", "oai-nr-ue2", UE2_CHART_PATH, "-n", RAN_NAMESPACE])
    wait_for_pods(RAN_NAMESPACE)

    # Capture the end time
    end_time = time.time()
    end_timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))

    # Calculate the total duration
    # Calculate the total duration
    duration_seconds = end_time - start_time

    # Write to the CSV file
    with open(log_file_path, mode='a', newline='') as file:
        writer = csv.writer(file)

        # Check if file is empty, if so, write the header
        file.seek(0, 2)  # Move to the end of the file to check if it’s empty
        if file.tell() == 0:
            writer.writerow(["Start Timestamp", "End Timestamp", "Duration"])

        # Write the data
        writer.writerow([start_timestamp, end_timestamp, duration_seconds])
    

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
    tcpdump = False

    print("\n------------------------------NEW EXPERIMENT------------------------------")
    experiment_dir = f"2CU_deployment_time_{index}/"
    os.makedirs(experiment_dir, exist_ok=True)
    LOG_DEPLOY_CU2 = os.path.join(experiment_dir, "log_deploy_cu2.csv")
    deployment_succeeded = False
    while not deployment_succeeded:
        deploy_bp3_with_second_du_and_ue(tcpdump=tcpdump, log_file_path=LOG_DEPLOY_CU2)

    return True



if __name__ == "__main__":
    for i in range(3, 10):
        finished = False
        while not finished:
            finished = run_experiments_with_multiple_ues(index=i)

    print("All the experiments are done. Hurray.")
    # Force a successful exit
    sys.exit(0)
