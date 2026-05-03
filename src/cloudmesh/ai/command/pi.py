"""
Cloudmesh AI Pi Burner Extension
================================

This extension provides tools to automate the creation of a secure, optimized 
Raspberry Pi environment specifically for OpenClaw. It handles OS flashing, 
SSH key injection, kernel memory optimization (Cgroups), and swap space expansion.

Usage Examples:
-------------------------------------------------------------------------------
1. Burn a Pi image using a config file:
   $ cme pi burn --config config.yaml

2. Burn a Pi image by specifying parameters:
   $ cme pi burn --name claw-node-01 --user admin --key ~/.ssh/id_ed25519.pub

3. Burn with a custom image and script:
   $ cme pi burn --name node-01 --user admin --key ~/.ssh/id_ed25519.pub --image raspios_lite_arm32 --script my_opt.sh

Detailed Workflow:
-------------------------------------------------------------------------------
a. OS Check: Confirms the host is macOS or Linux.
b. Imager Check: Verifies Raspberry Pi Imager CLI is installed.
c. Pre-Plug Scan: Snapshots existing drives to detect the new USB.
d. Detection: Identifies the newly plugged USB/SSD drive.
e. Credentials: Prompts for the system password for the new user.
f. Flashing: Uses RPi Imager CLI to write the OS.
g. Optimization: Mounts the boot partition to inject Cgroup and swap settings.
h. Cleanup: Ejects the drive safely and logs the history.

Usage:
    pi burn [options]
    pi -h | --help

Options:
    --config <path>    Path to a YAML config file containing name, user, and key.
    --name <name>      Hostname for the Pi node.
    --user <user>      Username for the Pi node.
    --key <path>       Path to the public SSH key.
    --image <image>    OS image to use (default: raspios_lite_arm64).
    --script <path>    Path to a custom optimization shell script.
    -h, --help         Show this screen.
-------------------------------------------------------------------------------
"""

import os
import sys
import yaml
import getpass
import click
import ipaddress

from cloudmesh.ai.common.logging import get_logger
from cloudmesh.ai.common.io import console
from cloudmesh.ai.pi.burner import OpenClawBurner, ClusterBurner, BurnStateManager
from cloudmesh.ai.pi.installer import PiInstaller
from cloudmesh.ai.pi.network import NetworkDiscoverer
from rich.table import Table

# Initialize Logger
logger = get_logger("pi")

# --- Click Group and Commands ---

@click.group()
def pi_group():
    """
    OpenClaw Pi Burner - Strict macOS/Linux Deployment Tool.
    """
    pass

@pi_group.command(name="install")
@click.option("--name", help="Hostname for the Pi node.")
def install_cmd(name):
    """
    Install OpenClaw software and configure the OS on the local Pi.
    Note: This command must be run on the Raspberry Pi itself.
    """
    try:
        installer = PiInstaller(hostname=name)
        installer.full_install()
    except Exception as e:
        console.error(f"Installation failed: {e}")

