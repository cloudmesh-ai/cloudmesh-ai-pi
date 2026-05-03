"""
Pi IO Module
============
Handles interaction with the physical Raspberry Pi display (TTY and Framebuffer).
"""

import os
import numpy as np
from PIL import Image, ImageDraw
from rich.console import Console
from rich.panel import Panel
import pyfiglet
from cloudmesh.ai.common.logging import get_logger

logger = get_logger("pi_io")

class Terminal:
    """Handles output to the physical Pi screen (/dev/tty1 and /dev/fb1)."""

    def __init__(self, tty_path: str = "/dev/tty1", fb_path: str = "/dev/fb1"):
        self.tty_path = tty_path
        self.fb_path = fb_path
        self._init_console()

    def _init_console(self):
        """Initializes the rich console for the TTY device."""
        if os.path.exists(self.tty_path):
            # We create a console that writes to the TTY file
            # Note: In a real environment, we'd open the file in a way that persists
            # or re-open it per write to avoid locking issues.
            self.console = Console(width=480, force_terminal=True)
        else:
            self.console = Console()
            logger.warn(f"TTY path {self.tty_path} not found. Falling back to standard output.")

    def clear(self):
        """Clears the physical terminal screen."""
        if os.path.exists(self.tty_path):
            with open(self.tty_path, "w") as f:
                f.write("\033[H\033[J")

    def write_text(self, text: str, style: str = ""):
        """Writes formatted text to the physical screen."""
        try:
            with open(self.tty_path, "w") as f:
                # Use rich to render the text to a string and write it to the file
                from rich.console import Console
                temp_console = Console(file=f, force_terminal=True, width=480)
                temp_console.print(f"[{style}]{text}[/{style}]")
        except Exception as e:
            logger.error(f"Failed to write text to {self.tty_path}: {e}")

    def write_panel(self, text: str, title: str = "Status", style: str = "green"):
        """Writes a formatted rich panel to the physical screen."""
        try:
            with open(self.tty_path, "w") as f:
                from rich.console import Console
                temp_console = Console(file=f, force_terminal=True, width=480)
                temp_console.print(Panel(f"[{style}]{text}[/{style}]", title=title, expand=False))
        except Exception as e:
            logger.error(f"Failed to write panel to {self.tty_path}: {e}")

    def write_banner(self, text: str, font: str = "slant"):
        """Writes a large ASCII banner to the physical screen."""
        try:
            banner = pyfiglet.figlet_format(text, font=font)
            with open(self.tty_path, "w") as f:
                f.write("\033[H\033[J") # Clear screen
                f.write(banner)
        except Exception as e:
            logger.error(f"Failed to write banner to {self.tty_path}: {e}")

    def write_graphics(self, image: Image.Image = None, color: tuple = (0, 0, 0), text: str = None):
        """
        Renders graphics to the framebuffer (/dev/fb1).
        If no image is provided, creates a simple colored screen with optional text.
        """
        if not os.path.exists(self.fb_path):
            logger.error(f"Framebuffer {self.fb_path} not found.")
            return

        try:
            if image is None:
                # Create a default image (480x320 for Kuman)
                image = Image.new('RGB', (480, 320), color=color)
                if text:
                    draw = ImageDraw.Draw(image)
                    # Simple text centering
                    draw.text((200, 150), text, fill=(255, 255, 255))

            # Ensure image is the correct size
            image = image.resize((480, 320))
            data = np.array(image)

            # Pack RGB888 to RGB565 (16-bit)
            r = (data[:, :, 0] >> 3).astype(np.uint16)
            g = (data[:, :, 1] >> 2).astype(np.uint16)
            b = (data[:, :, 2] >> 3).astype(np.uint16)
            rgb565 = (r << 11) | (g << 5) | b

            with open(self.fb_path, "wb") as f:
                f.write(rgb565.tobytes())
        except Exception as e:
            logger.error(f"Failed to write graphics to {self.fb_path}: {e}")

    def set_backlight(self, state: bool = True):
        """Ensures the display is awake."""
        cmd = 'sudo sh -c "TERM=linux setterm -blank 0 > /dev/tty1"'
        try:
            subprocess.run(cmd, shell=True, check=True)
        except Exception as e:
            logger.error(f"Failed to set backlight: {e}")