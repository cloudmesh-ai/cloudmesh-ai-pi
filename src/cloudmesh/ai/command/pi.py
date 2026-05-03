he"""
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

from cloudmesh.ai.common.logging import get_logger
from cloudmesh.ai.common.io import console
from cloudmesh.ai.pi.burner import OpenClawBurner

# Initialize Logger
logger = get_logger("pi")

# --- Click Group and Commands ---

@click.group()
def pi_group():
    """
    OpenClaw Pi Burner - Strict macOS/Linux Deployment Tool.
    """
    pass

@pi_group.command(name="burn")
@click.option("--config", type=click.Path(exists=True), help="Path to a YAML config file.")
@click.option("--name", help="Hostname for the Pi node.")
@click.option("--user", help="Username for the Pi node.")
@click.option("--key", help="Path to the public SSH key.")
@click.option("--image", default="raspios_lite_arm64", help="OS image to use.")
@click.option("--script", type=click.Path(exists=True), help="Path to a custom optimization script.")
def burn_cmd(config, name, user, key, image, script):
    """
    Automate the creation of a secure, optimized Raspberry Pi environment.
    """
    if config:
        with open(config, "r") as f:
            c = yaml.safe_load(f)
        burner = OpenClawBurner(c['name'], c['user'], c['key'], image=image, custom_script=script)
    else:
        # Interactive mode for missing parameters
        name = name or click.prompt("Enter hostname for the Pi node", default="claw-node-01")
        user = user or click.prompt("Enter username for the Pi node", default="admin")
        key = key or click.prompt("Enter path to the public SSH key")
        burner = OpenClawBurner(name, user, key, image=image, custom_script=script)

    if not burner._validate_ssh_key():
        return

    if burner.detect_device(pause_callback=click.pause):
        pwd = getpass.getpass(f"Set password for Pi user '{burner.username}': ")
        try:
            burner.flash(pwd)
            burner.apply_optimizations()
            burner.cleanup()
        except Exception as e:
            console.error(f"An error occurred during the burn process: {e}")
    else:
        console.error("Device detection failed. Aborting.")

def register():
    """
    Registers the pi command group with the CME framework.
    """
    return pi_group