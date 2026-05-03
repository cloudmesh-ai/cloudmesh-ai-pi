import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import platform
import threading
import time
from cloudmesh.ai.common.io import console, path_expand
from cloudmesh.ai.pi.burner import OpenClawBurner
from cloudmesh.ai.pi.led import PiLeds, PiLed
from cloudmesh.ai.pi.logger import InstallLogger
from cloudmesh.ai.pi.installer import PiInstaller
from cloudmesh.ai.pi.network import NetworkDiscoverer


class TestOpenClawBurner(unittest.TestCase):
    def setUp(self):
        self.patcher_system = patch("platform.system", return_value="Linux")
        self.patcher_system.start()
        self.patcher_which = patch("shutil.which", return_value="/usr/bin/rpi-imager")
        self.patcher_which.start()
        self.patcher_check_output = patch(
            "subprocess.check_output", return_value=b"rpi-imager v2.0.7"
        )
        self.patcher_check_output.start()
        self.patcher_run = patch("subprocess.run")
        self.patcher_run.start()
        self.hostname = "test-node"
        self.username = "test-user"
        self.key_path = "/tmp/test_key.pub"
        # We mock the existence and content of the key file in tests that use it

    def tearDown(self):
        self.patcher_system.stop()
        self.patcher_which.stop()
        self.patcher_check_output.stop()
        self.patcher_run.stop()

    def test_os_support_fail(self):
        with patch("platform.system", return_value="Windows"):
            with self.assertRaises(SystemExit):
                OpenClawBurner(self.hostname, self.username, self.key_path)

    def test_validate_ssh_key_mocked(self):
        # Test SSH key validation without real file system access
        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.stat"
        ) as mock_stat:
            mock_stat.return_value.st_size = 100
            burner = OpenClawBurner(self.hostname, self.username, self.key_path)
            self.assertTrue(burner._validate_ssh_key())

    def test_config_loading_single_yaml(self):
        yaml_content = """
        defaults:
          prefix: "test"
          range: "01-02"
          username: "cluster-user"
        nodes:
          node-{range}:
            hostname: "{prefix}-{range}"
        """
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            burner = OpenClawBurner(
                hostname="",
                username="",
                key_path="",
                config_file="cluster.yaml",
                node_name="node-01",
            )
            self.assertEqual(burner.hostname, "test-01")
            self.assertEqual(burner.username, "cluster-user")


class TestPiLeds(unittest.TestCase):
    @patch("subprocess.run")
    def test_led_on_off(self, mock_run):
        led = PiLed("led0")
        led.on()
        # Verify trigger set to none and brightness set to 1
        mock_run.assert_any_call(
            ["sudo", "sh", "-c", "echo none > /sys/class/leds/led0/trigger"],
            check=True,
            capture_output=True,
        )
        mock_run.assert_any_call(
            ["sudo", "sh", "-c", "echo 1 > /sys/class/leds/led0/brightness"],
            check=True,
            capture_output=True,
        )

        led.off()
        mock_run.assert_called_with(
            ["sudo", "sh", "-c", "echo 0 > /sys/class/leds/led0/brightness"],
            check=True,
            capture_output=True,
        )

    @patch("subprocess.run")
    def test_siren_pattern(self, mock_run):
        leds = PiLeds()
        # Use a very short duration for testing
        leds.siren(duration=0.1, interval=0.01)
        # Verify that both act and pwr were toggled
        calls = [c[0][0] for c in mock_run.call_args_list]
        self.assertTrue(any("led0" in str(cmd) for cmd in calls))
        self.assertTrue(any("led1" in str(cmd) for cmd in calls))


