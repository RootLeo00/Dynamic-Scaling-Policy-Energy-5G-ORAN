#!/bin/bash

set -e

# Variables
VM_NAME="vm0"
USERNAME="ubuntu"
PASSWORD="sbp"
TEMPLATE_DIR="/var/lib/libvirt/images/templates"
VM_DIR="/var/lib/libvirt/images/$VM_NAME"
TEMPLATE_IMAGE="ubuntu-22-server.qcow2"
CLOUD_IMAGE_URL="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
SSH_KEY=$(cat ~/.ssh/id_rsa.pub)

# Update and install dependencies
echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y \
    ninja-build zlib1g zlib1g-dev gcc-11 gcc-11-base libgcc-11-dev gcc \
    python3-venv python3-pip libglib2.0-dev git flex bison \
    libvirt-daemon libvirt-daemon-system cloud-image-utils cloud-utils whois \
    qemu qemu-kvm wget

# Enable and start libvirtd
echo "Starting libvirtd service..."
sudo systemctl enable libvirtd
sudo systemctl start libvirtd

# Download and prepare QEMU
echo "Downloading and preparing QEMU..."
cd /tmp
wget https://download.qemu.org/qemu-9.1.1.tar.xz
tar xvJf qemu-9.1.1.tar.xz
cd qemu-9.1.1
./configure
make -j$(nproc)
sudo make install

# Prepare cloud image
echo "Preparing cloud image..."
sudo mkdir -p $TEMPLATE_DIR
if [ ! -f "$TEMPLATE_DIR/$TEMPLATE_IMAGE" ]; then
    wget $CLOUD_IMAGE_URL -O /tmp/$TEMPLATE_IMAGE
    sudo mv /tmp/$TEMPLATE_IMAGE $TEMPLATE_DIR/$TEMPLATE_IMAGE
fi

# Prepare VM directory and disk
echo "Setting up VM directory and disk..."
sudo mkdir -p $VM_DIR
sudo qemu-img convert -f qcow2 -O qcow2 $TEMPLATE_DIR/$TEMPLATE_IMAGE $VM_DIR/root-disk.qcow2
sudo qemu-img resize $VM_DIR/root-disk.qcow2 50G

# Create cloud-init configuration
echo "Generating cloud-init configuration..."
cat <<EOF | sudo tee $VM_DIR/cloud-init.cfg
#cloud-config
system_info:
  default_user:
    name: $USERNAME
    home: /home/$USERNAME
password: $PASSWORD
chpasswd: { expire: False }
hostname: $VM_NAME
ssh_pwauth: True
ssh_authorized_keys:
  - $SSH_KEY
EOF

# Create cloud-init ISO
echo "Creating cloud-init ISO..."
sudo cloud-localds $VM_DIR/cloud-init.iso $VM_DIR/cloud-init.cfg

# Install the VM
echo "Installing the VM..."
sudo virt-install \
    --name $VM_NAME \
    --memory 4096 \
    --vcpus 7 \
    --disk $VM_DIR/root-disk.qcow2,device=disk,bus=virtio \
    --disk $VM_DIR/cloud-init.iso,device=cdrom \
    --os-variant ubuntu22.04 \
    --virt-type kvm \
    --graphics none \
    --network network=default,model=virtio \
    --import

# Exit message
echo "VM setup complete. Use 'virsh list' to check running VMs."
echo "To SSH into the VM, first check its IP address:"
echo "  sudo virsh domifaddr $VM_NAME"
echo "Then connect using:"
echo "  ssh $USERNAME@<VM-IP>"
