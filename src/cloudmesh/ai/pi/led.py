import os
import time
from typing import Optional
from cloudmesh.ai.common.io import console

class PiLed:
    """
    Manages a single Raspberry Pi onboard LED via sysfs.
    """
    def __init__(self, led_id: str = "led0"):
        self.led_id = led_id
        self.base_path = f"/sys/class/leds/{self.led_id}"
        self.brightness_path = os.path.join(self.base_path, "brightness")
        self.trigger_path = os.path.join(self.base_path, "trigger")

    def _write_sysfs(self, path: str, value: str):
        try:
            # Use sudo to write to sysfs
            import subprocess
            subprocess.run(["sudo", "sh", "-c", f"echo {value} > {path}"], check=True, capture_output=True)
        except Exception as e:
            console.error(f"Failed to write {value} to {path}: {e}")

    def on(self):
        """Turns the LED on."""
        # Set trigger to none first to allow manual control
        self._write_sysfs(self.trigger_path, "none")
        self._write_sysfs(self.brightness_path, "1")

    def off(self):
        """Turns the LED off."""
        self._write_sysfs(self.brightness_path, "0")

    def blink(self, times: int = 3, interval: float = 0.2):
        """Blinks the LED a specified number of times."""
        for _ in range(times):
            self.on()
            time.sleep(interval)
            self.off()
            time.sleep(interval)

class PiLeds:
    """
    Manages the set of onboard LEDs on a Raspberry Pi.
    """
    def __init__(self):
        # Typically led0 is ACT and led1 is PWR (depending on model)
        self.leds = {
            "act": PiLed("led0"),
            "pwr": PiLed("led1")
        }

    def set_led(self, led_name: str, state: bool):
        """Sets a specific LED state."""
        led = self.leds.get(led_name.lower())
        if led:
            led.on() if state else led.off()
        else:
            console.warn(f"LED {led_name} not found.")

    def blink_all(self, times: int = 3):
        """Blinks all managed LEDs."""
        import threading
        threads = []
        for led in self.leds.values():
            t = threading.Thread(target=led.blink, args=(times,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

    def status_ok(self):
        """Signal OK by blinking ACT LED."""
        self.leds["act"].blink(times=2, interval=0.1)

    def status_error(self):
        """Signal Error by blinking ACT LED slowly."""
        self.leds["act"].blink(times=1, interval=0.5)

    def siren(self, duration: float = 5.0, interval: float = 0.3):
        """Alternates ACT and PWR LEDs for a specified duration."""
        import time
        end_time = time.time() + duration
        while time.time() < end_time:
            self.leds["act"].on()
            self.leds["pwr"].off()
            time.sleep(interval)
            self.leds["act"].off()
            self.leds["pwr"].on()
            time.sleep(interval)
        # Reset to a known state
        self.leds["act"].off()
        self.leds["pwr"].on()
