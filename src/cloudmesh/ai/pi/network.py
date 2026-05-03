"""
Network Discovery Logic
=======================
Provides functionality to discover devices on the local network using nmap.
"""

import subprocess
import re
import socket
from typing import List, Dict, Optional
from cloudmesh.ai.common.io import console

class NetworkDiscoverer:
    """Handles network scanning and parsing of nmap output."""

    def __init__(self, subnet: str = "192.168.1.0/24"):
        self.subnet = subnet

    def discover(self, deep: bool = False) -> List[Dict[str, str]]:
        """
        Runs nmap -sn on the subnet and parses the output.
        Returns a list of discovered devices.
        """
        console.print(f"Scanning network {self.subnet}... (requires sudo)")
        try:
            # Run nmap -sn (Ping Scan)
            result = subprocess.run(
                ["sudo", "nmap", "-sn", self.subnet],
                capture_output=True,
                text=True,
                check=True
            )
            devices = self._parse_nmap_output(result.stdout)
            
            if deep:
                for device in devices:
                    if device["hostname"] == "Unknown":
                        deep_name = self._deep_scan(device["ip"])
                        if deep_name:
                            device["hostname"] = deep_name
            
            return devices
        except subprocess.CalledProcessError as e:
            console.error(f"Nmap scan failed: {e.stderr}")
            return []
        except FileNotFoundError:
            console.error("nmap not found. Please install it (e.g., 'brew install nmap' on macOS).")
            return []

    def _resolve_hostname(self, ip: str) -> str:
        """
        Attempts to resolve the hostname for a given IP using system resolver.
        This often finds .local names on macOS.
        """
        try:
            # gethostbyaddr returns (hostname, aliaslist, ipaddrlist)
            return socket.gethostbyaddr(ip)[0]
        except (socket.herror, socket.gaierror, IndexError):
            return "Unknown"

    def _deep_scan(self, ip: str) -> Optional[str]:
        """
        Probes common ports to find a service banner that might reveal the device name.
        """
        try:
            # -sV: Service version detection
            # -p: Only scan common ports to keep it relatively fast
            result = subprocess.run(
                ["sudo", "nmap", "-sV", "-p", "22,80,443", ip],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Look for service names in the output
            # Example: 22/tcp open ssh OpenSSH 8.2p1 Ubuntu...
            # Example: 80/tcp open http Apache httpd 2.4.41 ((Ubuntu))
            for line in result.stdout.splitlines():
                if "/tcp" in line and "open" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        # The service name is usually the 3rd or 4th element
                        # e.g., "ssh", "http", "https"
                        service = parts[2]
                        version = " ".join(parts[3:])
                        # If we find a specific product name in the version string, use it
                        return f"{service} ({version})"
            
            return None
        except Exception:
            return None

    def _parse_nmap_output(self, output: str) -> List[Dict[str, str]]:
        """
        Parses nmap -sn output to extract IP, MAC, and Vendor.
        """
        devices = []
        # Nmap output for -sn typically looks like:
        # Nmap scan report for 192.168.50.1
        # Host is up (0.0086s latency).
        # MAC Address: 30:C5:99:C2:7C:B0 (ASUSTek Computer)
        
        # Split by "Nmap scan report for"
        reports = output.split("Nmap scan report for ")[1:]
        
        for report in reports:
            lines = report.splitlines()
            if not lines:
                continue
                
            # IP and Hostname are in the first line of the report
            ip_line = lines[0].strip()
            # Handle cases like "pi.hole (192.168.50.200)"
            if "(" in ip_line and ")" in ip_line:
                hostname = ip_line[:ip_line.find(" (")].strip()
                ip = ip_line[ip_line.find("(")+1 : ip_line.find(")")]
            else:
                hostname = "Unknown"
                ip = ip_line.split()[0]
                
            # If hostname is still unknown, try a deep resolve
            if hostname == "Unknown":
                hostname = self._resolve_hostname(ip)
                
            mac = "Unknown"
            vendor = "Unknown"
            
            for line in lines:
                if "MAC Address:" in line:
                    # Example: MAC Address: 30:C5:99:C2:7C:B0 (ASUSTek Computer)
                    match = re.search(r"MAC Address: ([0-9A-Fa-f:]{17})(?:\s+\((.*?)\))?", line)
                    if match:
                        mac = match.group(1)
                        vendor = match.group(2) if match.group(2) else "Unknown"
                    break
            
            devices.append({
                "hostname": hostname,
                "ip": ip,
                "mac": mac,
                "vendor": vendor
            })
            
        return devices