#Power Consumption Monitoring Tool

# Project Setup and Configuration

This README provides step-by-step instructions to install and configure the necessary tools and dependencies for deploying a 5G network and monitoring power consumption using Scaphandre, Prometheus, and Grafana.

---

## 1. Install 5GBPv3

To install the 5GBPv3 (5G Blueprint v3), follow the official instructions at the [5GBPv3 repository](https://gitlab.inria.fr/slices-ri/blueprints/post-5g/reference_implementation/-/tree/main?ref_type=heads#deploy-5g-network).

---

## 2. Set Up Scaphandre

Scaphandre is a power monitoring tool that can be integrated into Kubernetes for energy tracking. Follow these steps to set it up:

```bash
cd ~/power-consumption-tool/scaphandre-kubernetes/scaphandre/
```

### Configure values.yaml

Ensure that the `helm/scaphandre/values.yaml` file is properly configured based on your environment:

- For Virtual Machines (VMs): Update the values.yaml file to add in `arg{}` the "vm" parameter (`args{vm}`)
- For Bare-Metal Deployments: No changes needed

Install Scaphandre with helm
```bash
helm install scaphandre helm/scaphandre
```

## 2. Set Up Prometheus and Grafana

Prometheus and Grafana will be used for monitoring and visualizing power consumption data.
Install Prometheus

```bash
cd ~/power-consumption-tool/prometheus-grafana/charts
helm install prometheus prometheus --set alertmanager.persistentVolume.enabled=false --set server.persistentVolume.enabled=false
```
## DOC TO BE FIXED  
Create a Grafana dashboard configuration for Scaphandre
```bash
kubectl create configmap scaphandre-dashboard \
    --from-file=scaphandre-dashboard.json=~/power-consumption-tool/scaphandre-kubernetes/scaphandre/
```
Install Grafana
```bash
helm install grafana grafana --values ~/power-consumption-tool/scaphandre-kubernetes/scaphandre/docs_src/tutorials/grafana-helm-values.yaml
```
##

## 3. Set Up Power Consumption App
```bash
cd ~/power-consumption-tool/power-metrics-per-pod-app
```
Set config in order for the pod to run `kubectl`
```bash
cat ~/.kube/config > kube_conf/config
```
Deploy with old fashion kubectl:
```bash
kubectl apply -f kubernetes/deployment.yaml
```

### 4. Run multiple automated experiments
BP v3 deployment + iperf experiments can be run in an automated python script:
```bash
cd ~/power-consumption-tool/power-metrics-per-pod-realtime/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
run the experiment, as an example:
```bash
cd ~/power-consumption-tool/power-metrics-per-pod-realtime/test_automation
python3 multiple_tests_packet_energy.py 
```


