import os
import pandas as pd
import requests
from datetime import datetime
import numpy as np

# Load CSV into DataFrame
csv_file = '/home/pow_cons/power-consumption-tool/power-metrics-per-pod-realtime/data/2CU_deployment_time_3/log_deploy_cu2_original.csv'
df = pd.read_csv(csv_file)

# Function to convert datetime to Unix timestamp
def to_unix_timestamp(dt_str):
    dt_obj = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    return int(dt_obj.timestamp())

# Function to fetch the power metric from Prometheus
def fetch_power_values(prometheus_url, query, start_timestamp, end_timestamp, step='1s'):
    try:
        # Send the query to Prometheus to get values over the time range
        response = requests.get(f"{prometheus_url}/api/v1/query_range", 
                                params={'query': query, 'start': start_timestamp, 'end': end_timestamp, 'step': step})
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON response
        result = response.json()
        
        # Extract the power values from the result
        if result['status'] == 'success' and result['data']['result']:
            # Get power values (timestamps and corresponding power values)
            power_values = [(float(value[1]), float(value[0])) for value in result['data']['result'][0]['values']]
            return power_values
        else:
            print(f"No data returned for query: {query}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Prometheus: {e}")
        return None

# Function to calculate the energy using numpy.trapz
def calculate_energy_trapz(power_values):
    # Extract power and time values separately
    power_array = [value[0] for value in power_values]  # Power values in microwatts
    time_array = [value[1] for value in power_values]  # Timestamps in seconds
    
    # Use numpy.trapz to compute the integral (area under the curve)
    # Convert power to watts (from microwatts) during the calculation
    energy = np.trapz(np.array(power_array) * 1e-6, x=np.array(time_array))
    
    return energy  # Energy in joules

# Process each row in the CSV
energy_values = []  # To store the calculated energy values
prometheus_url = "http://132.227.122.122:31894"

for index, row in df.iterrows():
    start_timestamp = to_unix_timestamp(row['Start Timestamp'])
    end_timestamp = to_unix_timestamp(row['End Timestamp'])
    duration = row['Duration']  # Duration is already available in the CSV
    
    # Construct the Prometheus query for this time range
    query = f'scaph_host_power_microwatts{{node="node2"}}'
    
    # Fetch power values for the entire interval
    power_values = fetch_power_values(prometheus_url, query, start_timestamp, end_timestamp)
    
    if power_values:
        try:
            # Attempt to calculate energy using the trapezoidal rule
            energy_joules = calculate_energy_trapz(power_values)
        except Exception as e:
            print(f"Error calculating energy using trapezoidal rule: {e}")
            # Fallback to max power calculation if trapz fails
            max_power_microwatts = max([value[0] for value in power_values])
            energy_joules = (max_power_microwatts * 1e-6) * duration
        
        energy_values.append(energy_joules)
    else:
        energy_values.append(None)

# Add the energy column to the DataFrame
df['Energy'] = energy_values

# Create the directory if it doesn't exist
output_dir = os.path.dirname(csv_file)  # Get the directory from the original CSV path
if not os.path.exists(output_dir):
    os.makedirs(output_dir)  # Create the directory if it doesn't exist

# Generate the output file path
updated_csv_file = os.path.join(output_dir, 'updated_' + os.path.basename(csv_file))

# Save the updated DataFrame to the new CSV file
df.to_csv(updated_csv_file, index=False)
print(f"Updated CSV saved as: {updated_csv_file}")
