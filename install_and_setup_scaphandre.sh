#!/bin/bash

set -e

# Variables
DOMAIN_NAME="vm0"
SHARED_FS_DIR="/var/lib/libvirt/scaphandre/$DOMAIN_NAME"
RUSTUP_URL="https://sh.rustup.rs"
SCAPHANDRE_REPO="https://github.com/RootLeo00/power-consumption-tool.git"

echo "Starting bare-metal setup..."
sudo apt update

# Install Rust (set default option automatically)
echo "Installing Rust..."
sudo apt install -y curl
curl --proto '=https' --tlsv1.2 -sSf $RUSTUP_URL | sh -s -- -y
source "$HOME/.cargo/env"

# Verify Rust version
echo "Verifying Rust version..."
cargo_version=$(cargo --version | awk '{print $2}')
rustc_version=$(rustc --version | awk '{print $2}')

if [[ "$cargo_version" < "1.48.0" || "$rustc_version" < "1.48.0" ]]; then
  echo "Error: Rust version is too old. Please install at least cargo 1.48.0 and rustc 1.48.0."
  exit 1
fi

# Clone and build Scaphandre
echo "Cloning and building Scaphandre..."
git clone $SCAPHANDRE_REPO
cd power-consumption-tool/scaphandre-kubernetes/scaphandre
sudo apt install -y libssl-dev
cargo build --release
cd ..

# Setup shared filesystem for metrics
echo "Setting up shared filesystem for metrics..."
sudo mkdir -p $SHARED_FS_DIR
sudo mount -t tmpfs tmpfs_$DOMAIN_NAME $SHARED_FS_DIR -o size=10m

# Edit VM configuration with xmlstarlet
echo "Editing VM configuration for $DOMAIN_NAME..."
sudo apt install -y xmlstarlet

# Backup current XML configuration
virsh dumpxml $DOMAIN_NAME > ${DOMAIN_NAME}_backup.xml

# Extract current XML for editing
virsh dumpxml $DOMAIN_NAME > ${DOMAIN_NAME}_temp.xml

# Add <filesystem> block inside <devices>
xmlstarlet ed --inplace \
  -s "//devices" -t elem -n filesystem -v "" \
  -s "//devices/filesystem[last()]" -t attr -n type -v "mount" \
  -s "//devices/filesystem[last()]" -t attr -n accessmode -v "passthrough" \
  -s "//devices/filesystem[last()]" -t elem -n source -v "" \
  -s "//devices/filesystem[last()]/source" -t attr -n dir -v "$SHARED_FS_DIR" \
  -s "//devices/filesystem[last()]" -t elem -n target -v "" \
  -s "//devices/filesystem[last()]/target" -t attr -n dir -v "scaphandre" \
  ${DOMAIN_NAME}_temp.xml

# Add <memoryBacking> if not present
if ! xmlstarlet sel -t -c "//domain/memoryBacking" ${DOMAIN_NAME}_temp.xml &>/dev/null; then
  xmlstarlet ed --inplace \
    -s "//domain" -t elem -n memoryBacking -v "" \
    -s "//domain/memoryBacking[last()]" -t elem -n source -v "" \
    -s "//domain/memoryBacking/source" -t attr -n type -v "memfd" \
    -s "//domain/memoryBacking[last()]" -t elem -n access -v "" \
    -s "//domain/memoryBacking/access" -t attr -n mode -v "shared" \
    ${DOMAIN_NAME}_temp.xml
else
  echo "<memoryBacking> block already exists. Skipping addition."
fi

# Apply the edited XML configuration
virsh define ${DOMAIN_NAME}_temp.xml
rm -f ${DOMAIN_NAME}_temp.xml

echo "Restarting $DOMAIN_NAME..."

# Check if the domain is active
if virsh domstate $DOMAIN_NAME | grep -q "running"; then
  echo "Domain $DOMAIN_NAME is running. Shutting it down..."
  virsh shutdown $DOMAIN_NAME
  # Wait for the domain to shut down
  while virsh domstate $DOMAIN_NAME | grep -q "running"; do
    echo "Waiting for $DOMAIN_NAME to shut down..."
    sleep 2
  done
fi

# Start the domain
echo "Starting $DOMAIN_NAME..."
virsh start $DOMAIN_NAME

# Start Scaphandre exporter
echo "Starting Scaphandre exporter..."
cd scaphandre
sudo target/release/scaphandre qemu &
cd ..

# Retrieve VM IP address
echo "Retrieving IP address of $DOMAIN_NAME..."
VM_IP=$(virsh domifaddr $DOMAIN_NAME | awk '/ipv4/ {print $4}' | cut -d'/' -f1)

if [ -z "$VM_IP" ]; then
  echo "Error: Unable to retrieve IP address for $DOMAIN_NAME."
  exit 1
else
  echo "IP address of $DOMAIN_NAME is $VM_IP."
fi

# VM setup for shared filesystem
echo "Configuring shared filesystem in the VM at $VM_IP..."
ssh ubuntu@$VM_IP <<EOF
  sudo mkdir -p /var/scaphandre
  sudo mount -t 9p -o trans=virtio scaphandre /var/scaphandre
EOF

## Kubernetes setup for Scaphandre, Prometheus, and Grafana
#echo "Setting up Kubernetes metrics on master node..."
#git clone https://github.com/RootLeo00/power-consumption-tool.git
#cd power-consumption-tool

## Install Scaphandre Helm chart
#cd scaphandre-kubernetes/scaphandre
#helm install scaphandre helm/scaphandre

## Install Prometheus
#cd ../../prometheus-grafana/charts
#helm install prometheus prometheus \
#  --set alertmanager.persistentVolume.enabled=false \
#  --set server.persistentVolume.enabled=false

## Install Grafana
#kubectl create configmap scaphandre-dashboard \
#    --from-file=scaphandre-dashboard.json=docs_src/tutorials/grafana-kubernetes-dashboard.json

#helm install grafana grafana --values ~/power-consumption-tool/scaphandre-kubernetes/scaphandre/docs_src/tutorials/grafana-helm-values.yaml

## Port-forwarding for local access
#echo "Set up port forwarding for Grafana and Prometheus to access dashboards locally."

echo "Setup complete."
