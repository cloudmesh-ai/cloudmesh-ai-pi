he "Power User" Setup: fzf Selector If you don't have fzf installed, grab it via Homebrew: brew install fzf.

Add this function to your \~/.zshrc (or \~/.bashrc):

Bash \# Interactive SSH host selector s() { local host host=\$(grep -i '\^Host ' \~/.ssh/config \| awk '{print $2}' | grep -v '*' | fzf --height 40% --reverse --prompt="SSH Host > ")
  if [ -n "$host" \]; then echo "Connecting to $host..."
    ssh "$host" fi }

|             |                  |              |                                  |
|-------------|------------------|--------------|----------------------------------|
| **Machine** | **Color Name**   | **Hex Code** | **.bashrc / .zshrc Command**     |
| **DGX**     | **Misty Rose**   | `#FFE4E1`    | `echo -ne "\033]11;#FFE4E1\007"` |
| **White**   | **Lavender**     | `#E6E6FA`    | `echo -ne "\033]11;#E6E6FA\007"` |
| **Spark**   | **Spring Green** | `#00FF7F`    | `echo -ne "\033]11;#00FF7F\007"` |
| **NAS**     | **Alice Blue**   | `#F0F8FF`    | `echo -ne "\033]11;#F0F8FF\007"` |