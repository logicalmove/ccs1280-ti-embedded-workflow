---
name: ccs1280-ti-embedded-workflow
description: Use when working with the local C:\ti\ccs1280 Code Composer Studio 12.8.0 installation, TI C2000/DSP/MCU projects, CCS workspaces, .ccsproject/.cproject/.ccxml/.cmd files, F28034/F28335/F28x firmware, DebugServer, DSS, UniFlash, SysConfig, XDCtools, TI compiler builds, flashing, target configuration, or embedded delivery workflows.
---

# CCS1280 TI Embedded Workflow

## Overview

Use the local `C:\ti\ccs1280` tree as a verified TI embedded development environment, not just as an IDE folder. Treat it as four layers: CCS/Eclipse, TI debug/device support, compiler/build tools, and user CCS workspaces.

## Safety Rules

- Do not modify `C:\ti\ccs1280` installation files unless the user explicitly asks.
- Treat workspace projects under `C:\ti\ccs1280\ccs\F28335_PID` as user code, not installer content.
- Before flashing, erasing, unlocking, or writing target memory, get explicit confirmation of target board, emulator, power state, `.ccxml`, and `.out`.
- Exclude `.metadata`, `.jxbrowser.userdata`, `Debug`, and `Release` when summarizing source structure unless generated outputs are specifically relevant.

## Quick Start

1. Verify the base path exists:
   ```powershell
   Test-Path -LiteralPath 'C:\ti\ccs1280'
   ```
2. Read `references/ccs1280-local-map.md` for known local components and project locations.
3. Inventory without changing files:
   ```powershell
   Get-ChildItem -LiteralPath 'C:\ti\ccs1280\ccs' -Force
   Get-Content -LiteralPath 'C:\ti\ccs1280\ccs\.installedComponents.properties'
   Get-Content -LiteralPath 'C:\ti\ccs1280\ccs\.installedProductFamilies'
   ```
4. For CCS projects, inspect `.ccsproject`, `.cproject`, `.project`, `.cmd`, `.ccxml`, source files, and generated `Debug\makefile` if build behavior matters.

## Capability Workflow

### Installation and Component Analysis

- Summarize top-level directories and file counts.
- Read `.installedComponents.properties`, `.installedProductFamilies`, release notes, and tool directories.
- Confirm installed compiler versions with read-only version commands:
  ```powershell
  & 'C:\ti\ccs1280\ccs\tools\compiler\ti-cgt-c2000_22.6.1.LTS\bin\cl2000.exe' --compiler_revision
  & 'C:\ti\ccs1280\ccs\tools\compiler\ti-cgt-armllvm_3.2.2.LTS\bin\tiarmclang.exe' --version
  & 'C:\ti\ccs1280\ccs\utils\sysconfig_1.21.0\sysconfig_cli.bat' --version
  ```

### C2000 Project Analysis

For F28034/F28335/F28x work:

- Inspect linker command files for RAM/FLASH layout, entry points, codestart, interrupt vectors, and peripheral register sections.
- Inspect device support files such as `DSP2803x_*` or `DSP2833x_*`.
- Check ePWM, ADC, GPIO, PIE, SysCtrl, SCI, SPI, I2C, CAN, CPU timer, and ISR setup.
- Verify `EALLOW`/`EDIS` around protected registers and PIEACK/interrupt flag clearing inside ISRs.
- Use map/linkInfo files to diagnose memory overflow, unresolved symbols, wrong RTS library, ABI mismatch, or section placement problems.

### Command-Line Build and Error Triage

- Prefer reproducing IDE builds through generated `Debug\makefile`/`Release\makefile` when present.
- Use compiler paths from `C:\ti\ccs1280\ccs\tools\compiler`.
- For Eclipse/CDT headless builds, use installed `eclipsec.exe`/`ccstudio.exe` only after choosing a workspace and confirming imports will not overwrite user state.
- Report exact command, exit code, and key error lines.

### Debug, Flash, and Automation

- Use `C:\ti\ccs1280\ccs\ccs_base\DebugServer\bin` for DebugServer/DSLite/Flash components.
- Use `C:\ti\ccs1280\ccs\ccs_base\scripting` and `C:\ti\ccs1280\ccs\scripting` for DSS and Node-based scripting references.
- Build scripts that can connect targets, load `.out`, set breakpoints, read/write memory/registers, run/halt/reset, erase/program/verify Flash, and calculate checksums.
- Prefer dry-run inspection first: list operations/options before executing destructive flash operations.

### Target Configuration

- Use `ccs_base\common\targetdb` for devices, boards, CPUs, drivers, and connections.
- Check `.ccxml` against target chip and emulator.
- Common local connections include TI XDS100/XDS110/XDS2xx/XDS560, Blackhawk, SEGGER J-Link, MSP430 USB/FET, Stellaris ICDI, and UART.

## Current Local Projects

Known workspace: `C:\ti\ccs1280\ccs\F28335_PID`

- `8065_d9_board_test_ccs`: F28034/8065 D9 board test project with protocol, platform layer, linker scripts, and `TMS320F28034.ccxml`.
- `F28335_PID`: F28335 PID/ADC/ePWM example with DSP2833x device files and `PID_DEMO.c`.
- `28034test`: F28034/F28035 support/template project with DSP2803x device files.
- `TMS320F28034_Project`: minimal F28034 project skeleton.

## Common Mistakes

| Mistake | Correct action |
|---|---|
| Treating all files as source | Separate installer files, workspace files, caches, and build outputs |
| Editing generated `Debug` files first | Edit source/project settings, then rebuild |
| Flashing from an unverified `.ccxml` | Confirm target device, emulator, board state, and `.out` first |
| Ignoring linker files | Read `.cmd` before diagnosing C2000 build/runtime failures |
| Assuming SDK examples exist locally | Check for C2000Ware/controlSUITE/SDK paths before citing examples |

## Delivery Pattern

When asked to document or preserve work:

1. Record the exact CCS path, project path, compiler version, target config, and output artifact.
2. Write a concise Chinese engineering note if the user is working in Chinese.
3. Keep generated reports on Desktop when requested.
4. Commit/tag/push only in a real Git repo; if the skill directory is not a repo, create or use a separate repository for GitHub delivery.
