from flask import Flask, jsonify, request
import subprocess
import requests
import json
import threading
import time
from prometheus_client import CollectorRegistry, Gauge, generate_latest

app = Flask(__name__)

# Constants for Prometheus URL
PROMETHEUS_URL = "http://prometheus-server.default.svc.cluster.local:80/"  # Change to your Prometheus server URL

# Prometheus client registry
registry = CollectorRegistry()

# Global variable to store pod metrics and UID to pod mapping
pod_metrics = {}
uid_pod_map = {}

# Define Prometheus Gauge to represent pod power consumption
pod_power_gauge = Gauge('pod_power_consumption_mw', 'Pod Power Consumption in mW', ['pod'], registry=registry)

# Function to get pod information and UID based on a search term
def get_uid_pod_map():
    """Retrieve a dictionary mapping pod names to their truncated UIDs (last segment)."""
    uid_pod_map = {}
    try:
        # Get the output of the kubectl command to find the pods with their UIDs
        result = subprocess.run(
            ['kubectl', 'get', 'pods', '-A', '-o', 'json'],
            capture_output=True,
            text=True,
            check=True
        )
        
        pods_info = json.loads(result.stdout)
        for item in pods_info.get('items', []):
            pod_name = item['metadata']['name']
            uid = item['metadata']['uid']
            truncated_uid = uid.split('-')[-1]  # Take the last part of the UID
            uid_pod_map[truncated_uid] = pod_name  # Map truncated UID to pod name

        return uid_pod_map

    except subprocess.CalledProcessError as e:
        print(f"Error executing kubectl: {e}")
        return {}

# Fetch metrics from Prometheus for a specific truncated UID
def fetch_metrics_for_uid(truncated_uid):
    """Fetches metrics from Prometheus for a specific truncated UID."""
    query = f'sum(scaph_process_power_consumption_microwatts{{container_id="{truncated_uid}"}}) / 1000000'
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={'query': query})
        response.raise_for_status()  # Raise an error for bad responses
        metrics_data = response.json()
        return metrics_data.get('data', {}).get('result', [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching metrics for truncated UID {truncated_uid}: {e}")
        return []

# Background thread function to scrape and update metrics every 0.5 seconds
def scrape_metrics():
    global pod_metrics, uid_pod_map   # Declare pod_metrics as global to modify it
    while True:
        new_metrics = {}  # Temporary dictionary to hold the latest metrics
        for truncated_uid, pod_name in uid_pod_map.items():
            metrics = fetch_metrics_for_uid(truncated_uid)
            if metrics:
                # Use the latest value available for this metric
                latest_value = float(metrics[0]['value'][1])
                new_metrics[pod_name] = latest_value  # Save in the temporary dictionary
        
        pod_metrics = new_metrics  # Update global variable with the new metrics
        
        # Wait for 0.5 seconds before the next scrape
        time.sleep(5)

# Background thread function to update the UID to pod mapping every 5 seconds
def update_uid_pod_map():
    global uid_pod_map  # Declare uid_pod_map as global to modify it
    while True:
        uid_pod_map = get_uid_pod_map()  # Update the global uid_pod_map
        # Wait for 5 seconds before the next update
        time.sleep(5)

# Start the background threads
threading.Thread(target=scrape_metrics, daemon=True).start()
threading.Thread(target=update_uid_pod_map, daemon=True).start()

# Get all pod metrics and expose them in Prometheus format
@app.route('/metrics', methods=['GET'])
def metrics():
    # Clear the registry before populating with new data
    #registry.clear()  # Clear previous metrics

    # Populate the Gauge with values from the global pod_metrics variable
    for pod, power in pod_metrics.items():
        pod_power_gauge.labels(pod=pod).set(power)

    return generate_latest(registry)

# Endpoint to get metrics by pod
@app.route('/api/metrics-by-pod', methods=['GET'])
def get_metrics_by_pod():
    search_term = request.args.get('search_term')
    if not search_term:
        return jsonify({"error": "Search term is required"}), 400

    # Find the truncated UID based on the provided search term (pod name)
    truncated_uid = next((uid for uid, name in uid_pod_map.items() if search_term in name), None)
    
    if not truncated_uid:
        return jsonify({"error": "Pod not found"}), 404

    metrics = fetch_metrics_for_uid(truncated_uid) 
    return jsonify(metrics)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # Change port as necessary

