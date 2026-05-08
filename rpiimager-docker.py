import subprocess

class DockerRPiImager:
    """
    Comprehensive Python wrapper for rpi-imager --cli running inside Docker.
    Requires a Docker image built with xvfb and necessary Qt libraries.
    """
    def __init__(self, image_name="rpi-imager-docker"):
        self.image_name = image_name

    def _execute(self, args):
        """Internal helper to run the docker command with hardware access."""
        # Combines privileged access and device mounting [cite: 186, 193]
        cmd = [
            "docker", "run", "--rm",
            "--privileged",
            "-v", "/dev:/dev",
            self.image_name
        ] + args
        
        try:
            result = subprocess.run(
                cmd,
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
              eject=True,
              write_system_drive=False,
              sha256=None,
              cache_file=None,
              first_run_script=None,
              userdata=None,
              networkconfig=None,
              secure_boot_key=None,
              debug=False,
              quiet=False,
              log_file=None):
        """
        Executes the flash process with all supported CLI parameters [cite: 160-165].
        """
        # Start with the mandatory --cli flag for the container's entrypoint
        args = ["--cli"]

        # Boolean Flags [cite: 160-164]
        if not verify: args.append("--disable-verify")
        if not eject: args.append("--disable-eject")
        if write_system_drive: args.append("--enable-writing-system-drives")
        if debug: args.append("--debug")
        if quiet: args.append("--quiet")

        # Value-based Arguments [cite: 160-165]
        if sha256: args.extend(["--sha256", sha256])
        if cache_file: args.extend(["--cache-file", cache_file])
        if first_run_script: args.extend(["--first-run-script", first_run_script])
        if userdata: args.extend(["--cloudinit-userdata", userdata])
        if networkconfig: args.extend(["--cloudinit-networkconfig", networkconfig])
        if secure_boot_key: args.extend(["--secure-boot-key", secure_boot_key])
        if log_file: args.extend(["--log-file", log_file])

        # Positional Arguments [cite: 166]
        args.extend([src, dst])

        return self._execute(args)

    def get_version(self):
        """Retrieve the version of rpi-imager inside the container[cite: 159]."""
        return self._execute(["--version"])

# Usage Example
if __name__ == "__main__":
    imager = DockerRPiImager()
    
    # Example: Flashing a local image with cloud-init data
    # response = imager.flash(
    #     src="/home/admin/images/raspios.img",
    #     dst="/dev/sda",
    #     userdata="/home/admin/config/user-data",
    #     verify=False
    # )
    # print(f"Success: {response['returncode'] == 0}")