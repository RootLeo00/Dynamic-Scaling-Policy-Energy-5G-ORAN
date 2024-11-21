import requests
import json
import matplotlib.pyplot as plt
import pandas as pd
import time
import os
import subprocess
import threading
import matplotlib.pyplot as plt
import json
import matplotlib.ticker as ticker

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

if __name__ == "__main__":
    # Experiment parameters
    mb = 70
    duration = 60
    packet_length = 1300
    description = "100mi_at_cu"  # Add any unique description here

    # Generate directory name
    EXPERIMENT_DIR = os.path.join(WORK_DIR, "data", generate_experiment_dir(mb, duration, packet_length, description))
    os.makedirs(EXPERIMENT_DIR, exist_ok=True)

    SAVE_FILE_PATH_DATA = os.path.join(EXPERIMENT_DIR, "pc-time-containers.json")
    SAVE_FILE_PATH_PLOT = os.path.join(EXPERIMENT_DIR, "pc-time-containers.png")

    # Fetch pod info and set up iperf server
    search_term = "oai-nr-ue"
    pod_name, namespace = get_pod_info(search_term)
    mode = 'server'
    print("Run iperf server: ", pod_name, namespace, mode)
    iperf_thread_server = threading.Thread(target=run_iperf, args=(pod_name, namespace, mode, EXPERIMENT_DIR, duration))

    # Fetch pod info and set up iperf client
    search_term = "oai-upf"
    pod_name, namespace = get_pod_info(search_term)
    mode = 'client'
    ip_address = '12.1.1.100'
    print("Run iperf client: ", pod_name, namespace, mode, "mb", mb, "duration", duration, "ip address", ip_address)
    iperf_thread_client = threading.Thread(
        target=run_iperf,
        args=(pod_name, namespace, mode, EXPERIMENT_DIR, duration, ip_address, mb, packet_length)
    )

    # Collect metrics
    metrics_thread = threading.Thread(target=collect_metrics, args=(duration, SAVE_FILE_PATH_DATA))

    # Start threads
    iperf_thread_server.start()
    iperf_thread_client.start()
    metrics_thread.start()

    # Wait for threads to finish
    iperf_thread_client.join()
    iperf_thread_server.join()
    metrics_thread.join()

    # Load UID to pod mapping
    get_all_pod_names(POD_DATA)
    create_uid_pod_mapping(UID_POD_MAPPING_PATH, POD_DATA)
    uid_pod_map = load_uid_pod_map(UID_POD_MAPPING_PATH)

    # Plot metrics
    plot_metrics(SAVE_FILE_PATH_DATA, SAVE_FILE_PATH_PLOT, interval=1, uid_pod_map=uid_pod_map)
