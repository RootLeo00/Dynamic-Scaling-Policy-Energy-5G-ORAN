import os
import sys
import argparse
import time
from utils import collect_metrics_with_stop_event, run_iperf_tcp_number_packets
from stoppable_thread import StoppableThread
from threading import Event, Thread

def run(data_volume_list, num_cus, ue_pod_names, upf_pod_names, prometheus_url, core_namespace, ran_namespace, packet_length, duration_baseline):
    
    per_ue_data = [vol // num_cus for vol in data_volume_list]
    
    for index, data in enumerate(per_ue_data):
        experiment_dir = f"experiment_{index}_{data}_{packet_length}"
        os.makedirs(experiment_dir, exist_ok=True)

        stop_event = Event()
        metrics_thread = StoppableThread(target=collect_metrics_with_stop_event, args=(os.path.join(experiment_dir, "metrics.json"), prometheus_url, "energy", None, stop_event), stop_event=stop_event)

        # Start iperf servers first
        server_threads = []
        client_threads = []
        
        upf_pod_name=upf_pod_names[0] # although you could pass a list of upfs in the main args, we consider only one upf in our experiments
        for i,ue_pod_name in enumerate(ue_pod_names):
            ue_pod_name=ue_pod_name[0]
            upf_pod_name=upf_pod_name[0]
            server_threads.append(Thread(target=run_iperf_tcp_number_packets, args=(ue_pod_name, ran_namespace, "server", experiment_dir, f"12.1.1.10{i}", data, packet_length)))
            client_threads.append(Thread(target=run_iperf_tcp_number_packets, args=(upf_pod_name, core_namespace, "client", experiment_dir, f"12.1.1.10{i}", data, packet_length)))

        # Start the metrics collection thread
        metrics_thread.start()

        # Start server threads first
        for t in server_threads:
            t.start()

        time.sleep(duration_baseline)  # Ensure servers are ready before starting clients

        # Start client threads
        for t in client_threads:
            t.start()

        # Wait for all threads to finish
        for t in server_threads:
            t.join()

        for t in client_threads:
            t.join()

        time.sleep(15)
        stop_event.set()
        metrics_thread.join()

# Define a custom argument type for a list of strings
def list_of_strings(arg):
    return arg.strip().split(' ')
 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run experiments with multiple UEs")
    parser.add_argument("--data-volumes", type=int, nargs='+', help="List of data volumes separated by spaces")
    parser.add_argument("--num-cus", type=int, choices=[1, 2, 3, 4], help="Number of CUs (must be 1, 2, 3, or 4)")
    parser.add_argument("--ue-pod-names", type=list_of_strings, nargs='+', default=[], help="List of oai-nr-ue pod names")
    parser.add_argument("--upf-pod-names", type=list_of_strings, nargs='+', default=[], help="List of oai-upf pod names")
    parser.add_argument("--prometheus-url", type=str, help="Prometheus URL for metrics")
    parser.add_argument("--core-namespace", type=str, help="Core namespace")
    parser.add_argument("--ran-namespace", type=str, help="RAN namespace")
    parser.add_argument("--packet-length", type=int, help="Packet length for iperf")
    parser.add_argument("--duration-baseline", type=int, help="Duration for the baseline in seconds")

    args = parser.parse_args()
    if not args.data_volumes or not args.num_cus or not args.ue_pod_names or not args.upf_pod_names:
        parser.print_usage()
        sys.exit(1)

    # Check if data volumes are provided and greater than 0
    if any(volume <= 0 for volume in args.data_volumes):
        print("Error: All data volumes must be greater than 0.")
        parser.print_usage()
        sys.exit(1)

    # Run the experiment with the provided parameters
    run(
        args.data_volumes, 
        args.num_cus, 
        args.ue_pod_names, 
        args.upf_pod_names, 
        args.prometheus_url, 
        args.core_namespace, 
        args.ran_namespace, 
        args.packet_length, 
        args.duration_baseline
    )

    print("All experiments are done.")
    sys.exit(0)
