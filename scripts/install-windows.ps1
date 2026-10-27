# SPDX-License-Identifier: GPL-3.0-or-later
# Per-user install of VigilCode on Windows. No administrator rights; nothing outside your profile is changed.
#   - a private Python environment in %LOCALAPPDATA%\VigilCode
#   - vigil.cmd in %LOCALAPPDATA%\VigilCode\bin, added to your user PATH
#   - a "VigilCode Workbench" Start menu shortcut (no custom icon yet)
#   - %USERPROFILE%\VigilCode Projects, the folder the workbench opens (created once, never overwritten)
# Needs Python 3.9+ (python.org or winget install Python.Python.3.12) and a C compiler:
# LLVM clang (winget install LLVM.LLVM) with Visual Studio Build Tools, or MinGW-w64 gcc.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSScriptRoot
$homeDir = Join-Path $env:LOCALAPPDATA 'VigilCode'
$bin = Join-Path $homeDir 'bin'
$projects = Join-Path $env:USERPROFILE 'VigilCode Projects'
$python = (Get-Command py -ErrorAction SilentlyContinue)
if ($python) { $pyArgs = @('-3') } else { $python = Get-Command python -ErrorAction SilentlyContinue; $pyArgs = @() }
if (-not $python) { throw 'Python was not found. Install Python 3.9 or later first.' }
if (-not ((Get-Command clang -ErrorAction SilentlyContinue) -or (Get-Command gcc -ErrorAction SilentlyContinue) -or (Get-Command cc -ErrorAction SilentlyContinue))) {
    Write-Warning 'No C compiler (clang or gcc) is on PATH. VigilCode will install, but cannot build programs until one is.'
}
New-Item -ItemType Directory -Force -Path $homeDir, $bin | Out-Null
& $python.Source @pyArgs -m venv (Join-Path $homeDir 'venv')
$venvPython = Join-Path $homeDir 'venv\Scripts\python.exe'
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet --upgrade --force-reinstall $here
if ($LASTEXITCODE -ne 0) { throw 'Installing the VigilCode package failed.' }
Set-Content -Encoding ASCII -Path (Join-Path $bin 'vigil.cmd') -Value "@echo off`r`n`"$homeDir\venv\Scripts\vigil.exe`" %*"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (($userPath -split ';') -contains $bin)) {
    [Environment]::SetEnvironmentVariable('Path', ($(if ($userPath) { "$userPath;$bin" } else { $bin })), 'User')
}
if (-not (Test-Path $projects)) {
    New-Item -ItemType Directory -Path $projects | Out-Null
    Copy-Item (Join-Path $here 'examples\hello.vigil'), (Join-Path $here 'examples\ledger.vigil') $projects
    Copy-Item -Recurse (Join-Path $here 'examples\tally') (Join-Path $projects 'tally')
}
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'VigilCode Workbench.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $homeDir 'venv\Scripts\vigil.exe'
$shortcut.Arguments = "workbench `"$projects`""
$shortcut.WorkingDirectory = $projects
$shortcut.Save()
$version = (& (Join-Path $homeDir 'venv\Scripts\vigil.exe') --version)
Write-Output "Installed $version."
Write-Output "  Command:  vigil   (open a new terminal so PATH includes $bin)"
Write-Output "  Editor:   VigilCode Workbench in the Start menu"
Write-Output "  Projects: $projects"
