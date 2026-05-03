#!/bin/bash

# Bootstrap script to install cloudmesh-ai-pi on a vanilla Raspberry Pi OS
# Usage: curl -sSL https://cloudmesh-ai.github.io/pi.sh | sh

set -e

echo "--- Starting Cloudmesh AI Pi Bootstrap ---"

# 1. Install Git and Python Pip
echo "Checking for git and pip..."
if ! command -v git > /dev/null 2>&1; then
    echo "Git not found. Installing git..."
    sudo apt-get update
    sudo apt-get install -y git
else
    echo "Git is already installed."
fi

if ! command -v pip3 > /dev/null 2>&1; then
    echo "Pip not found. Installing python3-pip..."
    sudo apt-get update
    sudo apt-get install -y python3-pip
else
    echo "Pip is already installed."
fi

# 2. Setup Workspace
WORKSPACE="$HOME/cloudmesh-ai"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

# 3. Clone Repositories
REPOS="https://github.com/cloudmesh-ai/cloudmesh-ai-common.git https://github.com/cloudmesh-ai/cloudmesh-ai-pi.git"

for repo in $REPOS; do
    repo_name=$(basename "$repo" .git)
    if [ -d "$repo_name" ]; then
        echo "Updating $repo_name..."
        cd "$repo_name" && git pull && cd ..
    else
        echo "Cloning $repo_name..."
        git clone "$repo"
    fi
done

# 4. Install using pip
echo "Installing cloudmesh-ai-pi from source..."
cd cloudmesh-ai-pi

# Install dependencies and the package
# Using --break-system-packages for global install on newer Debian/Pi OS versions
sudo pip3 install . --break-system-packages || sudo pip3 install .

echo "--- Installation Complete ---"
echo "You can now use the 'cmc pi' commands."
echo "Try running: cmc pi --help"