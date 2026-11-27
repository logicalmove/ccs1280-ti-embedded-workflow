# CCS1280 TI Embedded Workflow Skill

This repository contains a Codex skill for working with the local TI Code Composer Studio installation at:

`C:\ti\ccs1280`

## What It Covers

- CCS 12.8.0 installation analysis
- TI C2000/DSP/MCU project inspection
- F28034/F28335/F28x firmware workflows
- `.ccsproject`, `.cproject`, `.project`, `.ccxml`, and `.cmd` files
- TI compiler, SysConfig, DebugServer, DSS, UniFlash, and XDCtools usage
- Safe build, debug, flash, target configuration, and delivery procedures
- Fast incremental build loop for the 8065 dual-board IAP project

## Local Installation

The skill has also been installed locally at:

`C:\Users\hjs\.codex\skills\ccs1280-ti-embedded-workflow`

## Validation

Validated with:

```powershell
python C:\Users\hjs\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\hjs\.codex\skills\ccs1280-ti-embedded-workflow
```

Expected output:

```text
Skill is valid!
```

## Fast Build Loop

The project-specific entrypoint is `tools/workflow.ps1` in the active checkout at
`C:\f28035_gpio_zonghe\dual_board_iap`. It reuses matching `.out` and `.map`
artifacts using the existing input fingerprint manifest.

```powershell
cd C:\f28035_gpio_zonghe\dual_board_iap
.\tools\workflow.ps1 -Action plan -Target small
.\tools\workflow.ps1 -Action build -Target small
.\tools\workflow.ps1 -Action verify -Target small
.\tools\workflow.ps1 -Action test
```

From WSL2, use the wrapper:

```bash
bash /mnt/c/f28035_gpio_zonghe/dual_board_iap/tools/workflow.sh \
  -Action plan -Target small
```

The wrapper delegates TI compilation to Windows CCS. It does not connect to an
XDS probe or flash a target. Logs are written to
`C:\f28035_gpio_zonghe\dual_board_iap\build\workflow`.

## Repository Layout

```text
ccs1280-ti-embedded-workflow/
  SKILL.md
  agents/openai.yaml
  references/ccs1280-local-map.md
```

## Tagging

Initial release tag: `v0.1.0`
