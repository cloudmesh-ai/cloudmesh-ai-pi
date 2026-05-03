"""
Pi Installer Logic
==================
Automates the software installation and OS configuration for OpenClaw Pi nodes.
Uses a state-machine approach to handle system reboots and post-install tasks.
"""

import subprocess
import os
import textwrap
import json
import time
import shutil
from typing import List, Optional, Dict, Tuple
from pathlib import Path
from cloudmesh.ai.common.logging import get_logger
from cloudmesh.ai.common.io import console, path_expand
from cloudmesh.ai.pi.logger import InstallLogger
import threading

logger = get_logger("pi_installer")

class PiInstaller:
    """Handles the installation of drivers, tools, and OS configuration on the Pi."""

    STATE_FILE = path_expand("~/.cloudmesh_install_state.json")
    TMP_DIR = "/tmp/cloudmesh"

    def __init__(self, hostname: Optional[str] = None):
        self.hostname = hostname
        # Registry for commands: { phase: [(description, command), ...] }
        self.registry: Dict[str, List[Tuple[str, str]]] = {
            "pre_reboot": [],
            "post_reboot": []
        }
        self.logger = InstallLogger()
        self._heartbeat_stop = threading.Event()
        self._load_defaults()

    def _start_heartbeat(self) -> None:
        """Starts a background thread to flicker the ACT LED."""
        def run():
            self.logger.leds.set_led("pwr", True)
            while not self._heartbeat_stop.is_set():
                self.logger.leds.set_led("act", True)
                threading.Event().wait(0.1)
                self.logger.leds.set_led("act", False)
                threading.Event().wait(0.1)
        
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _load_defaults(self) -> None:
        """Populates the registry with default commands from fixos.txt."""
        self._apply_config_file()

        # Pre-Reboot Phase
        self.add_command(
            "pre_reboot", 
            "Installing base tools and fixing locales",
            """
            sudo apt-get update
            sudo apt-get install -y locales-all git python3-pip python3-pil python3-pyfiglet htop tmux build-essential net-tools avahi-daemon iotop glances
            """
        )
        self.add_command(
            "pre_reboot",
            "Installing Kuman LCD drivers",
            """
            rm -rf LCD-show
            git clone https://github.com/goodtft/LCD-show.git
            chmod +x LCD-show/LCD35-show
            sudo ./LCD-show/LCD35-show
            """
        )
        self.add_command(
            "pre_reboot",
            "Configuring display and framebuffer",
            """
            sudo sh -c "TERM=linux setterm -blank 0 > /dev/tty1"
            sudo sed -i "$ s/$/ fbcon=map:10/" /boot/firmware/cmdline.txt
            sudo usermod -aG video,tty admin
            sudo chmod 666 /dev/tty1
            sudo chmod 666 /dev/fb1
            """
        )
        self.add_command(
            "pre_reboot",
            "Configuring zRAM for performance",
            """
            sudo apt-get install -y zram-tools
            echo "PERCENT=50" | sudo tee /etc/default/zramswap
            sudo systemctl enable zramswap
            sudo systemctl start zramswap
            """
        )
        self.add_command(
            "pre_reboot",
            "Configuring Log Management",
            """
            sudo sed -i 's/#SystemMaxUse=/SystemMaxUse=100M/' /etc/systemd/journald.conf
            sudo sed -i 's/#RuntimeMaxUse=/RuntimeMaxUse=50M/' /etc/systemd/journald.conf
            sudo systemctl restart systemd-journald
            """
        )
        self.add_command(
            "pre_reboot",
            "Configuring Time Synchronization",
            """
            sudo systemctl enable systemd-timesyncd
            sudo systemctl start systemd-timesyncd
            """
        )
        self.add_command(
            "pre_reboot",
            "Optimizing Kernel Cgroups",
            """
            sudo sed -i 's/^$/cgroup_enable=memory cgroup_memory=1/' /boot/firmware/cmdline.txt
            # If the above fails to append correctly, we ensure it's there
            sudo grep -q "cgroup_enable=memory" /boot/firmware/cmdline.txt || echo "cgroup_enable=memory cgroup_memory=1" | sudo tee -a /boot/firmware/cmdline.txt
            """
        )
        if self.hostname:
            self.add_command(
                "pre_reboot",
                f"Setting hostname to {self.hostname}",
                f"""
                sudo hostnamectl set-hostname {self.hostname}
                sudo sed -i 's/$(hostname)/{self.hostname}/g' /etc/hosts
                sudo sed -i 's/$(hostname)/{self.hostname}/g' /etc/hostname
                """
            )
        self.add_command(
            "pre_reboot",
            "Optimizing Swap and running OpenClaw install",
            """
            sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
            sudo dphys-swapfile setup && sudo dphys-swapfile swapon
            curl -fsSL https://openclaw.ai/install.sh | bash
            """
        )
        self.add_command(
            "pre_reboot",
            "Security Hardening: SSH Lockdown",
            """
            sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
            sudo sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
            sudo systemctl restart ssh
            """
        )
        self.add_command(
            "pre_reboot",
            "Security Hardening: UFW Firewall",
            """
            sudo apt-get install -y ufw
            sudo ufw default deny incoming
            sudo ufw default allow outgoing
            sudo ufw allow 22/tcp
            sudo ufw allow 8000/tcp
            sudo ufw --force enable
            """
        )
        self.add_command(
            "pre_reboot",
            "System Resilience: Hardware Watchdog",
            """
            sudo apt-get install -y watchdog
            echo "watchdog_device = /dev/watchdog" | sudo tee -a /etc/watchdog.conf
            sudo systemctl enable watchdog
            sudo systemctl start watchdog
            """
        )
        self.add_command(
            "pre_reboot",
            "Installing Python dependencies",
            "pip install rich numpy Pillow pyfiglet"
        )

        # Post-Reboot Phase
        self.add_command(
            "post_reboot",
            "Verifying display, drivers, and system services",
            """
            if [ -c /dev/fb1 ]; then
                echo "Framebuffer /dev/fb1 is active."
            else
                echo "Error: /dev/fb1 not found."
                exit 1
            fi
            
            if systemctl is-active --quiet avahi-daemon; then
                echo "Avahi daemon is active."
            else
                echo "Warning: Avahi daemon is not active."
            fi
            
            if systemctl is-active --quiet zramswap; then
                echo "zRAM swap is active."
            else
                echo "Warning: zRAM swap is not active."
            fi
            
            if timedatectl status | grep -q "System clock synchronized: yes"; then
                echo "System clock is synchronized."
            else
                echo "Warning: System clock is NOT synchronized."
            fi
            """
        )

    def add_command(self, phase: str, description: str, command: str) -> None:
        """Adds a command to a specific installation phase."""
        if phase not in self.registry:
            raise ValueError(f"Invalid phase: {phase}. Use 'pre_reboot' or 'post_reboot'.")
        self.registry[phase].append((description, command))

    def _apply_config_file(self) -> None:
        """Reads the injected config file and applies settings to the registry."""
        config_path = "/etc/cloudmesh_config.json"
        if not os.path.exists(config_path):
            return

        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            
            # 1. Network Configuration
            network = config.get("network", {})
            if network.get("static_ip"):
                self.set_static_ip(
                    interface=network.get("interface", "eth0"),
                    address=network.get("address"),
                    gateway=network.get("gateway"),
                    dns=network.get("dns")
                )
            
            # 2. Docker Installation
            if config.get("install_docker"):
                username = config.get("username", "admin")
                self.add_command(
                    "pre_reboot",
                    "Installing Docker Engine",
                    f"""
                    curl -fsSL https://get.docker.com -o get-docker.sh
                    sudo sh get-docker.sh
                    sudo usermod -aG docker {username}
                    rm get-docker.sh
                    """
                )
        except Exception as e:
            logger.error(f"Failed to apply config file {config_path}: {e}")

    def set_static_ip(self, interface: str, address: str, gateway: str, dns: Optional[str] = None) -> None:
        """Optionally configures a static IP address and DNS using nmcli."""
        dns_servers = dns if dns else "8.8.8.8 1.1.1.1"
        cmd = textwrap.dedent(f"""
            sudo nmcli con mod "{interface}" ipv4.addresses {address}
            sudo nmcli con mod "{interface}" ipv4.gateway {gateway}
            sudo nmcli con mod "{interface}" ipv4.dns "{dns_servers}"
            sudo nmcli con mod "{interface}" ipv4.method manual
            sudo nmcli con up "{interface}"
        """)
        self.add_command("pre_reboot", f"Configuring static IP for {interface}", cmd)

    def run_cmd(self, command: Optional[str] = None, description: Optional[str] = None, shell: bool = True, *args) -> str:
        """Executes a shell command (supports multiline strings) and returns the output."""
        if command is None and args:
            command = args[0]
        
        if not command:
            raise ValueError("No command provided to run_cmd")

        if description:
            self.logger.info(f"Executing: {description}")

        dedented_cmd = textwrap.dedent(command).strip()
        try:
            result = subprocess.run(
                dedented_cmd, 
                shell=shell, 
                check=True, 
                capture_output=True, 
                text=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {dedented_cmd}\nError: {e.stderr}")
            raise

    def _get_state(self) -> dict:
        """Reads the installation state from the state file."""
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"phase": "PRE_REBOOT"}

    def _set_state(self, phase: str) -> None:
        """Writes the installation state to the state file."""
        with open(self.STATE_FILE, "w") as f:
            json.dump({"phase": phase}, f)

    def _generate_scripts(self, phase: str) -> List[str]:
        """Writes the commands for a phase into .sh files in the tmp directory."""
        if not os.path.exists(self.TMP_DIR):
            os.makedirs(self.TMP_DIR, exist_ok=True)
        
        scripts = []
        for i, (desc, cmd) in enumerate(self.registry[phase]):
            script_path = os.path.join(self.TMP_DIR, f"{i:02d}_{desc.replace(' ', '_').lower()}.sh")
            with open(script_path, "w") as f:
                f.write("#!/bin/bash\n")
                f.write(textwrap.dedent(cmd))
            
            os.chmod(script_path, 0o755)
            scripts.append(script_path)
        
        return scripts

    def _schedule_auto_resume(self) -> None:
        """Schedules the installer to run again after reboot using cron."""
        # We assume the command to run is 'cmc pi install'
        # Note: In a real environment, we'd use the full path to the cme binary
        cron_cmd = "@reboot /usr/bin/cmc pi install"
        try:
            # Use crontab to add the entry
            current_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            if cron_cmd not in current_cron:
                new_cron = current_cron + cron_cmd + "\n"
                subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)
            console.print("[green]Auto-resume scheduled via cron @reboot.[/green]")
        except Exception as e:
            logger.error(f"Failed to schedule auto-resume: {e}")

    def _cleanup_auto_resume(self) -> None:
        """Removes the auto-resume cron job."""
        try:
            current_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            new_cron = "\n".join([line for line in current_cron.splitlines() if "cmc pi install" not in line])
            subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)
            console.print("[green]Auto-resume trigger removed.[/green]")
        except Exception as e:
            logger.error(f"Failed to cleanup auto-resume: {e}")

    def full_install(self) -> None:
        """Orchestrates the installation process across reboots."""
        state = self._get_state()
        phase = state.get("phase", "PRE_REBOOT")

        if phase == "PRE_REBOOT":
            self.logger.info("PHASE 1: PRE-REBOOT SETUP")
            try:
                self._heartbeat_stop.clear()
                self.logger.set_state("heartbeat")
                self._start_heartbeat()
                
                scripts = self._generate_scripts("pre_reboot")
                for script in scripts:
                    desc = os.path.basename(script).replace(".sh", "").replace("_", " ").capitalize()
                    self.run_cmd(f"sudo {script}", description=desc)
                
                self._heartbeat_stop.set()
                self.logger.set_state("siren")
                
                self._set_state("POST_REBOOT")
                self._schedule_auto_resume()
                
                self.logger.info("REBOOT REQUIRED: All pre-reboot tasks complete. System will reboot in 5 seconds...")
                time.sleep(5)
                self.run_cmd("sudo reboot")
            except Exception as e:
                self._heartbeat_stop.set()
                self.logger.set_state("fault")
                self.logger.error(f"Pre-reboot installation failed: {e}")
                raise

        elif phase == "POST_REBOOT":
            self.logger.info("PHASE 2: POST-REBOOT VERIFICATION")
            try:
                self._heartbeat_stop.clear()
                self.logger.set_state("heartbeat")
                self._start_heartbeat()
                
                scripts = self._generate_scripts("post_reboot")
                for script in scripts:
                    desc = os.path.basename(script).replace(".sh", "").replace("_", " ").capitalize()
                    self.run_cmd(f"sudo {script}", description=desc)
                
                self._heartbeat_stop.set()
                self.logger.set_state("success")
                
                self._set_state("COMPLETED")
                self._cleanup_auto_resume()
                
                # Cleanup tmp scripts
                if os.path.exists(self.TMP_DIR):
                    shutil.rmtree(self.TMP_DIR)
                
                self.logger.info("SUCCESS: Pi OS has been fully configured and verified.")
            except Exception as e:
                self._heartbeat_stop.set()
                self.logger.set_state("fault")
                self.logger.error(f"Post-reboot verification failed: {e}")
                raise

        else:
            console.print("[yellow]Installation already completed.[/yellow]")