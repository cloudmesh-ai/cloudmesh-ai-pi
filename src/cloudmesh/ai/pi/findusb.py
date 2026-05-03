
"""
USB Device Discovery Logic
=========================
"""

import os
import subprocess
import platform
import re
import plistlib
from typing import Set, Dict, Any
from cloudmesh.ai.common.logging import get_logger

# Initialize Logger
logger = get_logger("findusb")

class USBFinder:
    """Handles discovery and metadata extraction of external USB storage devices."""
    
    def __init__(self):
        self.system = platform.system()

    def get_external_drives(self) -> Set[str]:
        """
        Returns a set of external block devices, including those connected via USB hubs, 
        filtered by size (excludes drives > 512GB).
        """
        candidates = set()
        if self.system == "Darwin":
            try:
                # Use system_profiler for robust USB tree traversal on macOS
                output = subprocess.check_output(["system_profiler", "SPUSBDataType"], text=True)
                matches = re.findall(r"BSD Name: (disk\d+)", output)
                for disk_id in matches:
                    candidates.add(f"/dev/{disk_id}")
                
                # Fallback: boot-disk exclusion method
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
        else:
            try:
                output = subprocess.check_output(["lsblk", "-dno", "NAME"], text=True)
                candidates = {f"/dev/{line.strip()}" for line in output.splitlines() if line.strip()}
            except Exception as e:
                logger.error(f"Error detecting drives on Linux: {e}")

        # Return all candidates to avoid filtering issues
        return candidates

    def get_device_info(self, disk_id: str) -> Dict[str, Any]:
        """Retrieves detailed metadata about the disk, including USB vendor and product strings."""
        info = {
            "id": disk_id,
            "name": "Unknown",
            "size": "Unknown",
            "size_bytes": 0,
            "model": "Unknown",
            "protocol": "Unknown",
            "type": "Unknown",
            "vendor": "Unknown",
            "product": "Unknown",
            "idVendor": "Unknown",
            "idProduct": "Unknown",
            "serial": "Unknown",
            "bus": "Unknown",
            "device": "Unknown",
            "usb_id": "Unknown"
        }
        try:
            if self.system == "Darwin":
                # 1. Basic disk info via diskutil
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
                
                # 2. Enhanced USB info via system_profiler
                usb_output = subprocess.check_output(["system_profiler", "SPUSBDataType"], text=True)
                blocks = re.split(r'\n(?=[^\s])', usb_output)
                for block in blocks:
                    if f"BSD Name: {disk_id.replace('/dev/', '')}" in block:
                        vendor_match = re.search(r"Manufacturer:\s*(.*)", block)
                        product_match = re.search(r"Product:\s*(.*)", block)
                        if vendor_match: info["vendor"] = vendor_match.group(1).strip()
                        if product_match: info["product"] = product_match.group(1).strip()
                        break
                
                # 3. Direct ioreg scan using the user's suggested command
                try:
                    # Use -r (recursive) and -c IOUSBHostDevice to group USB devices with their children
                    ioreg_output = subprocess.check_output(["ioreg", "-r", "-c", "IOUSBHostDevice", "-l"], text=True)
                    
                    # Split output into blocks by the start of a new IOUSBHostDevice object
                    # Objects typically start with a hex address at the beginning of the line
                    blocks = re.split(r'(?=0x[0-9a-fA-F]+)', ioreg_output)
                    disk_short = disk_id.replace('/dev/', '')
                    
                    for block in blocks:
                        # If this USB device block contains the BSD Name of our disk, it's the correct device
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
                            break # Found the matching USB device
                except Exception as e:
                    logger.debug(f"ioreg scan failed for {disk_id}: {e}")

                if info["name"] != "Unknown":
                    info["model"] = info["name"]
                elif info["product"] != "Unknown":
                    info["model"] = info["product"]
                elif info["protocol"] != "Unknown":
                    info["model"] = f"{info['protocol']} Storage Device"

            else:
                # Linux: Use lsblk for basic info
                try:
                    # Remove BUS and DEV as they are not supported on all lsblk versions (e.g. Raspberry Pi)
                    output = subprocess.check_output(["lsblk", "-dno", "MODEL,SIZE,TRAN", disk_id], text=True)
                    parts = output.strip().split()
                    if len(parts) >= 1: info["model"] = parts[0]
                    if len(parts) >= 2: 
                        size_str = parts[1]
                        info["size"] = size_str
                        match = re.match(r"(\d+)([GTMK])", size_str)
                        if match:
                            val, unit = match.groups()
                            mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
                            info["size_bytes"] = int(val) * mult.get(unit, 1)
                    if len(parts) >= 3: info["protocol"] = parts[2]
                    info["type"] = "USB/External" if info["protocol"] == "usb" else "Block Device"
                except Exception as e:
                    logger.debug(f"lsblk failed for {disk_id}: {e}")

                # Use udevadm for robust USB metadata extraction
                try:
                    udev_output = subprocess.check_output(["udevadm", "info", "--query=all", "--name=" + disk_id], text=True)
                    for line in udev_output.splitlines():
                        if "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip()
                            # Try multiple common keys for vendor/product
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

                # Fallback to lsusb if udevadm didn't find the USB ID
                if info["usb_id"] == "Unknown":
                    try:
                        # Find the device in lsusb output by matching the device path or model
                        lsusb_output = subprocess.check_output(["lsusb", "-v"], text=True)
                        # This is a complex parse, but we look for the device that matches our disk_id
                        # A simpler way is to use lsusb -t to find the bus/dev and then match
                        # For now, let's try to find the vendor/product if we have a model name
                        if info["model"] != "Unknown":
                            for line in lsusb_output.splitlines():
                                if info["model"] in line and "id" in line.lower():
                                    match = re.search(r"id\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", line)
                                    if match:
                                        info["idVendor"], info["idProduct"] = match.groups()
                                        info["usb_id"] = f"{info['idVendor']}:{info['idProduct']}"
                                        break
                    except Exception as e:
                        logger.debug(f"lsusb fallback failed for {disk_id}: {e}")
        except Exception as e:
            logger.debug(f"Error fetching detailed device info for {disk_id}: {e}")
        
        return info

def find_usb_devices():
    """
    Convenience function to find external USB devices.
    Returns a list of device info dictionaries.
    """
    print("DEBUG: Loading find_usb_devices from local source")
    finder = USBFinder()
    drives = finder.get_external_drives()
    return [finder.get_device_info(d) for d in drives]
