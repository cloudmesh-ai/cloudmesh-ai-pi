"""
USB discovery for Raspberry Pi (Linux).
"""
import os
import subprocess
import re
from typing import Set, Dict, Any
from cloudmesh.ai.pi.base import USBFinderBase
from cloudmesh.ai.common.logging import get_logger

logger = get_logger("raspbian_finder")

class RaspbianFinder(USBFinderBase):
    """USB discovery for Raspberry Pi (Linux)."""
    def get_external_drives(self) -> Set[str]:
        try:
            output = subprocess.check_output(["lsblk", "-dno", "NAME"], text=True)
            return {f"/dev/{line.strip()}" for line in output.splitlines() if line.strip()}
        except Exception as e:
            logger.error(f"Error detecting drives on Linux: {e}")
            return set()

    def get_device_info(self, disk_id: str) -> Dict[str, Any]:
        info = {
            "id": disk_id, "name": "Unknown", "size": "Unknown", "size_bytes": 0,
            "model": "Unknown", "protocol": "Unknown", "type": "Unknown",
            "vendor": "Unknown", "product": "Unknown", "idVendor": "Unknown",
            "idProduct": "Unknown", "serial": "Unknown", "bus": "Unknown",
            "device": "Unknown", "usb_id": "Unknown", "mountpoint": "Unknown",
            "label": "Unknown", "uuid": "Unknown"
        }
        try:
            import json
            # 1. Use lsblk --json for reliable parsing
            # -b for bytes, -o for specific columns
            output = subprocess.check_output(
                ["lsblk", "--json", "-b", "-o", "MODEL,SIZE,TRAN,MOUNTPOINT", disk_id], 
                text=True
            )
            data = json.loads(output)
            
            if "blockdevices" in data and len(data["blockdevices"]) > 0:
                dev = data["blockdevices"][0]
                info["model"] = dev.get("model") or "Unknown"
                
                bytes_size = dev.get("size")
                if bytes_size:
                    try:
                        bytes_size = int(bytes_size)
                        info["size_bytes"] = bytes_size
                        info["size"] = f"{bytes_size // (1024**3)} GB" if bytes_size >= 1024**3 else f"{bytes_size // (1024**2)} MB"
                    except ValueError:
                        info["size"] = str(bytes_size)
                
                info["protocol"] = dev.get("tran") or "Unknown"
                info["mountpoint"] = dev.get("mountpoint") or "Unknown"
                
                # Try to get Label and UUID from lsblk JSON if available
                info["label"] = dev.get("label") or info["label"]
                info["uuid"] = dev.get("uuid") or info["uuid"]
            else:
                # Fallback if JSON doesn't return the device
                return info
            info["type"] = "USB/External" if info["protocol"] == "usb" else "Block Device"

            # 2. Use blkid for Label and UUID (requires root usually, but we try)
            try:
                blkid_output = subprocess.check_output(["blkid", disk_id], text=True)
                # blkid output: /dev/sda1: UUID="..." TYPE="..." LABEL="..."
                label_match = re.search(r'LABEL="([^"]+)"', blkid_output)
                uuid_match = re.search(r'UUID="([^"]+)"', blkid_output)
                if label_match: info["label"] = label_match.group(1)
                if uuid_match: info["uuid"] = uuid_match.group(1)
            except Exception:
                pass

            # 3. udevadm metadata
            try:
                udev_output = subprocess.check_output(["udevadm", "info", "--query=all", "--name=" + disk_id], text=True)
                for line in udev_output.splitlines():
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key, val = key.strip(), val.strip()
                        if key in ["ID_VENDOR_ID", "ID_USB_VENDOR_ID"]: info["idVendor"] = val
                        elif key in ["ID_MODEL_ID", "ID_USB_MODEL_ID"]: info["idProduct"] = val
                        elif key in ["ID_SERIAL_SHORT", "ID_SERIAL"]: info["serial"] = val
                        elif key in ["ID_VENDOR", "ID_USB_VENDOR"]: info["vendor"] = val
                        elif key in ["ID_MODEL", "ID_USB_MODEL"]: info["product"] = val
                        elif key == "ID_USB_DRIVER": info["protocol"] = "usb"
                if info["idVendor"] != "Unknown" and info["idProduct"] != "Unknown":
                    info["usb_id"] = f"{info['idVendor']}:{info['idProduct']}"
            except Exception as e:
                logger.debug(f"udevadm failed for {disk_id}: {e}")

            # Fallback: Use lsusb to find Vendor/Product if udevadm failed
            if info["usb_id"] == "Unknown":
                try:
                    lsusb_output = subprocess.check_output(["lsusb"], text=True)
                    # Look for the model name in lsusb output
                    if info["model"] != "Unknown":
                        for line in lsusb_output.splitlines():
                            if info["model"].lower() in line.lower():
                                # Line format: Bus 001 Device 004: ID 0781:5581 Kingston Technology Co.
                                match = re.search(r'ID ([0-9a-fA-F]{4}):([0-9a-fA-F]{4})', line)
                                if match:
                                    info["idVendor"] = match.group(1)
                                    info["idProduct"] = match.group(2)
                                    info["usb_id"] = f"{info['idVendor']}:{info['idProduct']}"
                                    # Try to extract vendor/product from the rest of the line
                                    parts = line.split("ID " + info["usb_id"] + " ")
                                    if len(parts) > 1:
                                        info["product"] = parts[1].strip()
                                    break
                except Exception as e:
                    logger.debug(f"lsusb fallback failed: {e}")

            # 4. Aggressive sysfs traversal for USB ID and Bus/Dev
            try:
                dev_name = disk_id.replace("/dev/", "")
                sys_path = f"/sys/block/{dev_name}/device"
                
                # Find Bus and Device numbers from the sysfs path
                # Path usually looks like /sys/devices/pci.../usb1/1-1/1-1:1.0/host0/usb0/0-1/sdX
                # We look for the 'usbX' part and the 'X-Y' part
                curr = sys_path
                while curr and curr != "/":
                    if "usb" in curr:
                        # Try to extract bus and device from the path
                        # Example: /sys/devices/platform/soc/3f980000.usb/usb1/1-1/host1/usb1/1-1/sda
                        # The '1-1' part is often bus-device
                        match = re.search(r'/usb(\d+)/(\d+-\d+)', curr)
                        if match:
                            info["bus"] = match.group(1)
                            info["device"] = match.group(2).split('-')[-1]
                            break
                    
                    v_file, p_file = f"{curr}/idVendor", f"{curr}/idProduct"
                    if os.path.exists(v_file) and os.path.exists(p_file):
                        with open(v_file, 'r') as f: info["idVendor"] = f.read().strip()
                        with open(p_file, 'r') as f: info["idProduct"] = f.read().strip()
                        info["usb_id"] = f"{info['idVendor']}:{info['idProduct']}"
                    
                    curr = os.path.dirname(curr)
                    if curr == "/": break
            except Exception as e:
                logger.debug(f"sysfs traversal failed for {disk_id}: {e}")
        except Exception as e:
            logger.debug(f"Error fetching detailed device info for {disk_id}: {e}")
        return info

    def get_usb_slot(self, disk_id: str) -> int:
        """Maps a block device to a physical USB slot (1-4) on Raspberry Pi."""
        try:
            dev_name = disk_id.replace("/dev/", "")
            # Handle partitions (e.g., sda1 -> sda)
            match = re.match(r'^([a-z]+)\d*$', dev_name)
            if match:
                dev_name = match.group(1)
            
            sys_path = f"/sys/block/{dev_name}/device"
            
            # We need the full path to find the port number
            # Example: /sys/devices/.../usb1/1-1/1-1.4/1-1.4:1.0/...
            # The port is the digit after the dot in the segment like '1-1.4'
            
            # Use readlink to get the absolute path from /sys/block/sdX/device
            full_path = subprocess.check_output(["readlink", "-f", sys_path], text=True)
            
            # Look for the pattern X-Y.Z where Z is the port
            matches = re.findall(r'(\d+-\d+\.(\d+))', full_path)
            if matches:
                last_match = matches[-1]
                port = int(last_match[1])
                if 1 <= port <= 4:
                    # Map kernel ports 1-4 to physical ports 2-5 as per ports.md
                    return port + 1
        except Exception:
            pass
        return 0

    def get_boot_slot(self) -> int:
        """Identifies which USB slot is used for the current boot device."""
        try:
            # Find the device mounted at /
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) > 1 and parts[1] == "/":
                        boot_dev = parts[0]
                        return self.get_usb_slot(boot_dev)
        except Exception:
            pass
        return 0
