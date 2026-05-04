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
    Wrapper for platform-specific USB discovery logic.
    """
    def __init__(self):
        system = platform.system()
        self.finder = DarwinFinder() if system == "Darwin" else RaspbianFinder()

    def get_external_drives(self):
        """Delegate to the platform-specific finder."""
        return self.finder.get_external_drives()

    def get_device_info(self, disk_id: str):
        """Delegate to the platform-specific finder."""
        return self.finder.get_device_info(disk_id)

    def find_devices(self):
        """Backward compatibility method."""
        devices, _ = find_usb_devices()
        return devices

def find_usb_devices() -> Tuple[List[Dict[str, Any]], Dict[int, str], int, List[int]]:
    """
    Convenience function to find external USB devices.
    Returns a tuple: (list of device info, slot_map, boot_slot, candidate_slots)
    """
    system = platform.system()
    finder = DarwinFinder() if system == "Darwin" else RaspbianFinder()
    drives = finder.get_external_drives()
    devices = [finder.get_device_info(d) for d in drives]
    
    slot_map = {}
    boot_slot = 0
    if isinstance(finder, RaspbianFinder):
        boot_slot = finder.get_boot_slot()
        for dev in devices:
            slot = finder.get_usb_slot(dev["id"])
            dev["slot"] = str(slot) if slot > 0 else "Unknown"
            if slot > 0:
                slot_map[slot] = dev["model"]
    
    # Candidates for burning are occupied slots that are NOT the boot slot
    candidate_slots = [slot for slot in slot_map if slot != boot_slot]
                
    return devices, slot_map, boot_slot, candidate_slots
