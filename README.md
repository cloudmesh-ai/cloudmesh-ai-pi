# Cloudmesh AI Pi Burner

The **Cloudmesh AI Pi Burner** is a deployment tool designed to automate the creation of secure, optimized Raspberry Pi environments specifically for **OpenClaw**. 

Instead of manually flashing an image and then SSHing into the device to perform tedious configuration, this tool handles the entire pipeline: from OS flashing and SSH key injection to kernel memory optimization and swap space expansion.

---

## 🚀 Quickstart Guide

Get your OpenClaw node ready in minutes:

1.  **Install the tool**:
    ```bash
    cd cloudmesh-ai-pi
    pip install -e .
    ```

2.  **Prepare your SSH Key**:
    Ensure you have a public SSH key (e.g., `~/.ssh/id_ed25519.pub`).

3.  **Run the Burner**:
    ```bash
    cme pi burn --name claw-node-01 --user admin --key ~/.ssh/id_ed25519.pub
    ```
    *Follow the on-screen prompts to unplug/plug your USB drive and set the system password.*

---

## 📋 Prerequisites

### Hardware
- A Raspberry Pi (compatible with 64-bit OS).
- A USB SSD or SD Card.
- A host machine running **macOS** or **Linux**.

### Software
- **Python 3.8+**
- **Raspberry Pi Imager CLI**: The tool relies on the official RPi Imager CLI for flashing.
    - **macOS**: Install via the official `.dmg` from [raspberrypi.com/software](https://www.raspberrypi.com/software/).
    - **Linux**: Install via the official repository or download the CLI tool.

---

## 🛠 Installation

Clone the repository and install it in editable mode:

```bash
git clone <repository-url>
cd cloudmesh-ai-pi
pip install -e .
```

---

## 📖 User Manual

### The `pi burn` Command

The primary command is `cme pi burn`. It can be used in three different ways:

#### 1. Direct Command Line Arguments
Best for quick deployments.
```bash
cme pi burn --name <hostname> --user <username> --key <path_to_pub_key>
```

#### 2. Using a Configuration File
Best for standardized deployments across multiple nodes.
```bash
cme pi burn --config config.yaml
```

**Example `config.yaml`**:
```yaml
name: "claw-node-01"
user: "admin"
key: "~/.ssh/id_ed25519.pub"
```

#### 3. Interactive Mode
If you omit the required arguments, the tool will guide you through the process:
```bash
cme pi burn
# The tool will prompt you for hostname, username, and SSH key path.
```

### Advanced Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `--image` | Specify the OS image to flash (e.g., `raspios_lite_arm32`). | `raspios_lite_arm64` |
| `--script` | Path to a custom `.sh` script to be injected and run on first boot. | Default OpenClaw script |

**Example with custom image and script**:
```bash
cme pi burn --name node-01 --user admin --key ~/.ssh/id_ed25519.pub --image raspios_lite_arm32 --script my_optimizations.sh
```

---

## ⚙️ How it Works (The Workflow)

The tool follows a strict sequence to ensure the drive is correctly identified and optimized:

1.  **Pre-flight Checks**: Verifies the host OS and ensures `rpi-imager` is installed.
2.  **Device Detection**: 
    -   Prompts you to **unplug** the drive to take a snapshot of current disks.
    -   Prompts you to **plug in** the drive and scans for the new hardware ID.
3.  **Flashing**: Calls the RPi Imager CLI to write the OS, set the hostname, create the user, and inject the SSH key.
4.  **Optimization**:
    -   Mounts the boot partition.
    -   **Cgroups**: Injects `cgroup_enable=memory cgroup_memory=1` into `cmdline.txt` to enable memory limits.
    -   **Swap**: Injects a setup script to expand swap space to 2GB.
    -   **OpenClaw**: Injects the one-touch installer script.
5.  **Cleanup**: Safely ejects the drive and logs the event to `~/.config/cloudmesh/ai/pi_burn_history.json`.

---

## ❓ Troubleshooting

**"Raspberry Pi Imager CLI is not installed"**
Ensure you have installed the official RPi Imager. On macOS, the tool looks for the binary inside `/Applications/Raspberry Pi Imager.app`.

**"Device detection failed"**
Ensure the drive is properly connected and that you followed the unplug/plug sequence exactly as prompted.

**"SSH key not found"**
Verify that the path provided to `--key` is the **public** key (`.pub`), not the private key.

---

## 🧪 Development

### Running Tests
The project includes a comprehensive test suite that mocks system calls to verify logic without needing hardware.

```bash
# Install test dependencies
pip install pytest

# Run tests
pytest tests/test_pi.py
```

### Project Structure
- `src/cloudmesh/ai/pi/burner.py`: Core logic and `OpenClawBurner` class.
- `src/cloudmesh/ai/command/pi.py`: CLI interface and `click` command definitions.
- `tests/`: Unit tests for the burner logic.