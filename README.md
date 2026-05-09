# OpenClaw Pi Deployment Manual

This system provides a production-grade pipeline for flashing, configuring, and hardening Raspberry Pi nodes for the OpenClaw cluster.

## Table of Contents
- Overview
- Prerequisites
- Deployment Workflow
- Quick Start: Single Node
- Advanced: Cluster Batch Deployment
- Configuration Reference
- Specialized Features
- Post-Burn Installation
- Production Hardening Details
- Management and Maintenance
- Development

---

## Overview
The deployment process is split into two distinct phases to ensure maximum reliability and security:

1. Burn Phase (Host Machine): Flashes the OS, injects SSH keys, and configures basic identity.
2. Install Phase (On the Pi): Applies performance tweaks, security hardening, and installs the OpenClaw agent.

---

## Prerequisites
- Host OS: Linux (Required for low-level disk access and rpi-imager CLI).
- Hardware: 
  - Raspberry Pi (3, 4, or 5).
  - SD Cards or USB SSDs.
  - (Optional) USB Hub for batch burning.
- Software: 
  - Raspberry Pi Imager (v2.0.7+ for CLI support).
  - cmc CLI tool installed.

---

## Deployment Workflow
The recommended path for a successful cluster deployment is:
1. Create a "Golden Node" (Single Node Burn) to verify your SSH keys and image.
2. Boot the Golden Node and run the `install` command to verify hardening.
3. Define your cluster in a YAML file using the `range` and `prefix` features.
4. Use the Batch Burn process with a USB hub to flash all remaining nodes.
5. Boot each node and run the `install` command.

---

## Quick Start: Single Node
Before deploying a full cluster, create a "Golden Node" as your baseline.

```bash
cmc pi burn --name node-01 --user admin --key ~/.ssh/id_rsa.pub
```

The tool will detect the USB drive, flash the official Raspberry Pi OS Lite, inject your SSH key, and set the hostname.

---

## Advanced: Cluster Batch Deployment
Use a YAML configuration file to manage large-scale deployments efficiently.

### YAML Configuration Example
Example `cluster.yaml`:
```yaml
defaults:
  prefix: "openclaw"
  range: "00-05,08,10-12"
  username: "admin"
  key_path: "~/.ssh/id_rsa.pub"
  image: "raspios_lite_arm64"
  install_docker: false # Optional: Install Docker Engine (default: false)

nodes:
  node-{range}:
    hostname: "{prefix}-{range}"
    network:
      static_ip: true
      address: "192.168.1.100" # Note: Static IPs must be unique per node
      gateway: "192.168.1.1"
      dns: "8.8.8.8 1.1.1.1"
```

### Batch Burning Workflow
1. Plug in a USB hub with multiple SD cards.
2. Run the burn command:
   ```bash
   cmc pi burn --config cluster.yaml
   ```
3. The system will expand the range, detect all available cards, and burn them sequentially. If you have more nodes than slots, the system will prompt you to swap cards and continue.

### State Persistence
Successfully burned nodes are recorded in `~/.config/cloudmesh/ai/pi_burn_state.json`. If the process is interrupted, running the command again will skip already completed nodes.

---

## Configuration Reference

### Global Defaults (`defaults:`)
| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `prefix` | String | Prefix used for `{prefix}` placeholders | `openclaw` |
| `range` | String | Range of node IDs (e.g., `01-10,15`) | N/A |
| `username` | String | Default system user for all nodes | `admin` |
| `key_path` | Path | Path to the public SSH key to inject | N/A |
| `image` | String | OS image identifier (e.g., `raspios_lite_arm64`) | `raspios_lite_arm64` |
| `install_docker` | Boolean | Whether to install Docker Engine | `false` |

### Node Overrides (`nodes:`)
| Parameter | Type | Description |
|-----------|------|-------------|
| `hostname` | String | Unique hostname for the node. Supports `{prefix}` and `{range}`. |
| `network` | Object | Network settings (see below). |

### Network Settings (`network:`)
| Parameter | Type | Description |
|-----------|------|-------------|
| `static_ip` | Boolean | Enable static IP configuration. |
| `interface` | String | Network interface (e.g., `eth0`, `wlan0`). Default: `eth0`. |
| `address` | String | Static IP address in CIDR notation (e.g., `192.168.1.10/24`). |
| `gateway` | String | Default gateway IP. |
| `dns` | String | Space-separated list of DNS servers. |

