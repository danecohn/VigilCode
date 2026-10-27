# SPDX-License-Identifier: GPL-3.0-or-later
$ErrorActionPreference = 'Stop'
$homeDir = Join-Path $env:LOCALAPPDATA 'VigilCode'
$bin = Join-Path $homeDir 'bin'
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $homeDir
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Programs')) 'VigilCode Workbench.lnk')
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) { [Environment]::SetEnvironmentVariable('Path', (($userPath -split ';') | Where-Object { $_ -and $_ -ne $bin }) -join ';', 'User') }
Write-Output 'VigilCode removed. Your projects in VigilCode Projects were left in place.'
