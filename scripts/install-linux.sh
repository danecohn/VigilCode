#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Per-user install of VigilCode on Linux. No sudo; nothing outside your home folder is changed.
#   - a private Python environment in ~/.local/share/vigilcode
#   - the `vigil` command in ~/.local/bin
#   - a "VigilCode Workbench" menu entry (~/.local/share/applications), no custom icon yet
#   - ~/VigilCode Projects, the folder the workbench opens (created once, never overwritten)
# Needs python3 with the venv module (Debian/Ubuntu: python3-venv) and a C compiler (gcc or clang).
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
data="${XDG_DATA_HOME:-$HOME/.local/share}"
home_dir="$data/vigilcode"
projects="$HOME/VigilCode Projects"
command -v python3 >/dev/null || { echo "python3 not found. Install Python 3.9 or later." >&2; exit 1; }
command -v cc >/dev/null || command -v gcc >/dev/null || command -v clang >/dev/null || { echo "No C compiler found. Install gcc or clang." >&2; exit 1; }
mkdir -p "$home_dir" "$HOME/.local/bin" "$data/applications"
python3 -m venv "$home_dir/venv" || { echo "Could not create a Python environment. On Debian or Ubuntu: sudo apt install python3-venv" >&2; exit 1; }
"$home_dir/venv/bin/python" -m pip install --quiet --upgrade pip
"$home_dir/venv/bin/python" -m pip install --quiet --upgrade --force-reinstall "$here"
ln -sf "$home_dir/venv/bin/vigil" "$HOME/.local/bin/vigil"
if [ ! -e "$projects" ]; then
    mkdir -p "$projects"
    cp "$here/examples/hello.vigil" "$here/examples/ledger.vigil" "$projects/"
    cp -R "$here/examples/tally" "$projects/tally"
fi
cat > "$home_dir/workbench.sh" <<'LAUNCH'
#!/bin/sh
mkdir -p "$HOME/VigilCode Projects"
exec "$(dirname "$0")/venv/bin/vigil" workbench "$HOME/VigilCode Projects"
LAUNCH
chmod +x "$home_dir/workbench.sh"
cat > "$data/applications/vigilcode-workbench.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=VigilCode Workbench
Comment=Edit, check and run VigilCode programs
Exec="$home_dir/workbench.sh"
Terminal=false
Categories=Development;IDE;
DESKTOP
echo "Installed VigilCode $("$home_dir/venv/bin/vigil" --version | cut -d' ' -f2)."
echo "  Command:  $HOME/.local/bin/vigil   (add ~/.local/bin to PATH if needed)"
echo "  Editor:   VigilCode Workbench in your applications menu, or: vigil workbench"
echo "  Projects: $projects"