@pi_group.command(name="burn")
@click.option("--config", type=click.Path(exists=True), help="Path to a YAML config file.")
@click.option("--node", help="Node name for YAML config lookup.")
@click.option("--name", help="Hostname for the Pi node.")
@click.option("--user", help="Username for the Pi node.")
@click.option("--key", help="Path to the public SSH key.")
@click.option("--image", default="raspios_lite_arm64", help="OS image to use.")
@click.option("--gui", is_flag=True, help="Launch the Raspberry Pi Imager GUI instead of CLI.")
@click.option("--optimize-only", is_flag=True, help="Skip flashing and only apply optimizations to an existing drive.")
@click.option("--dump", is_flag=True, help="Dump the resolved configuration and exit.")
def burn_cmd(config, node, name, user, key, image, gui, optimize_only, dump):
    """
    Automate the creation of a secure, optimized Raspberry Pi environment.
    Supports single-node burn or cluster-batch burn via --config.
    """
    try:
        if config:
            # Cluster Burn Mode
            cluster_burner = ClusterBurner(config_file=config, node_name=node, image=image)
            
            if dump:
                # For dump, we need a single burner instance to resolve the config
                burner = OpenClawBurner(name, user, key, image=image, config_file=config, node_name=node)
                burner.dump_config()
                return

            if gui:
                # GUI mode is not supported for cluster batching
                console.error("GUI mode is not supported for cluster batch burning. Please use single-node mode.")
                return

            pwd = getpass.getpass("Set password for Pi users: ")
            cluster_burner.run(pwd)
            return

        else:
            # Single Node Mode
            name = name or click.prompt("Enter hostname for the Pi node", default="claw-node-01")
            user = user or click.prompt("Enter username for the Pi node", default="admin")
            key = key or click.prompt("Enter path to the public SSH key")
            burner = OpenClawBurner(name, user, key, image=image)
            
            if dump:
                burner.dump_config()
                return

            if gui:
                console.print("\nLaunching Raspberry Pi Imager GUI...")
                burner.launch_gui()
                console.banner("INFO", "GUI launched. Please flash your drive manually.\nOnce finished, run this command again with --optimize-only to apply OpenClaw tweaks.")
                return

            if not burner._validate_ssh_key():
                return

            if burner.detect_device(pause_callback=click.pause, confirm_callback=click.confirm):
                try:
                    if not optimize_only:
                        pwd = getpass.getpass(f"Set password for Pi user '{burner.username}': ")
                        burner.flash(pwd)
                    else:
                        console.print("\n--- OPTIMIZE ONLY MODE ---")
                        console.print("Skipping flashing step...")
                    
                    burner.cleanup()
                except Exception as e:
                    console.error(f"An error occurred during the burn process: {e}")
            else:
                console.error("Device detection failed. Aborting.")
    except SystemExit:
        raise
    except Exception as e:
        console.error(f"An error occurred: {e}")

@pi_group.group(name="discover")
def discover_group():
    """
    Discover devices connected to the Pi.
    """
    pass

@discover_group.command(name="net")
@click.option("--subnet", default="192.168.50.0/24", help="Subnet to scan (e.g. 192.168.50.0/24).")
@click.option("--deep", is_flag=True, help="Perform a deep scan to find hostnames from service banners.")
def discover_net(subnet, deep):
    """
    Discover devices on the local network using nmap.
    """
    try:
        discoverer = NetworkDiscoverer(subnet=subnet)
        devices = discoverer.discover(deep=deep)
        
        if not devices:
            console.print("No devices discovered.")
            return

        # Sort devices by IP address numerically
        try:
            devices.sort(key=lambda x: ipaddress.ip_address(x["ip"]))
        except Exception:
            # Fallback to string sort if IP is invalid
            devices.sort(key=lambda x: x["ip"])

        table = Table(title=f"Network Discovery Results ({subnet})", show_lines=True)
        table.add_column("Hostname", style="blue")
        table.add_column("IP Address", style="cyan")
        table.add_column("MAC Address", style="magenta")
        table.add_column("Vendor", style="green")

        for device in devices:
            table.add_row(device["hostname"], device["ip"], device["mac"], device["vendor"])

        console.print(table)
    except Exception as e:
        console.error(f"Network discovery failed: {e}")

@discover_group.command(name="usb")
def discover_usb():
    """
    Discover USB devices connected to the Pi.
    """
    from cloudmesh.ai.pi.findusb import find_usb_devices
    try:
        devices = find_usb_devices()
        if not devices:
            console.print("No USB devices discovered.")
            return

        table = Table(title="USB Device Discovery Results", show_lines=True)
        table.add_column("Device", style="blue")
        table.add_column("USB ID", style="cyan")
        table.add_column("Vendor", style="green")
        table.add_column("Product", style="magenta")
        table.add_column("Serial", style="yellow")
        table.add_column("Size", style="white")
        table.add_column("Bus/Dev", style="dim")

        for dev in devices:
            table.add_row(
                dev.get("model", "Unknown"),
                dev.get("usb_id", "Unknown"),
                dev.get("vendor", "Unknown"),
                dev.get("product", "Unknown"),
                dev.get("serial", "Unknown"),
                dev.get("size", "Unknown"),
                f"{dev.get('bus', 'U')}/{dev.get('device', 'U')}"
            )
        console.print(table)
    except Exception as e:
        console.error(f"USB discovery failed: {e}")

@pi_group.command(name="reset-burn")
def reset_burn_cmd():
    """
    Reset the cluster burn state. Clears the list of completed nodes.
    """
    try:
        BurnStateManager().reset()
        console.banner("SUCCESS", "Cluster burn state has been reset.")
    except Exception as e:
        console.error(f"Failed to reset burn state: {e}")

def register():
    """
    Registers the pi command group with the CME framework.
    """
    return pi_group
