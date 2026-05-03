"""
USB discovery for macOS.
"""
import subprocess
import re
import plistlib
from typing import Set, Dict, Any
from cloudmesh.ai.pi.base import USBFinderBase
from cloudmesh.ai.common.logging import get_logger

logger = get_logger("darwin_finder")

class DarwinFinder(USBFinderBase):
    """USB discovery for macOS."""
    def get_external_drives(self) -> Set[str]:
        candidates = set()
        try:
            output = subprocess.check_output(["system_profiler", "SPUSBDataType"], text=True)
            matches = re.findall(r"BSD Name: (disk\d+)", output)
            for disk_id in matches:
                candidates.add(f"/dev/{disk_id}")
            if not candidates:
                boot_disk_output = subprocess.check_output(["diskutil", "info", "/"], text=True)
                boot_disk = ""
                for line in boot_disk_output.splitlines():
                    if "Device Node:" in line:
                        boot_disk = line.split(":", 1)[1].strip()
                        break
                list_output = subprocess.check_output(["diskutil", "list"], text=True)
                for line in list_output.splitlines():
                    match = re.match(r"(/dev/disk\d+)", line.strip())
                    if match:
                        disk_id = match.group(1)
                        if boot_disk and (boot_disk in disk_id or disk_id == boot_disk):
                            continue
                        candidates.add(disk_id)
        except Exception as e:
            logger.error(f"Error detecting drives on macOS: {e}")
        return candidates

    def get_device_info(self, disk_id: str) -> Dict[str, Any]:
        info = {
            "id": disk_id, "name": "Unknown", "size": "Unknown", "size_bytes": 0,
            "model": "Unknown", "protocol": "Unknown", "type": "Unknown",
            "vendor": "Unknown", "product": "Unknown", "idVendor": "Unknown",
            "idProduct": "Unknown", "serial": "Unknown", "bus": "Unknown",
            "device": "Unknown", "usb_id": "Unknown", "mountpoint": "Unknown"
        }
        try:
            plist_data = subprocess.check_output(["diskutil", "info", "-plist", disk_id])
            data = plistlib.loads(plist_data)
            info["name"] = data.get("DeviceName", "Unknown")
            raw_size = data.get("TotalSize", 0)
            if isinstance(raw_size, int):
                info["size_bytes"] = raw_size
                info["size"] = f"{raw_size // (1024**3)} GB"
            else:
                info["size"] = str(raw_size)
            info["protocol"] = data.get("Protocol", "Unknown")
            info["type"] = data.get("DeviceType", "Unknown")
            info["mountpoint"] = data.get("MountPoint", "Unknown")
            
            usb_output = subprocess.check_output(["system_profiler", "SPUSBDataType"], text=True)
            blocks = re.split(r'\n(?=[^\s])', usb_output)
            for block in blocks:
                if f"BSD Name: {disk_id.replace('/dev/', '')}" in block:
                    vendor_match = re.search(r"Manufacturer:\s*(.*)", block)
                    product_match = re.search(r"Product:\s*(.*)", block)
                    if vendor_match: info["vendor"] = vendor_match.group(1).strip()
                    if product_match: info["product"] = product_match.group(1).strip()
                    break
            
            try:
                ioreg_output = subprocess.check_output(["ioreg", "-r", "-c", "IOUSBHostDevice", "-l"], text=True)
                blocks = re.split(r'(?=0x[0-9a-fA-F]+)', ioreg_output)
                disk_short = disk_id.replace('/dev/', '')
                for block in blocks:
                    if f'"BSD Name" = "{disk_short}"' in block or f'BSD Name "{disk_short}"' in block:
                        keys_to_find = {
                            "USB Product Name": "usb_product_name",
                            "USB Vendor Name": "usb_vendor_name",
                            "kUSBProductString": "usb_product_string",
                            "kUSBVendorString": "usb_vendor_string"
                        }
                        for label, internal_name in keys_to_find.items():
                            pattern = rf'"{label}"\s*=\s*"?([^"\n\r]*)"?'
                            match = re.search(pattern, block)
                            if match:
                                val = match.group(1).strip().strip('"')
                                if val:
                                    info[internal_name] = val
                                    if "Vendor" in label and info["vendor"] == "Unknown":
                                        info["vendor"] = val
                                    if "Product" in label and info["product"] == "Unknown":
                                        info["product"] = val
                        break
            except Exception as e:
                logger.debug(f"ioreg scan failed for {disk_id}: {e}")

            if info["name"] != "Unknown": info["model"] = info["name"]
            elif info["product"] != "Unknown": info["model"] = info["product"]
            elif info["protocol"] != "Unknown": info["model"] = f"{info['protocol']} Storage Device"
        except Exception as e:
            logger.debug(f"Error fetching detailed device info for {disk_id}: {e}")
        return info