---

## Specialized Features

### Pi 3 Bootstrap (Hybrid Boot)
For Raspberry Pi 3 nodes that need to boot from either SD or USB:
```bash
cmc pi burn --bootstrap --name node-01 --user admin --key ~/.ssh/id_rsa.pub
```
This modifies `cmdline.txt` to ensure `rootwait` is enabled, facilitating a reliable transition to USB boot.

### Configuration Visualization
To verify the resolved configuration (including prefix and range expansion) without flashing:
```bash
cmc pi burn --config cluster.yaml --node node-01 --dump
```

---

## Quick Installation (Bootstrap)
If you are on a vanilla Raspberry Pi OS image and need to install the `cmc` toolset quickly (even if `git` is not yet installed), you can use the bootstrap script.

**Recommended (via GitHub Pages):**
```bash
curl -sSL https://cloudmesh-ai.github.io/pi.sh | sh
```

**Alternative (via Raw GitHub):**
```bash
curl -sSLf https://raw.githubusercontent.com/cloudmesh-ai/cloudmesh-ai-pi/main/pi.sh | bash
```

This script will:
1. Install `git` and build essentials.
2. Clone the `cloudmesh-ai-common` and `cloudmesh-ai-pi` repositories.
3. Install the toolset and its dependencies.

---

## Post-Burn Installation
Once the card is flashed and inserted into the Pi, boot the Pi and run the installation command:

```bash
cmc pi install --name node-01
```

### Converting an Existing Pi
If you already have a Raspberry Pi running Raspberry Pi OS Lite, you can convert it into an OpenClaw node without re-flashing:

1. SSH into your existing Pi.
2. Run the installation command:
   ```bash
   cmc pi install --name your-node-name
   ```
This applies all production hardening and installs the OpenClaw agent.

---

## Production Hardening Details
The `install` phase applies the following optimizations:

- Performance:
  - zRAM: Configures 50% RAM compression to reduce disk I/O and protect SD card lifespan.
  - Cgroups: Optimizes kernel memory cgroups for better container/process isolation.
- Security:
  - SSH Lockdown: Disables password authentication and root login.
  - UFW Firewall: Implements a deny-by-default policy, allowing only SSH and OpenClaw agent traffic.
- Resilience:
  - Hardware Watchdog: Enables the Pi's internal watchdog to force a reboot if the system freezes.
  - Log Management: Limits systemd-journald to 100MB to prevent storage exhaustion.
  - Time Sync: Ensures system-wide time synchronization via systemd-timesyncd.

---

## Visual Status Indicators (Onboard LEDs)

The installer uses the onboard LEDs to provide real-time status feedback during the installation process.

| State | ACT LED | PWR LED | Visual Effect | Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Installing** | Rapid Flicker | Solid ON | Heartbeat | Active and progressing |
| **Rebooting** | Alternating | Alternating | Siren | Rebooting in 5 seconds |
| **Success** | Solid OFF | Solid ON | Static | Installation complete; Ready for use |
| **Fault** | Solid ON | Solid ON | Solid Block | Error: Manual check required |

---

## Management and Maintenance

### Resetting Burn State
To clear the record of completed nodes and start a cluster burn from scratch:
```bash
cmc pi reset-burn
```

### Troubleshooting
- Device not detected: Ensure you are running on Linux and have the latest Raspberry Pi Imager installed.
- SSH Connection failed: Verify that the public key provided during the burn phase matches the private key used for connection.

---

## Development

To contribute to the `cloudmesh-ai-pi` tool or test new features, you can check out the development version from Git.

### Installation from Source

1. Clone the repository:
   ```bash
   git clone https://github.com/cloudmesh-ai/cloudmesh-ai-pi.git
   cd cloudmesh-ai-pi
   ```

2. Install in editable mode:
   ```bash
   pip install -e .
   ```

### Running Tests

The project includes a test suite to verify the burner and installer logic. You can run the tests using the provided Makefile:

```bash
make test
```

## Core Dependencies
This project depends on the following core components of the Cloudmesh AI ecosystem:
- [cloudmesh-ai-common](https://github.com/cloudmesh-ai/cloudmesh-ai-common)
- [cloudmesh-ai-cmc](https://github.com/cloudmesh-ai/cloudmesh-ai-cmc)
