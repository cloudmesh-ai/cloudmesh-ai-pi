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
            # 1. Robust size and mountpoint using lsblk -b (bytes)
            # We use -n (no headings) and -o (output columns)
            output = subprocess.check_output(["lsblk", "-bno", "MODEL,SIZE,TRAN,MOUNTPOINT", disk_id], text=True)
            parts = output.strip().split()
            if len(parts) >= 1: info["model"] = parts[0]
            if len(parts) >= 2: 
                try:
                    bytes_size = int(parts[1])
                    info["size_bytes"] = bytes_size
                    info["size"] = f"{bytes_size // (1024**3)} GB" if bytes_size >= 1024**3 else f"{bytes_size // (1024**2)} MB"
                except ValueError:
                    info["size"] = parts[1]
            if len(parts) >= 3: info["protocol"] = parts[2]
            if len(parts) >= 4: info["mountpoint"] = parts[3]
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
            sys_path = f"/sys/block/{dev_name}/device"
            curr = sys_path
            while curr and curr != "/":
                if "usb" in curr:
                    # Look for port number in the path (e.g., .../usb1/1-1.2)
                    match = re.search(r'usb\d+/(\d+)-(\d+)', curr)
                    if match:
                        # This is a simplification; actual mapping depends on Pi model
                        # but usually the last digit of the port path relates to the slot
                        port = int(match.group(2))
                        return (port % 4) + 1
                curr = os.path.dirname(curr)
        except Exception:
            pass
        return 0