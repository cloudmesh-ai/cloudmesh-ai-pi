"""
Base class for USB discovery.
"""
from typing import Set, Dict, Any

class USBFinderBase:
    """Base class for USB discovery."""
    def get_external_drives(self) -> Set[str]:
        raise NotImplementedError()
    def get_device_info(self, disk_id: str) -> Dict[str, Any]:
        raise NotImplementedError()