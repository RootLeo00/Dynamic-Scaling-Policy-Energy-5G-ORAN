# Project Setup and Configuration

This README provides step-by-step instructions to install and configure the necessary tools and dependencies for deploying a 5G network and monitoring power consumption using Scaphandre, Prometheus, and Grafana.

---

## 1. Install 5GBPv3

To install the 5GBPv3 (5G Blueprint v3), follow the official instructions at the [5GBPv3 repository](https://gitlab.inria.fr/slices-ri/blueprints/post-5g/reference_implementation/-/tree/main?ref_type=heads#deploy-5g-network).

---

## 2. Set Up Scaphandre

Scaphandre is a power monitoring tool that can be integrated into Kubernetes for energy tracking. Follow these steps to set it up:

```bash
cd ~/Dynamic-Scaling-Policy-Energy-5G-ORAN/scaphandre-kubernetes/scaphandre/
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
cd ~/Dynamic-Scaling-Policy-Energy-5G-ORAN/prometheus-grafana/charts
helm install prometheus prometheus --set alertmanager.persistentVolume.enabled=false --set server.persistentVolume.enabled=false
```
Create a Grafana dashboard configuration for Scaphandre
```bash
kubectl create configmap scaphandre-dashboard \
    --from-file=~/Dynamic-Scaling-Policy-Energy-5G-ORAN/prometheus-grafana/charts/grafana/dashboards/custom-dashboard.json
```
Install Grafana
```bash
helm install grafana grafana --values ~/Dynamic-Scaling-Policy-Energy-5G-ORAN/scaphandre-kubernetes/scaphandre/docs_src/tutorials/grafana-helm-values.yaml
```

## 3. Set Up Power Consumption App
```bash
cd ~/Dynamic-Scaling-Policy-Energy-5G-ORAN/power-metrics-per-pod-app
```
Set config in order for the pod to run `kubectl`
```bash
cat ~/.kube/config > kube_conf/config
```
Deploy with old fashion kubectl:
```bash
kubectl apply -f kubernetes/deployment.yaml
```

### 4. Run multiple automated experiments with Ansible
BP v3 deployment + iperf experiments can be run in an automated Ansible+Python script.
Preconfiguration: creation of secrets file (Ansible vaults)

To create the file and vault it, use the following command:
```bash
cd ~/Dynamic-Scaling-Policy-Energy-5G-ORAN/power-metrics-per-pod-realtime/
EDITOR=vim ansible-vault create secrets.yaml
```
In this secret file you have to define
```yaml
secrets:
  prometheus_basic_auth_password: REDACTED
  grafana_password: REDACTED
```
This will create the encrypted file `secrets.yml` that we can use later to
access to critical data.

To run the experiments 
```bash
docker build -t deployment_node -f Dockerfile .
sudo docker run --rm -it -v "$(pwd)":/blueprint -v ${HOME}/.ssh/id_rsa:/id_rsa deployment_node
ansible-playbook -i inventories/staging --extra-vars "@params.yaml" --extra-vars "@params.5g.yaml" --extra-vars "@secrets.yaml" --ask-vault-pass run_tests.yaml
```

### 4. Run single experiments for one single type of scaling
Under `Dynamic-Scaling-Policy-Energy-5G-ORAN/single_tests` there are several python scripts.
```bash
cd ~/Dynamic-Scaling-Policy-Energy-5G-ORAN/power-metrics-per-pod-realtime/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 multiple_tests_packet_energy_4UE_4CU_tcp_iperf-n.py # change this to the configuration you want to test
```
