import requests
import json
import matplotlib.pyplot as plt
import pandas as pd
import time
import subprocess
import json
import matplotlib.ticker as ticker
import os

def plot_metrics(file_path_data, save_file_path_plot, uid_pod_map, interval=1):
    """Reads metrics from the JSON file, downsamples to the specified interval, and plots them."""
    # Load data from JSON file
    try:
        with open(file_path_data, "r") as f:
            metrics_over_time = json.load(f)
    except FileNotFoundError:
        print(f"{file_path_data} not found. Please collect metrics first.")
        return

    plt.figure(figsize=(20, 10))

    # Plot each container's data with a unique color
    for container_id, container_data in metrics_over_time.items():
        downsampled_data = []
        last_timestamp = None
        
        # Initialize pod name with a default value
        pod_name = "unknown"  # Default value
        
        # Downsample the data to show points every `interval` seconds
        for entry in container_data:
            timestamp = entry['timestamp']
            value = entry['value']
            
            # Find the corresponding pod name from the uid_pod_map
            for uid, name in uid_pod_map.items():
                if uid.endswith(container_id):
                    pod_name = name  # Use the mapped pod name
                    break  # Exit loop once we find the match

            # Add the first data point or any data point at least `interval` seconds after the last
            if last_timestamp is None or (timestamp - last_timestamp) >= interval:
                downsampled_data.append((timestamp, value))
                last_timestamp = timestamp
        
        if pod_name == "unknown":
            print(container_id)

        # Normalize timestamps to start from 0
        if downsampled_data:
            min_timestamp = downsampled_data[0][0]
            normalized_times = [(t[0] - min_timestamp) for t in downsampled_data]
            values = [t[1] for t in downsampled_data]
            
            # Plot the downsampled data for this container using the pod name as label
            plt.plot(normalized_times, values, marker='o', linestyle='-', label=pod_name)

    # Set up precise y-axis ticks
    plt.xlabel("Elapsed Time (s)")
    plt.ylabel("Power Consumption (Watts)")
    plt.title("Power Consumption Over Time by Pod Name")
    
    # Adjust y-axis major ticks for precision (every 5 Watts, for example)
    plt.gca().yaxis.set_major_locator(ticker.MultipleLocator(0.05))  # Major ticks every 5 Watts
    
    # Add minor ticks (every 1 Watt) for finer granularity
    plt.gca().yaxis.set_minor_locator(ticker.MultipleLocator(0.005))
    
    # Optional: You can enable the grid on minor ticks if desired
    plt.grid(which='both', axis='y', linestyle='--', color='gray', alpha=0.7)
    
    # Position the legend
    plt.legend(loc='lower center', bbox_to_anchor=(0.5, -0.40), ncol=1)  # Centered at bottom
    plt.tight_layout()

    # Save the plot to a file
    plt.savefig(save_file_path_plot)
    print(f"Plot saved as {save_file_path_plot}")


def get_all_pod_names(save_path):
    command = ['kubectl', 'get', 'pods', '--all-namespaces','-ojson']
    # Open the result file in write mode
    with open(save_path, 'w') as f:
        # Run the command, redirecting stderr to /dev/null
        subprocess.run(command, stdout=f, stderr=subprocess.DEVNULL, check=True)

    print(f"List of pod names saved to '{save_path}'")


