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

## Agent Control CLI and Web Console

This repository includes a local CLI and web console for CCS control:

```powershell
python tools\ccs_agent_control\ccs_agent.py status
python tools\ccs_agent_control\ccs_agent.py list-projects
python tools\ccs_agent_control\ccs_agent.py inspect 8065_d9_board_test_ccs
python tools\ccs_agent_control\ccs_agent.py build 8065_d9_board_test_ccs
python tools\ccs_agent_control\ccs_agent.py import C:\path\to\ccs_project
python tools\ccs_agent_control\ccs_agent.py read-expression 8065_d9_board_test_ccs PC
python tools\ccs_agent_control\ccs_agent.py last-log
```

Packaged executable:

```powershell
dist\ccs-agent.exe status
dist\ccs-agent.exe list-projects
dist\ccs-agent.exe inspect 8065_d9_board_test_ccs
dist\ccs-agent.exe build 8065_d9_board_test_ccs
dist\ccs-agent.exe import C:\path\to\ccs_project
dist\ccs-agent.exe last-log
```

Local web console:

```powershell
python -m tools.ccs_agent_control.ccs_agent_ui
dist\ccs-agent-ui.exe
dist\ccs-agent-ui-v2.exe
```

The web console opens `http://127.0.0.1:8765` by default. It provides Chinese UI buttons for project inspection, build, RAM load, run, halt, reset, variable/register reads, Watch lists, and a live DSS debug session used by fast observation mode.

The CLI prints JSON so an agent or a future web service can consume it directly.

Environment overrides:

```powershell
$env:CCS_AGENT_BASE='C:\ti\ccs1280'
$env:CCS_AGENT_WORKSPACE='C:\ti\ccs1280\ccs\F28335_PID'
$env:CCS_AGENT_LOG_DIR='.ccs_agent_logs'
```

Safety boundary:

- Build uses a project Makefile when present, otherwise it falls back to CCS headless project build through `eclipsec.exe` and `com.ti.ccstudio.apps.projectBuild`.
- `load` accepts only RAM `.out` files and rejects FLASH `.out` files.
- Expression reads are restricted to read-only symbol/register paths such as `PC`, `SP`, `GpioDataRegs.GPADAT.all`, or `array[0]`.
- Watch mode can start a live DSS session that loads symbols only and communicates through a local socket.
- The tool does not erase or program Flash.

## Repository Layout

```text
ccs1280-ti-embedded-workflow/
  SKILL.md
  agents/openai.yaml
  references/ccs1280-local-map.md
tools/ccs_agent_control/
  ccs_agent.py
tests/
  test_ccs_agent_control.py
```

## Tagging

Initial release tag: `v0.1.0`
