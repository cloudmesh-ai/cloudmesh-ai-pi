"""
USB Device Discovery Entry Point
================================
"""
import platform
from typing import List, Dict, Any, Tuple
from cloudmesh.ai.pi.darwin_finder import DarwinFinder
from cloudmesh.ai.pi.raspbian_finder import RaspbianFinder

class USBFinder:
    """
    Backward compatibility wrapper for the new finder logic.
    """
    def __init__(self):
        pass

    def find_devices(self):
        devices, _ = find_usb_devices()
        return devices

def find_usb_devices() -> Tuple[List[Dict[str, Any]], Dict[int, str]]:
    """
    Convenience function to find external USB devices.
    Returns a tuple: (list of device info, slot_map)
    """
    system = platform.system()
    finder = DarwinFinder() if system == "Darwin" else RaspbianFinder()
    drives = finder.get_external_drives()
    devices = [finder.get_device_info(d) for d in drives]
    
    slot_map = {}
    if isinstance(finder, RaspbianFinder):
        for dev in devices:
            slot = finder.get_usb_slot(dev["id"])
            dev["slot"] = str(slot) if slot > 0 else "Unknown"
            if slot > 0:
                slot_map[slot] = dev["model"]
                
    return devices, slot_map