def get_pod_info(search_term):
    """Retrieve the pod name and namespace based on the search term."""
    try:
        # Get the output of the kubectl command to find the pod
        result = subprocess.run(
            ['kubectl', 'get', 'pods', '-A'],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output to find the matching pod
        for line in result.stdout.splitlines()[1:]:  # Skip the header
            if search_term in line:
                parts = line.split()
                namespace = parts[0]
                pod_name = parts[1]
                return pod_name, namespace

        print("Pod not found.")
        return None, None
    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl: {e}")
        return None, None

def run_iperf(pod_name, namespace, mode, log_dir,duration=None,ip_address=None, mb=None, packet_length=None):
   
    # Set up log file path and header
    mode_suffix = 'client' if mode == 'client' else 'server'
    log_file = f"{log_dir}/log_iperf_{mode_suffix}_{pod_name}"
    if ip_address and mb:
        log_file += f"_{ip_address}_{mb}_{duration}_{packet_length}"
    log_file += ".csv"

    header = "Timestamp,Source_IP,Source_Port,Destination_IP,Destination_Port,Protocol,Interval,Transfer,Bitrate,Jitter,Lost_Packets,Lost_Packets_Percent,Unknown1,Unknown2"
    
    # Write the header to the log file
    with open(log_file, 'w') as f:
        f.write(header + '\n')

    try:
        # Construct the iperf command
        if mode == 'client':
            if not all([ip_address, mb, duration, packet_length]):
                raise ValueError("Client mode requires ip_address, value, duration, and packet_length parameters.")

            iperf_command = [
                'kubectl', 'exec', pod_name, '-n', namespace,
                '--', 'iperf', '-c', ip_address, '-u', '-i', '1',
                '-b', f"{mb}M", '-t', str(duration), '-l', str(packet_length), '--reportstyle', 'C'
            ]
        elif mode == 'server':
            iperf_command = [
                'kubectl', 'exec', pod_name, '-n', namespace,
                '--', 'iperf', '-s', '-u', '-i', '1', '-t', str(duration), '--reportstyle', 'C'
            ]
        else:
            raise ValueError("Mode must be either 'client' or 'server'.")

        # Print the command for debugging
        print("Running command:", iperf_command)

        # Open the log file in append mode
        with open(log_file, 'a') as f:
            # Run the iperf command, redirecting stderr to /dev/null
            subprocess.run(iperf_command, stdout=f, stderr=subprocess.DEVNULL, check=True)
        
        print(f"Log file saved to: {log_file}")

    except subprocess.CalledProcessError as e:
        print(f"Error executing iperf: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")




def run_iperf_tcp(pod_name, namespace, mode, log_dir,duration=None,ip_address=None, mb=None, packet_length=None):
   
    # Set up log file path and header
    mode_suffix = 'client' if mode == 'client' else 'server'
    log_file = f"{log_dir}/log_iperf_{mode_suffix}_{pod_name}"
    if ip_address and mb:
        log_file += f"_{ip_address}_{mb}_{duration}_{packet_length}"
    log_file += ".csv"

    header = "Timestamp,Source_IP,Source_Port,Destination_IP,Destination_Port,Protocol,Interval,Transfer,Bitrate,Jitter,Lost_Packets,Lost_Packets_Percent,Unknown1,Unknown2"
    
    # Write the header to the log file
    with open(log_file, 'w') as f:
        f.write(header + '\n')

    try:
        # Construct the iperf command
        if mode == 'client':
            if not all([ip_address, mb, duration, packet_length]):
                raise ValueError("Client mode requires ip_address, value, duration, and packet_length parameters.")

            iperf_command = [
                'kubectl', 'exec', pod_name, '-n', namespace,
                '--', 'iperf', '-c', ip_address, '-i', '1',
                '-b', f"{mb}M", '-t', str(duration), '-l', str(packet_length), '--reportstyle', 'C'
            ]
        elif mode == 'server':
            iperf_command = [
                'kubectl', 'exec', pod_name, '-n', namespace,
                '--', 'iperf', '-s', '-i', '1', '-t', str(duration), '--reportstyle', 'C'
            ]
        else:
            raise ValueError("Mode must be either 'client' or 'server'.")

        # Print the command for debugging
        print("Running command:", iperf_command)

        # Open the log file in append mode
        with open(log_file, 'a') as f:
            # Run the iperf command, redirecting stderr to /dev/null
            subprocess.run(iperf_command, stdout=f, stderr=subprocess.DEVNULL, check=True)
        
        print(f"Log file saved to: {log_file}")

    except subprocess.CalledProcessError as e:
        print(f"Error executing iperf: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def run_iperf_tcp_number_packets(pod_name, namespace, mode, log_dir, ip_address=None, mb=None, packet_length=None):
    # Set up log file path and header
    mode_suffix = 'client' if mode == 'client' else 'server'
    log_file = f"{log_dir}/log_iperf_{mode_suffix}_{pod_name}"
    if ip_address and mb:
        log_file += f"_{ip_address}_{mb}_{duration}_{packet_length}"
    log_file += ".csv"

    header = "Timestamp,Source_IP,Source_Port,Destination_IP,Destination_Port,Protocol,Interval,Transfer,Bitrate,Jitter,Lost_Packets,Lost_Packets_Percent,Unknown1,Unknown2"
    
    # Write the header to the log file
    with open(log_file, 'w') as f:
        f.write(header + '\n')

    try:
        # Construct the iperf command
        if mode == 'client':
            if not all([ip_address, mb, duration, packet_length]):
                raise ValueError("Client mode requires ip_address, value, duration, and packet_length parameters.")

            iperf_command = [
                'kubectl', 'exec', pod_name, '-n', namespace,
                '--', 'iperf', '-c', ip_address, '-i', '1',
                '-n', f"{mb}M", '-l', str(packet_length), '--reportstyle', 'C'
            ]
        elif mode == 'server':
            iperf_command = [
                'kubectl', 'exec', pod_name, '-n', namespace,
                '--', 'iperf', '-s', '-i', '1', '--reportstyle', 'C'
            ]
        else:
            raise ValueError("Mode must be either 'client' or 'server'.")

        # Print the command for debugging
        print("Running command:", iperf_command)

        # Open the log file in append mode
        with open(log_file, 'a') as f:
            # Run the iperf command, redirecting stderr to /dev/null
            subprocess.run(iperf_command, stdout=f, stderr=subprocess.DEVNULL, check=True)
        
        print(f"Log file saved to: {log_file}")

    except subprocess.CalledProcessError as e:
        print(f"Error executing iperf: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")



def create_uid_pod_mapping(save_file_path, pod_list_path):
    # Load pod data from JSON file
    try:
        with open(pod_list_path, "r") as f:
            pod_data = json.load(f)
    except FileNotFoundError:
        print(f"{pod_list_path} not found. Please collect the pod metrics first.")
        return

    # Initialize a dictionary to map UIDs to pod names
    uid_pod_map = {}

    # Retrieve all UIDs and corresponding pod names
    for pod_info in pod_data.get("items", []):  # `items` is a list of pods
        metadata = pod_info.get("metadata", {})
        uid = metadata.get("uid")
        pod_name = metadata.get("name")

        if uid and pod_name:  # Check if both uid and name exist
            uid_pod_map[uid] = pod_name

    # Convert the mapping to a DataFrame
    uid_pod_df = pd.DataFrame(list(uid_pod_map.items()), columns=['UID', 'Pod Name'])

    # Save the DataFrame to a CSV file
    uid_pod_df.to_csv(save_file_path, index=False)



def load_uid_pod_map(csv_file_path):
    """Loads UID to pod name mapping from a CSV file and returns it as a dictionary."""
    try:
        # Load the CSV file into a DataFrame
        df = pd.read_csv(csv_file_path)
        # Create a dictionary mapping UIDs to pod names
        uid_pod_map = dict(zip(df['UID'], df['Pod Name']))
        return uid_pod_map
    except FileNotFoundError:
        print(f"{csv_file_path} not found.")
        return {}
    
def fetch_host_energy_metrics(prometheus_url, query):
    try:
        # Send the query to Prometheus
        response = requests.get(f"{prometheus_url}/api/v1/query", params={'query': query})
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON response
        result = response.json()
        
        if result['status'] != 'success' or 'data' not in result:
            print(f"Unexpected response structure: {result}")
            return {}

        # Initialize the metrics dictionary
        metrics_by_node = {}
        
        for entry in result['data']['result']:
            # Extract node_name and metric value
            node_name = entry['metric'].get('node', 'unknown')
            if node_name == "unknown":
                # print("Warning: Container ID is unknown for entry:", entry)
                continue  # Skip entries with no valid container ID
            
            value = float(entry['value'][1])  # Metric value (e.g., power consumption)
            timestamp = time.time()  # Current timestamp
            
            # Initialize the container ID entry if it doesn't exist
            if node_name not in metrics_by_node:
                metrics_by_node[node_name] = []
            
            # Append the metric entry
            metrics_by_node[node_name].append({
                'timestamp': timestamp,
                'value': value,
            })

        return metrics_by_node
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching metrics from Prometheus: {e}")
        return {}
    except (ValueError, KeyError) as e:
        print(f"Error parsing Prometheus response: {e}")
        return {}


def fetch_energy_metrics(prometheus_url, query):
    """
    Fetches metrics from Prometheus and returns a dictionary of values grouped by container ID.
    
    Args:
        prometheus_url (str): Base URL of the Prometheus server.
        query (str): Prometheus query to retrieve the desired metrics.
    
    Returns:
        dict: A dictionary where keys are container IDs and values are lists of metric entries.
    """
    try:
        # Send the query to Prometheus
        response = requests.get(f"{prometheus_url}/api/v1/query", params={'query': query})
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON response
        result = response.json()
        
        if result['status'] != 'success' or 'data' not in result:
            print(f"Unexpected response structure: {result}")
            return {}

        # Initialize the metrics dictionary
        metrics_by_container = {}
        
        for entry in result['data']['result']:
            # Extract container_id and metric value
            container_id = entry['metric'].get('container_id', 'unknown')
            if container_id == "unknown":
                # print("Warning: Container ID is unknown for entry:", entry)
                continue  # Skip entries with no valid container ID
            
            value = float(entry['value'][1])  # Metric value (e.g., power consumption)
            cmdline = entry['metric'].get('cmdline', 'unknown')  # Command line info
            timestamp = time.time()  # Current timestamp
            
            # Initialize the container ID entry if it doesn't exist
            if container_id not in metrics_by_container:
                metrics_by_container[container_id] = []
            
            # Append the metric entry
            metrics_by_container[container_id].append({
                'timestamp': timestamp,
                'value': value,
                'cmdline': cmdline
            })

        return metrics_by_container
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching metrics from Prometheus: {e}")
        return {}
    except (ValueError, KeyError) as e:
        print(f"Error parsing Prometheus response: {e}")
        return {}


def fetch_cpu_metrics(prometheus_url, query, pod_name):
    try:
        # Send the query to Prometheus
        response = requests.get(f"{prometheus_url}/api/v1/query", params={'query': query})
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON response
        result = response.json()
        print("result",result)
        
        if result['status'] != 'success' or 'data' not in result:
            print(f"Unexpected response structure: {result}")
            return {}

        # Initialize the metrics dictionary
        metrics_by_pod = {}
        
        for entry in result['data']['result']:
            
            value = float(entry['value'][1])  # Metric value (e.g., power consumption)
            timestamp = time.time()  # Current timestamp
            
            # Initialize the container ID entry if it doesn't exist
            if pod_name not in metrics_by_pod:
                metrics_by_pod[pod_name] = []
            
            # Append the metric entry
            metrics_by_pod[pod_name].append({
                'timestamp': timestamp,
                'value': value,
            })

        return metrics_by_pod
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching metrics from Prometheus: {e}")
        return {}
    except (ValueError, KeyError) as e:
        print(f"Error parsing Prometheus response: {e}")
        return {}


def collect_metrics(duration, save_file_path, prometheus_url, mode, pod_name_cpu_metrics):
    start_time = time.time()
    metrics_over_time={}
    
    # Define the Prometheus queries basecd on mode
    if mode=="cpu":
        # query = 'rate(container_cpu_usage_seconds_total{}[1m]) * 1000'
        query = '100 * (sum(rate(container_cpu_usage_seconds_total{pod="'+pod_name_cpu_metrics+'"}['+str(round(duration))+'s])) by (pod)/ sum(kube_pod_container_resource_limits{pod="'+pod_name_cpu_metrics+'", resource="cpu"}) by (pod))'
        print('query',query)
        metrics = fetch_cpu_metrics(prometheus_url, query, pod_name_cpu_metrics)
        print("metrics",metrics)
        for id, data_points in metrics.items():
            print("id, data_points",id, data_points)
            if id not in metrics_over_time:
                metrics_over_time[id] = []
            metrics_over_time[id].extend(data_points)

    elif mode == "energy":
        query = 'sum(scaph_process_power_consumption_microwatts{container_scheduler="docker"} / 1000000) by (container_id)'
        while time.time() - start_time < duration:
            try:
                # Fetch both power consumption metrics
                metrics = fetch_energy_metrics(prometheus_url, query)
                
                # Extract CPU usage values
                for id, data_points in metrics.items():
                    if id not in metrics_over_time:
                        metrics_over_time[id] = []
                    metrics_over_time[id].extend(data_points)

                time.sleep(1)  # Adjust polling interval as needed

            except Exception as e:
                print(f"Error collecting metrics: {e}")
                time.sleep(5)  # Retry after some delay if error occurs

    elif mode == "host_energy":
        query = 'scaph_host_power_microwatts / 1000000 > 0.001'
        while time.time() - start_time < duration:
            try:
                # Fetch both power consumption metrics
                metrics = fetch_host_energy_metrics(prometheus_url, query)
                
                # Extract CPU usage values
                for id, data_points in metrics.items():
                    if id not in metrics_over_time:
                        metrics_over_time[id] = []
                    metrics_over_time[id].extend(data_points)

                time.sleep(1)  # Adjust polling interval as needed

            except Exception as e:
                print(f"Error collecting metrics: {e}")
                time.sleep(5)  # Retry after some delay if error occurs
    else: 
        print(f"Error collecting metrics due to invalid mode: {mode}")
        return None

    # Save collected metrics to a file
    with open(save_file_path, "w") as f:
        json.dump(metrics_over_time, f)


def collect_metrics_with_stop_event(save_file_path, prometheus_url, mode, pod_name_cpu_metrics, stop_event):
    """
    Collect metrics continuously until a stop event is triggered.
    
    Args:
        save_file_path (str): Path to save the collected metrics.
        prometheus_url (str): Prometheus server URL.
        mode (str): Mode of metrics collection ('cpu', 'energy', or 'host_energy').
        pod_name_cpu_metrics (str): Pod name for CPU metrics.
        stop_event (threading.Event): Event to signal stopping the collection.
    """
    metrics_over_time = {}
    
    try:
        # Define the Prometheus query based on the mode
        if mode == "cpu":
            query = (
                f'100 * (sum(rate(container_cpu_usage_seconds_total{{pod="{pod_name_cpu_metrics}"}}[5s])) by (pod) '
                f'/ sum(kube_pod_container_resource_limits{{pod="{pod_name_cpu_metrics}", resource="cpu"}}) by (pod))'
            )
        elif mode == "energy":
            query = 'sum(scaph_process_power_consumption_microwatts{container_scheduler="docker"} / 1000000) by (container_id)'
        elif mode == "host_energy":
            query = 'scaph_host_power_microwatts / 1000000 > 0.001'
        else:
            print(f"Invalid mode: {mode}")
            return

        # Continuous collection loop
        while not stop_event.is_set():
            try:
                # Fetch metrics based on the mode
                if mode == "cpu":
                    metrics = fetch_cpu_metrics(prometheus_url, query, pod_name_cpu_metrics)
                elif mode in {"energy", "host_energy"}:
                    metrics = fetch_energy_metrics(prometheus_url, query)

                # Collect the metrics over time
                for id, data_points in metrics.items():
                    if id not in metrics_over_time:
                        metrics_over_time[id] = []
                    metrics_over_time[id].extend(data_points)

                time.sleep(1)  # Polling interval
            except Exception as e:
                print(f"Error collecting metrics: {e}")
                time.sleep(5)  # Retry after a delay if an error occurs

    finally:
        # Save collected metrics to a file
        with open(save_file_path, "w") as f:
            json.dump(metrics_over_time, f)
        print(f"Metrics saved to {save_file_path}")


def generate_experiment_dir(mb, duration, packet_length, description):
    """
    Generates a directory name for the experiment based on the parameters and a description.
    """
    return f"{mb}_{duration}_{packet_length}_{description}"




def check_ping(pod_name, namespace, target_ip, max_retries=4):
    """
    Check connectivity from a pod to a target IP with retries.

    Args:
        pod_name (str): Name of the pod to execute the ping command.
        namespace (str): Kubernetes namespace of the pod.
        target_ip (str): Target IP address to ping.
        max_retries (int): Maximum number of retry attempts.

    Returns:
        bool: True if the ping succeeds, False otherwise.
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            ping_command = [
                "kubectl", "exec", pod_name, "-n", namespace,
                "--", "ping", "-c", "3", target_ip
            ]
            subprocess.run(ping_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Ping from {pod_name} to {target_ip} successful.")
            return True  # Ping successful
        except subprocess.CalledProcessError as e:
            retry_count += 1
            print(f"Ping attempt {retry_count} failed: {e}")
            time.sleep(1)  # Wait 1 second before retrying

    print(f"ERROR: Ping test failed after {max_retries} attempts.")
    return False  # Ping failed after retries




def download_tcpdump(pod,namespace, download_to_dir="pcap_files"):
    """
    Downloads all files from /tmp/pcap/ in the 'tcpdump' container
    of the specified pod pod.
    
    Args:
        pod (str): Name of the pod pod.
        download_to_dir (str): Local directory to save the downloaded files. Default is 'pcap_files'.

    Returns:
        str: Path to the directory where the files are saved.
    """
    # Ensure the local directory exists
    os.makedirs(download_to_dir, exist_ok=True)

    # Define the source path in the pod's container
    remote_path = "/tmp/pcap/"
    container_name = "tcpdump"  # Specify the container name in the pod pod
    
    try:
        # Run kubectl cp command to copy files
        command = [
            "kubectl", "cp",
            f"{pod}:{remote_path}",  # Pod and path in the container
            download_to_dir,  # Local destination directory
            "-c", container_name,  # Specify the container within the pod
            "-n", namespace # namespace of the pod
        ]
        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True)
        print(f"Files successfully downloaded to: {download_to_dir}")
        
        return os.path.abspath(download_to_dir)
    
    except subprocess.CalledProcessError as e:
        print(f"Error during file download: {e}")
        raise RuntimeError(f"Failed to download files from {pod}:{remote_path}")


