import subprocess
import os

class RPiImager:
    """
    Full Python wrapper for rpi-imager --cli on headless systems.
    Requires: xvfb-run, libxcb-cursor0, and sudo privileges.
    """
    def __init__(self, imager_executable="rpi-imager"):
        self.executable = imager_executable

    def _run_command(self, args):
        """Internal helper to execute the command with the GUI-bypass layer."""
        # Combines the necessary headless bypass with the imager command [cite: 43, 48]
        base_cmd = ["sudo", "xvfb-run", self.executable, "--cli"]
        full_cmd = base_cmd + args
        
        try:
            # Capture output to allow for future parsing of progress or errors
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                check=False
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"returncode": 1, "stdout": "", "stderr": str(e)}

    def flash(self, src, dst, 
              verify=True, 
              quiet=False, 
              debug=False,
              eject=True,
              sha256=None,
              cache_file=None,
              first_run_script=None,
              userdata=None,
              networkconfig=None,
              secure_boot_key=None,
              write_system_drive=False):
        """
        Executes the flash process with all available CLI options [cite: 58-67].
        """
        args = []

        # Boolean Flags
        if not verify: args.append("--disable-verify")
        if not eject: args.append("--disable-eject")
        if quiet: args.append("--quiet")
        if debug: args.append("--debug")
        if write_system_drive: args.append("--enable-writing-system-drives")

        # Value-based Arguments [cite: 61-66]
        if sha256:
            args.extend(["--sha256", sha256])
        if cache_file:
            args.extend(["--cache-file", cache_file])
        if first_run_script:
            args.extend(["--first-run-script", first_run_script])
        if userdata:
            args.extend(["--cloudinit-userdata", userdata])
        if networkconfig:
            args.extend(["--cloudinit-networkconfig", networkconfig])
        if secure_boot_key:
            args.extend(["--secure-boot-key", secure_boot_key])

        # Positional Arguments: Source and Destination [cite: 67]
        args.extend([src, dst])

        return self._run_command(args)

    def get_version(self):
        """Returns version information[cite: 60]."""
        return self._run_command(["--version"])

# Example Implementation
if __name__ == "__main__":
    imager = RPiImager()
    
    # Example: Flashing with Cloud-Init and verification disabled
    # result = imager.flash(
    #     src="https://downloads.raspberrypi.org/raspios_lite_arm64.img.xz",
    #     dst="/dev/sdb",
    #     verify=False,
    #     userdata="user-data.yaml",
    #     networkconfig="network-config.yaml"
    # )
    
    # print(f"Status Code: {result['returncode']}")