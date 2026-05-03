import os
import datetime
import subprocess
from cloudmesh.ai.common.io import console
from cloudmesh.ai.pi.led import PiLeds

class InstallLogger:
    """
    Multiplexes installation logs to a file, the system console (TTY), 
    and the onboard LEDs.
    """
    def __init__(self, log_file: str = "/var/log/openclaw_install.log"):
        self.log_file = log_file
        self.leds = PiLeds()
        self.tty_path = "/dev/tty1"
        self._tty_available = self._check_tty()

    def _check_tty(self) -> bool:
        """Checks if the system console is writable."""
        try:
            if os.path.exists(self.tty_path):
                # Try to open for writing to verify permissions/availability
                with open(self.tty_path, "a") as f:
                    f.write("")
                return True
        except Exception:
            pass
        return False

    def _write_to_tty(self, message: str):
        """Writes a message to the physical monitor via /dev/tty1."""
        if self._tty_available:
            try:
                with open(self.tty_path, "a") as f:
                    f.write(f"{message}\n")
            except Exception as e:
                # If we lose access to TTY, stop trying
                self._tty_available = False

    def _write_to_file(self, level: str, message: str):
        """Writes a timestamped message to the log file."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level}] {message}\n"
        try:
            # Use sudo to write to /var/log
            subprocess.run(["sudo", "sh", "-c", f"echo '{formatted_msg}' >> {self.log_file}"], 
                           check=True, capture_output=True)
        except Exception as e:
            console.error(f"Failed to write to log file {self.log_file}: {e}")

    def info(self, message: str):
        """Log informational message to all outputs."""
        self._write_to_file("INFO", message)
        self._write_to_tty(f"INFO: {message}")
        console.print(f"[blue]{message}[/blue]")

    def warn(self, message: str):
        """Log warning message to all outputs."""
        self._write_to_file("WARN", message)
        self._write_to_tty(f"WARNING: {message}")
        console.print(f"[yellow]{message}[/yellow]")

    def error(self, message: str):
        """Log error message and trigger Fault LED state."""
        self._write_to_file("ERROR", message)
        self._write_to_tty(f"ERROR: {message}")
        console.print(f"[red]{message}[/red]")
        
        # Trigger Fault State: Both LEDs Solid ON
        self.leds.set_led("act", True)
        self.leds.set_led("pwr", True)

    def set_state(self, state: str):
        """
        Triggers LED patterns based on installation state.
        States: 'heartbeat', 'siren', 'success', 'fault'
        """
        if state == "heartbeat":
            # Heartbeat is usually managed by a thread in the installer,
            # but we ensure PWR is ON here.
            self.leds.set_led("pwr", True)
        elif state == "siren":
            self.info("Triggering reboot warning siren...")
            self.leds.siren()
        elif state == "success":
            self.info("Installation successful. Setting LEDs to Ready state.")
            self.leds.set_led("act", False)
            self.leds.set_led("pwr", True)
        elif state == "fault":
            self.error("System fault detected. Setting LEDs to Fault state.")
            self.leds.set_led("act", True)
            self.leds.set_led("pwr", True)