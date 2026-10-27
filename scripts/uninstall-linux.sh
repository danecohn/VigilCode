#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
data="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$data/vigilcode" "$data/applications/vigilcode-workbench.desktop"
[ -L "$HOME/.local/bin/vigil" ] && rm "$HOME/.local/bin/vigil"
echo "VigilCode removed. Your projects in ~/VigilCode Projects were left in place."