class TestInstallLogger(unittest.TestCase):
    @patch("cloudmesh.ai.pi.logger.PiLeds")
    def test_multiplex_logging(self, mock_leds):
        # Mock TTY availability and open calls to prevent real OS interaction
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open()
        ) as mock_file, patch("cloudmesh.ai.pi.logger.subprocess.run") as mock_run:

            # We must patch subprocess.run inside the logger module specifically
            # because it's imported locally in the method.
            logger = InstallLogger()
            logger.info("Test Message")

            # Verify file write (via sudo echo)
            mock_run.assert_called()
            # The command is the 4th element in the list: ["sudo", "sh", "-c", "echo ..."]
            cmd_string = mock_run.call_args[0][0][3]
            self.assertIn("INFO", cmd_string)
            self.assertIn("Test Message", cmd_string)

            # Verify TTY write
            mock_file.assert_any_call("/dev/tty1", "a")

    @patch("cloudmesh.ai.pi.logger.subprocess.run")
    @patch("cloudmesh.ai.pi.logger.PiLeds")
    def test_error_triggers_fault_leds(self, mock_leds, mock_run):
        with patch("os.path.exists", return_value=False):
            logger = InstallLogger()
            logger.error("Critical Failure")

            # Verify both LEDs set to True
            mock_leds.return_value.set_led.assert_any_call("act", True)
            mock_leds.return_value.set_led.assert_any_call("pwr", True)


class TestPiInstaller(unittest.TestCase):
    @patch("cloudmesh.ai.pi.installer.InstallLogger")
    @patch("cloudmesh.ai.pi.led.PiLeds")
    def test_installation_flow(self, mock_leds, mock_logger_cls):
        mock_logger = mock_logger_cls.return_value
        installer = PiInstaller()

        # Mock state to be PRE_REBOOT
        with patch.object(
            PiInstaller, "_get_state", return_value={"phase": "PRE_REBOOT"}
        ), patch.object(
            PiInstaller, "_generate_scripts", return_value=[]
        ), patch.object(
            PiInstaller, "_schedule_auto_resume"
        ), patch.object(
            PiInstaller, "run_cmd"
        ):

            installer.full_install()

            # Verify heartbeat started
            mock_logger.set_state.assert_any_call("heartbeat")
            # Verify siren triggered before reboot
            mock_logger.set_state.assert_any_call("siren")

    @patch("cloudmesh.ai.pi.installer.InstallLogger")
    def test_fault_state_on_exception(self, mock_logger_cls):
        mock_logger = mock_logger_cls.return_value
        installer = PiInstaller()

        with patch.object(
            PiInstaller, "_get_state", return_value={"phase": "PRE_REBOOT"}
        ), patch.object(
            PiInstaller, "_generate_scripts", side_effect=Exception("Disk Full")
        ):

            with self.assertRaises(Exception):
                installer.full_install()

            # Verify fault state was set
            mock_logger.set_state.assert_called_with("fault")


