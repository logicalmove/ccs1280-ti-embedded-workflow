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

## Repository Layout

```text
ccs1280-ti-embedded-workflow/
  SKILL.md
  agents/openai.yaml
  references/ccs1280-local-map.md
```

## Tagging

Initial release tag: `v0.1.0`
