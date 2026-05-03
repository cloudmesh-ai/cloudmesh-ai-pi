"""
OpenClaw Pi Burner Core Logic
============================
Linux-only version for automated OS flashing and optimization.
"""

import os
import subprocess
import sys
import platform
import time
import shutil
import tempfile
import json
import textwrap
import yaml
from typing import List, Set, Optional, Dict, Any, Tuple
from pathlib import Path

from cloudmesh.ai.common.logging import get_logger
from cloudmesh.ai.pi.findusb import USBFinder
from cloudmesh.ai.common.io import console, path_expand

# Initialize Logger
logger = get_logger("pi")

class BurnStateManager:
    """Handles persistence of the cluster burn state."""
    STATE_FILE = path_expand("~/.config/cloudmesh/ai/pi_burn_state.json")

    def __init__(self):
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"completed_nodes": []}

    def mark_completed(self, node_name: str):
        if node_name not in self.state["completed_nodes"]:
            self.state["completed_nodes"].append(node_name)
            self._save()

    def is_completed(self, node_name: str) -> bool:
        return node_name in self.state["completed_nodes"]

    def reset(self):
        self.state = {"completed_nodes": []}
        self._save()

    def _save(self):
        Path(self.STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(self.STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

class ClusterBurner:
    """Orchestrates the batch burning of multiple Pi nodes."""
    
    def __init__(self, config_file: str, node_name: Optional[str] = None, 
                 image: str = "raspios_lite_arm64", prefix: str = "openclaw"):
        self.config_file = path_expand(config_file)
        self.node_name = node_name
        self.image = image
        self.prefix = prefix
        self.state_manager = BurnStateManager()
        
        # Load full config to determine the node list
        with open(self.config_file, "r") as f:
            self.full_config = yaml.safe_load(f) or {}
        
        self.defaults = self.full_config.get("defaults", {})
        self.nodes_config = self.full_config.get("nodes", {})
        self.range_def = self.defaults.get("range", "")

    def _get_all_nodes(self) -> List[str]:
        """Expands the YAML config into a full list of node names."""
        nodes = []
        # Add explicit nodes
        for k in self.nodes_config.keys():
            if "{range}" not in k:
                nodes.append(k)
        
        # Expand range templates
        if self.range_def:
            # We use a temporary burner to leverage its _parse_range logic
            temp_burner = OpenClawBurner("tmp", "tmp", "tmp")
            resolved_range = temp_burner._parse_range(self.range_def)
            
            for k in self.nodes_config.keys():
                if "{range}" in k:
                    for r in resolved_range:
                        nodes.append(k.replace("{range}", r))
        
        return sorted(list(set(nodes)))

    def run(self, password: str):
        """Main loop for batch burning."""
        all_nodes = self._get_all_nodes()
        
        # If a specific node was requested, only burn that one
        pending_nodes = [n for n in all_nodes if self.node_name is None or n == self.node_name]
        pending_nodes = [n for n in pending_nodes if not self.state_manager.is_completed(n)]
        
        if not pending_nodes:
            console.banner("COMPLETE", "All nodes in the configuration have already been burned.")
            return

        console.banner("CLUSTER BURN START", f"Pending Nodes: {len(pending_nodes)}")
        
        while pending_nodes:
            # 1. Detect all available devices
            # We create a burner just to use the detection logic
            detector = OpenClawBurner("tmp", "tmp", "tmp")
            available_devices = detector.detect_all_devices()
            
            if not available_devices:
                console.error("No suitable USB/SD cards detected.")
                if click.confirm("Would you like to try scanning again?"):
                    continue
                else:
                    break

            console.print(f"\nFound {len(available_devices)} available slots. Processing next batch...")
            
            # 2. Match devices to nodes
            batch = pending_nodes[:len(available_devices)]
            for i, node_name in enumerate(batch):
                device_id = available_devices[i]
                console.banner(f"BURNING NODE: {node_name}", f"Using Device: {device_id}")
                
                try:
                    # Create a specific burner for this node
                    burner = OpenClawBurner(
                        hostname="", username="", key_path="", 
                        image=self.image, config_file=self.config_file, 
                        node_name=node_name, prefix=self.prefix
                    )
                    burner.disk_id = device_id
                    burner.flash(password)
                    burner.cleanup()
                    
                    self.state_manager.mark_completed(node_name)
                    console.print(f"[bold green]Successfully burned {node_name}[/bold green]")
                except Exception as e:
                    console.error(f"Failed to burn {node_name} on {device_id}: {e}")
                    # We don't mark as completed, so it stays in pending_nodes
            
            # Remove processed nodes from pending list
            # Only remove if they were actually marked completed
            pending_nodes = [n for n in all_nodes if not self.state_manager.is_completed(n)]
            
            if pending_nodes:
                console.banner("BATCH COMPLETE", f"{len(pending_nodes)} nodes still remaining.")
                if click.confirm("Please swap the SD cards and press Enter to continue..."):
                    continue
                else:
                    break

        console.banner("CLUSTER BURN FINISHED", "All requested nodes have been processed.")

class OpenClawBurner:
    SUPPORTED_SYSTEMS = ["Linux"]
    
    # Mapping of image identifiers to official download URLs
    IMAGE_MAP = {
        "raspios_lite_arm64": "https://downloads.raspberrypi.org/raspios_lite_arm64.img.xz",
        "raspios_lite_arm32": "https://downloads.raspberrypi.org/raspios_lite_arm32.img.xz",
        "raspios_full_arm64": "https://downloads.raspberrypi.org/raspios_full_arm64.img.xz",
        "raspios_full_arm32": "https://downloads.raspberrypi.org/raspios_full_arm32.img.xz",
    }

    def __init__(self, hostname: str, username: str, key_path: str, 
                 image: str = "raspios_lite_arm64",
                 config_file: Optional[str] = None,
                 node_name: Optional[str] = None,
                 prefix: str = "openclaw",
                 bootstrap: bool = False):
        self.system: str = platform.system()
        self._check_os_support()
        self._verify_imager_installed()
        self.prefix: str = prefix
        self.bootstrap: bool = bootstrap
        
        # Load YAML config if provided
        self.config: Dict[str, Any] = {}
        if config_file:
            self.config = self._load_config(path_expand(config_file), node_name)
        
        # Merge YAML with CLI parameters (CLI takes precedence)
        self.hostname: str = hostname or self.config.get("hostname", f"{self.prefix}-node")
        self.username: str = username or self.config.get("username", "admin")
        self.key_path: str = path_expand(key_path or self.config.get("key_path", "~/.ssh/id_rsa.pub"))
        self.image: str = image or self.config.get("image", "raspios_lite_arm64")
        
        self.disk_id: Optional[str] = None
        self.usb_finder = USBFinder()

    def _check_os_support(self) -> None:
        """Strictly enforces Linux compatibility."""
        if self.system not in self.SUPPORTED_SYSTEMS:
            console.error(f"FATAL: {self.system} is not supported. This burner requires Linux.")
            sys.exit(1)

    def _get_imager_version(self) -> Optional[str]:
        """Attempts to retrieve the Raspberry Pi Imager version."""
        imager = "rpi-imager"
        try:
            output = subprocess.check_output([imager, "--version"], text=True, stderr=subprocess.STDOUT)
            for line in output.splitlines():
                if "v" in line:
                    return line.split("v")[-1].strip()
        except Exception:
            return None
        return None

    def _verify_imager_installed(self) -> None:
        """Checks if Raspberry Pi Imager is installed and meets version requirements."""
        imager = "rpi-imager"
        if shutil.which(imager) is None:
            console.error("Raspberry Pi Imager is not installed.")
            console.print("\nTo install it, please download the official RPi Imager:")
            console.banner("Installation", "Visit https://www.raspberrypi.com/software/")
            sys.exit(1)

        version_str = self._get_imager_version()
        if version_str:
            try:
                version_tuple = tuple(map(int, version_str.split('.')))
                if version_tuple < (2, 0, 7):
                    console.warn(f"Detected Raspberry Pi Imager v{version_str}. CLI flashing requires v2.0.7 or higher.")
                    console.banner("SUGGESTION", "Please update your Imager or use the GUI mode:\ncmc pi burn --gui")
            except ValueError:
                pass

    def launch_gui(self) -> None:
        """Launches the Raspberry Pi Imager GUI."""
        subprocess.run(["rpi-imager"], check=True)

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

    def _print_device_card(self, info: dict) -> None:
        """Prints a visually appealing device information card with deep USB metadata in a 2-column format."""
        console.banner("TARGET DEVICE IDENTIFIED", "")
        
        basic_info = [
            ("Device ID", info['id']),
            ("Capacity", info['size']),
            ("Protocol", info['protocol']),
            ("Type", info['type']),
        ]
        for label, val in basic_info:
            console.print(f"  [bold]{label:<12}:[/bold] {val}")
        
        console.print("")
        console.print("  [bold]USB Metadata:[/bold]")
        
        usb_info = [
            ("Vendor Name", info.get('vendor', 'Unknown')),
            ("Product Name", info.get('product', 'Unknown')),
            ("Model/Name", info['model'] if info['model'] != 'Unknown' else info['name']),
        ]
        
        ioreg_keys = {
            "USB Product Name": "usb_product_name",
            "USB Vendor Name": "usb_vendor_name",
            "kUSBProductString": "usb_product_string",
            "kUSBVendorString": "usb_vendor_string"
        }
        for label, key in ioreg_keys.items():
            val = info.get(key)
            if val and val != "Unknown":
                usb_info.append((label, val))
        
        for label, val in usb_info:
            console.print(f"    [cyan]{label:<15}:[/cyan] {val}")
        
        console.print("")

    def detect_all_devices(self) -> List[str]:
        """Detects all suitable external drives currently connected."""
        existing = self.usb_finder.get_external_drives()
        candidates = []
        for d in existing:
            info = self.usb_finder.get_device_info(d)
            size_bytes = info.get("size_bytes", 0)
            # Consider it a candidate if it's in a reasonable range for a Pi OS image
            if (4 * 1024**3) <= size_bytes <= (2 * 1024**4):
                candidates.append(d)
        return candidates

    def detect_device(self, pause_callback, confirm_callback) -> bool:
        """Legacy single-device detection flow."""
        console.banner("STEP 1: DEVICE DETECTION", "")
        
        def print_device_table(drives: Set[str]):
            if not drives:
                return
            
            for d in sorted(list(drives)):
                info = self.usb_finder.get_device_info(d)
                size_bytes = info.get("size_bytes", 0)
                is_strong = (54 * 1024**3) <= size_bytes <= (74 * 1024**3)
                status = "[bold green]Strong Candidate[/bold green]" if is_strong else "Candidate"
                
                console.print(f"[bold cyan]Device: {d}[/bold cyan]")
                console.print("-" * 30)
                
                attrs = [
                    ("Device ID", d),
                    ("Vendor", info.get('vendor', 'Unknown')),
                    ("Product", info.get('product', 'Unknown')),
                    ("Size", info['size']),
                    ("Status", status),
                ]
                
                ioreg_map = {
                    "usb_product_name": "USB Product Name",
                    "usb_vendor_name": "USB Vendor Name",
                    "usb_product_string": "kUSBProductString",
                    "usb_vendor_string": "kUSBVendorString"
                }
                for internal_key, label in ioreg_map.items():
                    val = info.get(internal_key)
                    if val and val != "Unknown":
                        attrs.append((label, val))
                
                for attr, val in attrs:
                    console.print(f"{attr:<18} : {val}")
                
                console.print("-" * 30)
                console.print("")

        existing = self.usb_finder.get_external_drives()
        if existing:
            console.print(f"Found {len(existing)} external drive(s) already connected.")
            console.print("")
            print_device_table(existing)
            
            if confirm_callback("One of these is my target device?"):
                import click
                self.disk_id = click.prompt("Enter the Device ID to use (e.g. /dev/sdb)", type=str)
                if self.disk_id in existing:
                    info = self.usb_finder.get_device_info(self.disk_id)
                    self._print_device_card(info)
                    return True
                else:
                    console.error(f"Invalid Device ID: {self.disk_id}")

        console.print("\nStarting automated detection flow...")
        console.print("Please UNPLUG your target USB/SSD drive.")
        pause_callback("Press any key once the drive is removed...")
        before = self.usb_finder.get_external_drives()

        console.print("\nAction: Now PLUG IN the USB/SSD drive.")
        with console.status("Scanning for new hardware..."):
            for _ in range(15):
                time.sleep(1)
                after = self.usb_finder.get_external_drives()
                diff = after - before
                if diff:
                    candidates = list(diff)
                    strong_candidates = [d for d in candidates if (54 * 1024**3) <= self.usb_finder.get_device_info(d).get("size_bytes", 0) <= (74 * 1024**3)]
                    self.disk_id = strong_candidates[0] if strong_candidates else candidates[0]
                    
                    info = self.usb_finder.get_device_info(self.disk_id)
                    self._print_device_card(info)
                    
                    if not confirm_callback(f"Is this the correct device to flash?"):
                        console.warn("User cancelled. Aborting.")
                        return False
                    return True
        console.error("Error: No new device detected.")
        return False

    def _resolve_image_path(self) -> str:
        """Resolves image identifier to a local path or official URL."""
        if os.path.exists(self.image):
            return self.image
        if self.image in self.IMAGE_MAP:
            return self.IMAGE_MAP[self.image]
        return self.image

    def _parse_range(self, range_str: str) -> List[str]:
        """Parses range strings like '00-01,04,06-09' into ['00', '01', '04', '06', '07', '08', '09']."""
        result = []
        for part in range_str.split(','):
            if '-' in part:
                try:
                    start, end = part.split('-')
                    # Preserve leading zeros by calculating length
                    length = len(start)
                    for i in range(int(start), int(end) + 1):
                        result.append(str(i).zfill(length))
                except ValueError:
                    result.append(part)
            else:
                result.append(part)
        return result

    def _replace_placeholders(self, data: Any, prefix: str, range_val: Optional[str] = None) -> Any:
        """Recursively replaces {prefix} and {range} in strings within the config data."""
        if isinstance(data, str):
            val = data.replace("{prefix}", prefix)
            if range_val:
                val = val.replace("{range}", range_val)
            return val
        elif isinstance(data, dict):
            return {k: self._replace_placeholders(v, prefix, range_val) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_placeholders(i, prefix, range_val) for i in data]
        return data

    def _load_config(self, path: str, node_name: Optional[str]) -> Dict[str, Any]:
        """Loads and merges YAML configuration, resolving placeholders and ranges."""
        try:
            with open(path, "r") as f:
                full_config = yaml.safe_load(f) or {}
            
            defaults = full_config.get("defaults", {})
            resolved_prefix = defaults.get("prefix", self.prefix)
            range_def = defaults.get("range", "")
            
            # 1. Resolve {prefix} globally first
            full_config = self._replace_placeholders(full_config, resolved_prefix)
            
            nodes = full_config.get("nodes", {})
            merged = defaults.copy()
            merged.pop("network", None)
            
            # 2. Handle Node Selection (Direct match or Range match)
            if node_name:
                # Direct match
                if node_name in nodes:
                    merged.update(nodes[node_name])
                else:
                    # Range match: check if node_name matches a template like 'node-{range}'
                    for template_key, config in nodes.items():
                        if "{range}" in template_key:
                            # Extract the potential range value from the node_name
                            # e.g., if template is 'node-{range}' and node_name is 'node-04', range_val is '04'
                            prefix_part = template_key.split("{range}")[0]
                            suffix_part = template_key.split("{range}")[1]
                            
                            if node_name.startswith(prefix_part) and node_name.endswith(suffix_part):
                                range_val = node_name[len(prefix_part):len(node_name)-len(suffix_part)]
                                if range_val in self._parse_range(range_def):
                                    # Found a match! Use this config and resolve {range} placeholders
                                    node_config = self._replace_placeholders(config, resolved_prefix, range_val)
                                    merged.update(node_config)
                                    break
            
            return merged
        except Exception as e:
            console.warn(f"Could not load config file {path}: {e}. Using CLI defaults.")
            return {}

    def _generate_cloud_init(self, password: str) -> str:
        """Generates a cloud-config user-data file for OS customization."""
        try:
            ssh_key = Path(self.key_path).read_text().strip()
        except Exception:
            ssh_key = ""

        # Prepare extra config for the installer
        extra_config = self.config.copy()
        extra_config.update({
            "hostname": self.hostname,
            "username": self.username
        })
        config_json = json.dumps(extra_config, indent=2)

        cloud_config = textwrap.dedent(f"""\
            #cloud-config
            hostname: {self.hostname}
            users:
              - name: {self.username}
                passwd: {password}
                shell: /bin/bash
                sudo: ALL=(ALL) NOPASSWD:ALL
                ssh_authorized_keys:
                  - {ssh_key}
            chpasswd:
              list: |
                {self.username}:{password}
              expire: False
            write_files:
              - path: /etc/cloudmesh_config.json
                content: |
                    {config_json}
                permissions: '0644'
        """).strip()
        tmp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.yaml')
        tmp_file.write(cloud_config)
        tmp_file.close()
        return tmp_file.name

    def _configure_bootstrap(self) -> None:
        """Configures the SD card to allow flexible booting (SD or USB) for Pi 3."""
        console.print("[bold yellow]Configuring Bootstrap for Pi 3 (USB/SD Hybrid Boot)...[/bold yellow]")
        
        # The boot partition is usually the first partition
        boot_partition = f"{self.disk_id}1"
        mount_point = f"/tmp/pi_boot_{self.disk_id.replace('/', '_')}"
        
        try:
            os.makedirs(mount_point, exist_ok=True)
            self.run_cmd(["mount", boot_partition, mount_point], use_sudo=True)
            
            cmdline_path = os.path.join(mount_point, "cmdline.txt")
            if os.path.exists(cmdline_path):
                with open(cmdline_path, "r") as f:
                    content = f.read()
                
                # To allow USB boot on Pi 3, we ensure rootwait is present 
                # and we can add a hint for the bootloader.
                # A common trick is to use 'root=/dev/sda2' for USB or 'root=/dev/mmcblk0p2' for SD.
                # We will ensure it's set to a flexible state or add a comment.
                if "rootwait" not in content:
                    content += " rootwait"
                
                with open(cmdline_path, "w") as f:
                    f.write(content)
                console.print("  - Updated cmdline.txt for hybrid boot.")
            
            self.run_cmd(["umount", mount_point], use_sudo=True)
        except Exception as e:
            console.error(f"Bootstrap configuration failed: {e}")
        finally:
            shutil.rmtree(mount_point, ignore_errors=True)

    def flash(self, password: str) -> None:
        console.banner("STEP 2: FLASHING OS", "")
        imager = "rpi-imager"
        
        userdata_path = self._generate_cloud_init(password)
        resolved_image = self._resolve_image_path()
        cmd = [
            imager, 
            "--cli", 
            "--cloudinit-userdata", userdata_path,
            resolved_image, 
            self.disk_id
        ]
        
        full_cmd = "sudo " + " ".join(cmd) if os.geteuid() != 0 else " ".join(cmd)
        console.print(f"Executing command: {full_cmd}")
        
        try:
            self.run_cmd(cmd, use_sudo=True)
            
            if self.bootstrap:
                self._configure_bootstrap()
                
        except subprocess.CalledProcessError as e:
            console.error(f"Flashing failed: {e}")
            raise
        finally:
            if os.path.exists(userdata_path):
                os.remove(userdata_path)

    def dump_config(self) -> None:
        """Prints the resolved configuration for the current node."""
        console.banner("RESOLVED CONFIGURATION", "")
        
        # Show the merged config that will be used
        final_config = {
            "hostname": self.hostname,
            "username": self.username,
            "image": self.image,
            "key_path": self.key_path,
            "extra_config": self.config
        }
        
        console.print(f"[bold cyan]Node Name:[/bold cyan] {self.hostname}")
        console.print(f"[bold cyan]Username:[/bold cyan] {self.username}")
        console.print(f"[bold cyan]Image:[/bold cyan] {self.image}")
        console.print(f"[bold cyan]SSH Key:[/bold cyan] {self.key_path}")
        
        if self.config:
            console.print("\n[bold]Additional Configuration (Injected into Pi):[/bold]")
            console.print(yaml.dump(self.config, default_flow_style=False))
        else:
            console.print("\n[yellow]No additional YAML configuration provided.[/yellow]")
        
        console.print("")

    def cleanup(self) -> None:
        self.run_cmd(["eject", self.disk_id], use_sudo=True)
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