class TestNetworkDiscoverer(unittest.TestCase):
    """Tests for the NetworkDiscoverer class."""

    def test_parse_nmap_output(self):
        # Mock nmap output based on user provided data
        mock_output = """
Nmap scan report for 192.168.50.1
Host is up (0.0086s latency).
MAC Address: 30:C5:99:C2:7C:B0 (ASUSTek Computer)

Nmap scan report for pi.hole (192.168.50.200)
Host is up (0.054s latency).
MAC Address: DC:A6:32:19:1B:C4 (Raspberry Pi Trading)

Nmap scan report for 192.168.50.104
Host is up.
"""
        discoverer = NetworkDiscoverer()
        devices = discoverer._parse_nmap_output(mock_output)
        
        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[0]["hostname"], "Unknown")
        self.assertEqual(devices[0]["ip"], "192.168.50.1")
        self.assertEqual(devices[0]["mac"], "30:C5:99:C2:7C:B0")
        self.assertEqual(devices[0]["vendor"], "ASUSTek Computer")
        
        self.assertEqual(devices[1]["hostname"], "pi.hole")
        self.assertEqual(devices[1]["ip"], "192.168.50.200")
        self.assertEqual(devices[1]["mac"], "DC:A6:32:19:1B:C4")
        self.assertEqual(devices[1]["vendor"], "Raspberry Pi Trading")
        
        self.assertEqual(devices[2]["hostname"], "Unknown")
        self.assertEqual(devices[2]["ip"], "192.168.50.104")
        self.assertEqual(devices[2]["mac"], "Unknown")
        self.assertEqual(devices[2]["vendor"], "Unknown")

    @patch("socket.gethostbyaddr")
    @patch("subprocess.run")
    def test_discover_success(self, mock_run, mock_resolve):
        # Mock subprocess.run to return a successful nmap scan without hostname
        mock_run.return_value = MagicMock(
            stdout="Nmap scan report for 192.168.50.1\nHost is up.\nMAC Address: 00:11:22:33:44:55 (Vendor X)",
            returncode=0
        )
        # Mock socket resolution to return a hostname
        mock_resolve.return_value = ("my-device.local", [], ["192.168.50.1"])
        
        discoverer = NetworkDiscoverer(subnet="192.168.50.0/24")
        devices = discoverer.discover()
        
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["ip"], "192.168.50.1")
        self.assertEqual(devices[0]["hostname"], "my-device.local")
        mock_run.assert_called_once_with(
            ["sudo", "nmap", "-sn", "192.168.50.0/24"],
            capture_output=True, text=True, check=True
        )
        mock_resolve.assert_called_once_with("192.168.50.1")

    @patch("subprocess.run")
    def test_discover_deep_scan(self, mock_run):
        # First call: nmap -sn (Ping Scan)
        # Second call: nmap -sV (Deep Scan)
        mock_run.side_effect = [
            MagicMock(
                stdout="Nmap scan report for 192.168.50.1\nHost is up.\nMAC Address: 00:11:22:33:44:55 (Vendor X)",
                returncode=0
            ),
            MagicMock(
                stdout="PORT    STATE SERVICE VERSION\n22/tcp open  ssh     OpenSSH 8.2p1 Ubuntu",
                returncode=0
            )
        ]
        
        # Mock socket resolution to fail so it triggers deep scan
        with patch("socket.gethostbyaddr", side_effect=socket.herror):
            discoverer = NetworkDiscoverer(subnet="192.168.50.0/24")
            devices = discoverer.discover(deep=True)
            
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["hostname"], "ssh (OpenSSH 8.2p1 Ubuntu)")
            
            # Verify both nmap calls were made
            self.assertEqual(mock_run.call_count, 2)
            mock_run.assert_any_call(
                ["sudo", "nmap", "-sn", "192.168.50.0/24"],
                capture_output=True, text=True, check=True
            )
            mock_run.assert_any_call(
                ["sudo", "nmap", "-sV", "-p", "22,80,443", "192.168.50.1"],
                capture_output=True, text=True, check=True
            )

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_discover_nmap_missing(self, mock_run):
        # Mock FileNotFoundError when nmap is not installed
        discoverer = NetworkDiscoverer()
        devices = discoverer.discover()
        
        self.assertEqual(devices, [])

class TestUSBDiscoverer(unittest.TestCase):
    """Tests for USB discovery functionality."""

    @patch("cloudmesh.ai.pi.findusb.subprocess.run")
    def test_discover_usb_success(self, mock_run):
        # Mock lsusb output
        mock_run.return_value = MagicMock(
            stdout="Bus 001 Device 002: ID 1d6b:0002 Linux Foundation 2.0 root hub\n"
                   "Bus 001 Device 003: ID 04b4:0101 Cypress Semiconductor Corp. USB Device",
            returncode=0
        )
        
        from cloudmesh.ai.pi.findusb import find_usb_devices
        devices = find_usb_devices()
        
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["idVendor"], "1d6b")
        self.assertEqual(devices[0]["idProduct"], "0002")
        self.assertEqual(devices[1]["idVendor"], "04b4")
        self.assertEqual(devices[1]["idProduct"], "0101")

if __name__ == "__main__":
    unittest.main()
