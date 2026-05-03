"""
OpenClaw Pi Burner Core Logic
============================
"""

import os
import subprocess
import sys
import platform
import time
import shutil
import tempfile
import json
from typing import List, Set, Optional
from pathlib import Path

from cloudmesh.ai.common.logging import get_logger
from cloudmesh.ai.common.io import console, path_expand

# Initialize Logger
logger = get_logger("pi")

class OpenClawBurner:
    SUPPORTED_SYSTEMS = ["Darwin", "Linux"]

    def __init__(self, hostname: str, username: str, key_path: str, 
                 image: str = "raspios_lite_arm64", 
                 custom_script: Optional[str] = None):
        self.system: str = platform.system()
        self._check_os_support()
        self._verify_imager_installed()
        
        self.hostname: str = hostname
        self.username: str = username
        self.key_path: str = path_expand(key_path)
        self.image: str = image
        self.custom_script: Optional[str] = path_expand(custom_script) if custom_script else None
        
        self.disk_id: Optional[str] = None
        self.boot_path: Optional[str] = None

    def _check_os_support(self) -> None:
        """Strictly enforces macOS or Linux compatibility."""
        if self.system not in self.SUPPORTED_SYSTEMS:
            console.error(f"FATAL: {self.system} is not supported. Use macOS or Linux.")
            sys.exit(1)

    def _verify_imager_installed(self) -> None:
        """Checks if Raspberry Pi Imager CLI is installed."""
        imager = "rpi-imager" if self.system == "Linux" else "/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager"
        if shutil.which(imager) is None and not os.path.exists(imager):
            console.error("Raspberry Pi Imager CLI is not installed.")
            console.print("\nTo install it, please download the official RPi Imager:")
            console.banner("Installation", "Visit https://www.raspberrypi.com/software/")
            sys.exit(1)

    def _validate_ssh_key(self) -> bool:
        """Verifies the SSH public key file exists and is not empty."""
        p = Path(self.key_path)
        if not p.exists() or p.stat().st_size == 0:
            console.error(f"SSH key not found or empty at: {self.key_path}")
            return False
        return True

    def run_cmd(self, cmd: List[str], use_sudo: bool = False) -> None:
        if use_sudo and os.geteuid() != 0:
            cmd = ["sudo"] + cmd
        subprocess.run(cmd, check=True)

    def get_external_drives(self) -> Set[str]:
        if self.system == "Darwin":
            output = subprocess.check_output(["diskutil", "list", "external", "physical"], text=True)
            return {line.split()[0] for line in output.splitlines() if line.startswith("/dev/disk")}
        else:
            output = subprocess.check_output(["lsblk", "-dno", "NAME"], text=True)
            return {f"/dev/{line.strip()}" for line in output.splitlines() if line.strip()}

    def detect_device(self, pause_callback) -> bool:
        console.print("\n--- STEP 1: DEVICE DETECTION ---")
        console.print("Please UNPLUG your target USB/SSD drive.")
        pause_callback("Press any key once the drive is removed...")
        before = self.get_external_drives()

        console.print("\nAction: Now PLUG IN the USB/SSD drive.")
        with console.status("Scanning for new hardware..."):
            for _ in range(15):
                time.sleep(1)
                after = self.get_external_drives()
                diff = after - before
                if diff:
                    self.disk_id = list(diff)[0]
                    console.print(f"TARGET IDENTIFIED: {self.disk_id}")
                    return True
        console.error("Error: No new device detected.")
        return False

    def flash(self, password: str) -> None:
        console.print("\n--- STEP 2: FLASHING OS ---")
        imager = "rpi-imager" if self.system == "Linux" else "/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager"
        
        try:
            self.run_cmd([
                imager, "--cli", "--cli-image", self.image,
                "--cli-dst", self.disk_id, "--cli-hostname", self.hostname,
                "--cli-username", self.username, "--cli-password", password,
                "--cli-ssh-key", self.key_path
            ], use_sudo=True)
        except subprocess.CalledProcessError as e:
            console.error(f"Flashing failed: {e}")
            raise

    def apply_optimizations(self) -> None:
        console.print("\n--- STEP 3: APPLYING KERNEL & SWAP TWEAKS ---")
        # Mount Logic
        if self.system == "Darwin":
            self.run_cmd(["diskutil", "mount", f"{self.disk_id}s1"])
            self.boot_path = "/Volumes/bootfs"
        else:
            self.boot_path = tempfile.mkdtemp(prefix="pi_boot_")
            self.run_cmd(["mount", f"{self.disk_id}1", self.boot_path], use_sudo=True)

        # Cgroup Memory Injection
        cmdline = os.path.join(self.boot_path, "cmdline.txt")
        try:
            if os.path.exists(cmdline):
                # Backup original
                shutil.copy2(cmdline, f"{cmdline}.bak")
                
                with open(cmdline, "r") as f:
                    content = f.read().strip()
                if "cgroup_enable=memory" not in content:
                    with open("temp_txt", "w") as f:
                        f.write(content + " cgroup_enable=memory cgroup_memory=1\n")
                    self.run_cmd(["mv", "temp_txt", cmdline], use_sudo=True)
        except Exception as e:
            console.error(f"Failed to optimize cmdline.txt: {e}")

        # Optimization Script
        if self.custom_script and os.path.exists(self.custom_script):
            setup_script_content = Path(self.custom_script).read_text()
        else:
            setup_script_content = """#!/bin/bash
echo "Optimizing Pi for OpenClaw..."
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup && sudo dphys-swapfile swapon
curl -fsSL https://openclaw.ai/install.sh | bash
"""
        setup_file = os.path.join(self.boot_path, "setup_openclaw.sh")
        try:
            with open("temp_sh", "w") as f: 
                f.write(setup_script_content)
            self.run_cmd(["mv", "temp_sh", setup_file], use_sudo=True)
            self.run_cmd(["chmod", "+x", setup_file], use_sudo=True)
        except Exception as e:
            console.error(f"Failed to create setup script: {e}")

    def cleanup(self) -> None:
        if self.system == "Darwin":
            self.run_cmd(["diskutil", "eject", self.disk_id])
        else:
            if self.boot_path:
                self.run_cmd(["umount", self.boot_path], use_sudo=True)
                shutil.rmtree(self.boot_path)
        
        console.banner("SUCCESS", f"OpenClaw Node Prepared.\nSSH Command: ssh {self.username}@{self.hostname}.local")
        self.save_history()

    def save_history(self) -> None:
        """Logs the burn event to a local JSON file."""
        history_file = Path(path_expand("~/.config/cloudmesh/ai/pi_burn_history.json"))
        history_file.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": self.hostname,
            "username": self.username,
            "image": self.image,
            "disk": self.disk_id
        }
        
        history = []
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                pass
        
        history.append(entry)
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)