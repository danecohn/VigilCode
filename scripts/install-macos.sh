#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Per-user install of VigilCode on macOS. No sudo; nothing outside your home folder is changed.
#   - a private Python environment in ~/Library/Application Support/VigilCode
#   - the `vigil` command in ~/.local/bin
#   - "VigilCode Workbench.app" in ~/Applications (no custom icon yet)
# Re-running upgrades the install from this checkout. Remove with scripts/uninstall-macos.sh.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
home_dir="$HOME/Library/Application Support/VigilCode"
app="$HOME/Applications/VigilCode Workbench.app"
command -v python3 >/dev/null || { echo "python3 not found. Install the Xcode command line tools: xcode-select --install" >&2; exit 1; }
command -v clang >/dev/null || command -v cc >/dev/null || { echo "No C compiler found. Install the Xcode command line tools: xcode-select --install" >&2; exit 1; }
mkdir -p "$home_dir" "$HOME/.local/bin" "$HOME/Applications"
python3 -m venv "$home_dir/venv"
"$home_dir/venv/bin/python" -m pip install --quiet --upgrade pip
"$home_dir/venv/bin/python" -m pip install --quiet --upgrade --force-reinstall "$here"
ln -sf "$home_dir/venv/bin/vigil" "$HOME/.local/bin/vigil"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>VigilCode Workbench</string>
<key>CFBundleIdentifier</key><string>org.vigiltech.vigilcode.workbench</string>
<key>CFBundleExecutable</key><string>workbench</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>0.1.0</string>
</dict></plist>
PLIST
cat > "$app/Contents/MacOS/workbench" <<'LAUNCH'
#!/bin/sh
# Starts the local workbench server; if one is already running, just opens it.
url="http://127.0.0.1:8765/"
if /usr/bin/curl -fs -o /dev/null "$url"; then exec /usr/bin/open "$url"; fi
exec "$HOME/Library/Application Support/VigilCode/venv/bin/vigil" workbench --port 8765
LAUNCH
chmod +x "$app/Contents/MacOS/workbench"
echo "Installed VigilCode $("$home_dir/venv/bin/vigil" --version | cut -d' ' -f2)."
echo "  Command:  $HOME/.local/bin/vigil   (add ~/.local/bin to PATH if needed)"
echo "  Editor:   $app"
