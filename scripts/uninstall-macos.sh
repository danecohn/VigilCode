#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
rm -rf "$HOME/Library/Application Support/VigilCode" "$HOME/Applications/VigilCode Workbench.app"
[ -L "$HOME/.local/bin/vigil" ] && rm "$HOME/.local/bin/vigil"
echo "VigilCode removed."
