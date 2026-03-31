#!/bin/bash
set -e

# Setup 2GB Swap (Essential for 1GB RAM instances to run Docker safely)
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Install Docker
apt-get update
apt-get install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io

# Enable Docker and allow current user
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Configure Firewall (OCI Ubuntu images use iptables or ufw)
if command -v ufw > /dev/null; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw --force enable
else
    iptables -I INPUT 6 -p tcp --dport 80 -j ACCEPT
    netfilter-persistent save
fi

echo "Setup complete. Swap enabled, Docker installed, and Port 80 opened."
