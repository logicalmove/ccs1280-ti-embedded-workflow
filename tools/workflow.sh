#!/usr/bin/env bash
set -euo pipefail

# Run the Windows CCS compiler workflow from WSL. Hardware access remains in Windows CCS.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$script_dir/workflow.ps1")" "$@"
