import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import platform
from cloudmesh.ai.pi.burner import OpenClawBurner

class TestOpenClawBurner(unittest.TestCase):

    def setUp(self):
        # Mock platform.system to return Linux by default for tests
        self.patcher_system = patch('platform.system', return_value='Linux')
        self.patcher_system.start()
        
        # Mock shutil.which to simulate imager installed
        self.patcher_which = patch('shutil.which', return_value='/usr/bin/rpi-imager')
        self.patcher_which.start()

        self.hostname = "test-node"
        self.username = "test-user"
        self.key_path = "/tmp/test_key.pub"
        
        # Create a dummy key file
        with open(self.key_path, "w") as f:
            f.write("ssh-rsa AAAAB3Nza...")

    def tearDown(self):
        self.patcher_system.stop()
        self.patcher_which.stop()
        if os.path.exists(self.key_path):
            os.remove(self.key_path)

    def test_os_support_fail(self):
        with patch('platform.system', return_value='Windows'):
            with self.assertRaises(SystemExit):
                OpenClawBurner(self.hostname, self.username, self.key_path)

    def test_imager_missing(self):
        with patch('shutil.which', return_value=None):
            with patch('os.path.exists', return_value=False):
                with self.assertRaises(SystemExit):
                    OpenClawBurner(self.hostname, self.username, self.key_path)

    def test_validate_ssh_key_success(self):
        burner = OpenClawBurner(self.hostname, self.username, self.key_path)
        self.assertTrue(burner._validate_ssh_key())

    def test_validate_ssh_key_fail(self):
        burner = OpenClawBurner(self.hostname, self.username, "/non/existent/key")
        self.assertFalse(burner._validate_ssh_key())

    @patch('subprocess.check_output')
    def test_get_external_drives_linux(self, mock_output):
        mock_output.return_value = b"sdb\nsdc"
        burner = OpenClawBurner(self.hostname, self.username, self.key_path)
        drives = burner.get_external_drives()
        self.assertEqual(drives, {"/dev/sdb", "/dev/sdc"})

    @patch('subprocess.run')
    def test_flash_command(self, mock_run):
        burner = OpenClawBurner(self.hostname, self.username, self.key_path)
        burner.disk_id = "/dev/sdb"
        burner.flash("password123")
        
        # Verify that sudo was used and the correct imager command was called
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("sudo", cmd)
        self.assertIn("rpi-imager", cmd)
        self.assertIn(self.hostname, cmd)
        self.assertIn(self.username, cmd)
        self.assertIn("password123", cmd)

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="root CONSOLE=tty1")
    @patch('subprocess.run')
    def test_apply_optimizations(self, mock_run, mock_file, mock_exists):
        burner = OpenClawBurner(self.hostname, self.username, self.key_path)
        burner.disk_id = "/dev/sdb"
        
        # Mock mount for Linux
        with patch('tempfile.mkdtemp', return_value="/tmp/pi_boot"):
            burner.apply_optimizations()
            
            # Verify mount was called
            mock_run.assert_any_call(["sudo", "mount", "/dev/sdb1", "/tmp/pi_boot"], check=True)
            
            # Verify cmdline.txt was modified (via the temp_txt move)
            mock_run.assert_any_call(["sudo", "mv", "temp_txt", "/tmp/pi_boot/cmdline.txt"], check=True)

if __name__ == '__main__':
    unittest.main()