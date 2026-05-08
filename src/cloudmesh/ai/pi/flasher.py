import subprocess
import re
import sys

# Optional tqdm import
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

class BMapTool:
    """
    A Python wrapper for bmaptool with an optional tqdm progress bar.
    """
    def __init__(self):
        # Regex to capture percentage from bmaptool output (e.g., "15.2%")
        self.progress_re = re.compile(r'(\d+\.?\d*)%')

    def flash(self, image_path, destination_device, use_tqdm=True):
        """
        Flashes an image. 
        :param use_tqdm: If True and tqdm is installed, shows a progress bar.
        """
        cmd = ["sudo", "bmaptool", "copy", image_path, destination_device]
        
        # Determine if we should actually use tqdm
        active_tqdm = use_tqdm and HAS_TQDM
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            if active_tqdm:
                self._run_with_tqdm(process)
            else:
                self._run_standard(process)

            process.wait()
            return process.returncode

        except Exception as e:
            print(f"\nExecution error: {e}")
            return 1

    def _run_with_tqdm(self, process):
        """Handles output parsing to update tqdm bar."""
        with tqdm(total=100, unit="%", desc="Flashing", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}%") as pbar:
            last_pct = 0
            for line in process.stdout:
                match = self.progress_re.search(line)
                if match:
                    current_pct = float(match.group(1))
                    if current_pct > last_pct:
                        pbar.update(current_pct - last_pct)
                        last_pct = current_pct

    def _run_standard(self, process):
        """Standard output for logs or environments without tqdm."""
        for line in process.stdout:
            print(line, end="")

# Example Usage
if __name__ == "__main__":
    # To use tqdm: pip install tqdm
    # To use bmaptool: sudo apt install bmap-tools
    
    IMAGE = "raspios_lite.img.xz"
    DRIVE = "/dev/sda" 
    
    flasher = BMapTool()
    
    # Example 1: Use tqdm if available
    flasher.flash(IMAGE, DRIVE, use_tqdm=True)
    
    # Example 2: Force standard text output (better for remote logging)
    # flasher.flash(IMAGE, DRIVE, use_tqdm=False)