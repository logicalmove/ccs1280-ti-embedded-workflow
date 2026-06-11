# CCS Agent Control V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first local CLI that lets an agent inspect and build CCS projects through safe, auditable commands.

**Architecture:** Add a small Python package under `tools/ccs_agent_control` with a command-line entry point. The CLI discovers CCS workspace projects, inspects key CCS files, runs a safe build command when available, and records the latest operation log under `.ccs_agent_logs`.

**Tech Stack:** Python standard library, `unittest`, PowerShell for local execution.

---

### Task 1: CLI Behavior Tests

**Files:**
- Create: `tests/test_ccs_agent_control.py`

- [x] **Step 1: Define tests for status, project listing, inspection, and logging**

Use temporary directories to emulate `C:\ti\ccs1280` and a CCS workspace. Validate JSON output so agents can consume it reliably.

- [x] **Step 2: Run tests to verify they fail before implementation**

Run: `python -m unittest tests.test_ccs_agent_control -v`

Expected before implementation: import failure for `tools.ccs_agent_control`.

### Task 2: CLI Implementation

**Files:**
- Create: `tools/ccs_agent_control/__init__.py`
- Create: `tools/ccs_agent_control/ccs_agent.py`

- [x] **Step 1: Implement path configuration**

Read defaults from the local CCS layout, with environment overrides for tests:

- `CCS_AGENT_BASE`
- `CCS_AGENT_WORKSPACE`
- `CCS_AGENT_LOG_DIR`

- [x] **Step 2: Implement commands**

Commands:

- `status`
- `list-projects`
- `inspect PROJECT`
- `build PROJECT`
- `last-log`

- [x] **Step 3: Ensure dangerous operations are absent**

V1 must not connect targets, erase flash, program flash, or write memory/registers.

### Task 3: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `ccs1280-ti-embedded-workflow/SKILL.md`

- [x] **Step 1: Document agent CLI usage**

Add command examples and explain that V1 is local-only and avoids destructive operations.

- [x] **Step 2: Run verification**

Run:

```powershell
python -m unittest tests.test_ccs_agent_control -v
python tools\ccs_agent_control\ccs_agent.py status
python tools\ccs_agent_control\ccs_agent.py list-projects
```

Expected: tests pass; real local commands return JSON status/project data.
