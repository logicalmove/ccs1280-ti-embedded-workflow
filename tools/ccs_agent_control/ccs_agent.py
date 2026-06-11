from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE = Path(r"C:\ti\ccs1280")
DEFAULT_WORKSPACE = DEFAULT_BASE / "ccs" / "F28335_PID"


@dataclass(frozen=True)
class Config:
    base_dir: Path
    workspace: Path
    log_dir: Path


@dataclass
class LiveDebugSession:
    config: Config
    project_name: str | None = None
    port: int | None = None
    process: subprocess.Popen[str] | None = None
    script: Path | None = None
    out_file: Path | None = None

    def start(self, project_name: str, out_file: str | None = None, load_program: bool = True) -> dict[str, Any]:
        self.stop()
        project_dir = _project_dir(self.config, project_name)
        _ensure_project_exists(project_dir, project_name)
        dss = self.config.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
        if not dss.exists():
            raise FileNotFoundError(f"DSS launcher not found: {dss}")
        ccxml_files = _relative_files(project_dir, "*.ccxml")
        if not ccxml_files:
            raise FileNotFoundError(f"No .ccxml file found for project: {project_name}")
        selected_out = _select_debug_out(project_dir, out_file) if load_program else _select_symbol_out(project_dir, out_file)
        if selected_out is None:
            raise FileNotFoundError(f"No .out file found for live debug session: {project_name}")
        port = _free_local_port()
        script_path = _write_live_debug_server_script(
            self.config,
            project_dir / ccxml_files[0],
            selected_out,
            port,
            load_program=load_program,
        )
        stdout_file = self.config.log_dir / "live_debug_stdout.log"
        stderr_file = self.config.log_dir / "live_debug_stderr.log"
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        stdout_handle = stdout_file.open("w", encoding="utf-8")
        stderr_handle = stderr_file.open("w", encoding="utf-8")
        process = subprocess.Popen(
            [str(dss), "-dss.workspace", str(self.config.workspace), str(script_path)],
            cwd=project_dir,
            text=True,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        _wait_for_live_port(port, process)
        self.project_name = project_name
        self.port = port
        self.process = process
        self.script = script_path
        self.out_file = selected_out
        return {
            "command": "live-start",
            "project": project_name,
            "port": port,
            "pid": process.pid,
            "script": _path(script_path),
            "out_file": _path(selected_out),
            "load_program": load_program,
        }

    def command(self, name: str, **kwargs: Any) -> dict[str, Any]:
        if self.port is None or self.process is None or self.process.poll() is not None:
            raise RuntimeError("Live debug session is not running")
        request = {"name": name, **kwargs}
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
            reader = sock.makefile("r", encoding="utf-8", newline="\n")
            writer = sock.makefile("w", encoding="utf-8", newline="\n")
            writer.write(json.dumps(request) + "\n")
            writer.flush()
            line = reader.readline()
        if not line:
            raise RuntimeError("Live debug session did not return a response")
        payload = json.loads(line)
        if payload.get("status") != "OK":
            raise RuntimeError(str(payload.get("message", "Live debug command failed")))
        return payload

    def stop(self) -> dict[str, Any]:
        pid = self.process.pid if self.process is not None else None
        if self.port is not None and self.process is not None and self.process.poll() is None:
            try:
                self.command("stop")
            except Exception:
                self.process.terminate()
        if self.process is not None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.project_name = None
        self.port = None
        self.process = None
        self.script = None
        self.out_file = None
        return {"command": "live-stop", "pid": pid}


def default_config() -> Config:
    base_dir = Path(os.environ.get("CCS_AGENT_BASE", str(DEFAULT_BASE)))
    workspace = Path(os.environ.get("CCS_AGENT_WORKSPACE", str(DEFAULT_WORKSPACE)))
    log_dir = Path(os.environ.get("CCS_AGENT_LOG_DIR", str(Path.cwd() / ".ccs_agent_logs")))
    return Config(base_dir=base_dir, workspace=workspace, log_dir=log_dir)


def status(config: Config) -> dict[str, Any]:
    tools = {
        "cl2000": _tool_exists(
            config.base_dir / "ccs" / "tools" / "compiler" / "ti-cgt-c2000_22.6.1.LTS" / "bin" / "cl2000.exe"
        ),
        "gmake": _tool_exists(config.base_dir / "ccs" / "utils" / "bin" / "gmake.exe"),
        "eclipsec": _tool_exists(config.base_dir / "ccs" / "eclipse" / "eclipsec.exe"),
        "dslite": _tool_exists(config.base_dir / "ccs" / "ccs_base" / "DebugServer" / "bin" / "DSLite.exe"),
    }
    return {
        "command": "status",
        "ccs_base": _path(config.base_dir),
        "workspace": _path(config.workspace),
        "log_dir": _path(config.log_dir),
        "ccs_base_exists": config.base_dir.exists(),
        "workspace_exists": config.workspace.exists(),
        "tools": tools,
    }


def list_projects(config: Config) -> dict[str, Any]:
    projects: list[dict[str, Any]] = []
    if config.workspace.exists():
        for child in sorted(config.workspace.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir():
                continue
            project_file = child / ".project"
            ccsproject_file = child / ".ccsproject"
            if not project_file.exists() and not ccsproject_file.exists():
                continue
            if _is_hidden_project(child.name):
                continue
            projects.append(
                {
                    "name": child.name,
                    "path": _path(child),
                    "has_project_file": project_file.exists(),
                    "has_ccsproject_file": ccsproject_file.exists(),
                }
            )
    return {"command": "list-projects", "workspace": _path(config.workspace), "projects": projects}


def inspect_project(config: Config, project_name: str) -> dict[str, Any]:
    project_dir = _project_dir(config, project_name)
    _ensure_project_exists(project_dir, project_name)
    ccxml_files = _relative_files(project_dir, "*.ccxml")
    cmd_files = _relative_files(project_dir, "*.cmd")
    out_files = _relative_files(project_dir, "*.out")
    return {
        "command": "inspect",
        "project": project_name,
        "path": _path(project_dir),
        "project_file": (project_dir / ".project").exists(),
        "ccsproject_file": (project_dir / ".ccsproject").exists(),
        "ccxml_files": ccxml_files,
        "cmd_files": cmd_files,
        "out_files": out_files,
        "build_entrypoints": {
            "makefile": (project_dir / "Makefile").exists() or (project_dir / "makefile").exists(),
            "debug_makefile": (project_dir / "Debug" / "makefile").exists(),
            "release_makefile": (project_dir / "Release" / "makefile").exists(),
        },
    }


def build_project(
    config: Config,
    project_name: str,
    clean: bool = False,
    configuration: str | None = None,
) -> dict[str, Any]:
    project_dir = _project_dir(config, project_name)
    _ensure_project_exists(project_dir, project_name)
    command = _build_command(config, project_dir, project_name, clean=clean, configuration=configuration)
    started = _timestamp()
    completed = subprocess.run(
        command,
        cwd=project_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    diagnostics = _build_diagnostics(project_name, completed.stdout, completed.stderr)
    exit_code = completed.returncode if not diagnostics else 2
    result = {
        "command": "build",
        "project": project_name,
        "path": _path(project_dir),
        "clean": clean,
        "configuration": configuration,
        "argv": command,
        "started_at": started,
        "finished_at": _timestamp(),
        "process_exit_code": completed.returncode,
        "exit_code": exit_code,
        "diagnostics": diagnostics,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _write_log(config, result)
    return result


def import_project(config: Config, project_path: Path | str) -> dict[str, Any]:
    source = Path(project_path)
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Project path not found: {source}")
    if not (source / ".project").exists() and not (source / ".ccsproject").exists():
        raise FileNotFoundError(f"Not a CCS project folder: {source}")
    eclipsec = config.base_dir / "ccs" / "eclipse" / "eclipsec.exe"
    if not eclipsec.exists():
        raise FileNotFoundError(f"CCS eclipsec.exe not found: {eclipsec}")
    command = [
        str(eclipsec),
        "-noSplash",
        "-data",
        str(config.workspace),
        "-application",
        "com.ti.ccstudio.apps.projectImport",
        "-ccs.location",
        str(source),
    ]
    started = _timestamp()
    completed = subprocess.run(
        command,
        cwd=source,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    result = {
        "command": "import",
        "project_path": _path(source),
        "workspace": _path(config.workspace),
        "argv": command,
        "started_at": started,
        "finished_at": _timestamp(),
        "process_exit_code": completed.returncode,
        "exit_code": completed.returncode,
        "diagnostics": [],
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _write_log(config, result)
    return result


def open_project_folder(config: Config, project_name: str) -> dict[str, Any]:
    project_dir = _project_dir(config, project_name)
    _ensure_project_exists(project_dir, project_name)
    os.startfile(str(project_dir))
    return {"command": "open-project", "project": project_name, "folder": _path(project_dir)}


def open_output_folder(config: Config, project_name: str) -> dict[str, Any]:
    project_dir = _project_dir(config, project_name)
    _ensure_project_exists(project_dir, project_name)
    out_files = [project_dir / item for item in _relative_files(project_dir, "*.out")]
    if not out_files:
        raise FileNotFoundError(f"No .out file found for project: {project_name}")
    folder = out_files[0].parent
    os.startfile(str(folder))
    return {"command": "open-output", "project": project_name, "folder": _path(folder)}


def debug_action(config: Config, project_name: str, action: str, out_file: str | None = None) -> dict[str, Any]:
    allowed = {"connect", "load", "run", "halt", "reset", "registers"}
    if action not in allowed:
        raise ValueError(f"Unsupported debug action: {action}")
    project_dir = _project_dir(config, project_name)
    _ensure_project_exists(project_dir, project_name)
    selected_out = _select_debug_out(project_dir, out_file)
    dss = config.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
    if not dss.exists():
        raise FileNotFoundError(f"DSS launcher not found: {dss}")
    ccxml_files = _relative_files(project_dir, "*.ccxml")
    if not ccxml_files:
        raise FileNotFoundError(f"No .ccxml file found for project: {project_name}")
    script_path = _write_debug_script(config, project_dir / ccxml_files[0], selected_out, action)
    started = _timestamp()
    completed = subprocess.run(
        [str(dss), "-dss.workspace", str(config.workspace), str(script_path)],
        cwd=project_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    diagnostics = _debug_diagnostics(completed.stdout, completed.stderr)
    exit_code = completed.returncode if not diagnostics else 2
    result = {
        "command": "debug",
        "project": project_name,
        "action": action,
        "ccxml": _path(project_dir / ccxml_files[0]),
        "out_file": _path(selected_out) if selected_out else None,
        "script": _path(script_path),
        "started_at": started,
        "finished_at": _timestamp(),
        "process_exit_code": completed.returncode,
        "exit_code": exit_code,
        "diagnostics": diagnostics,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _write_log(config, result)
    return result


def read_expression(
    config: Config,
    project_name: str,
    expression: str,
    out_file: str | None = None,
    halt: bool = True,
) -> dict[str, Any]:
    expression = _validate_read_expression(expression)
    project_dir = _project_dir(config, project_name)
    _ensure_project_exists(project_dir, project_name)
    selected_out = _select_symbol_out(project_dir, out_file)
    dss = config.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
    if not dss.exists():
        raise FileNotFoundError(f"DSS launcher not found: {dss}")
    ccxml_files = _relative_files(project_dir, "*.ccxml")
    if not ccxml_files:
        raise FileNotFoundError(f"No .ccxml file found for project: {project_name}")
    script_path = _write_expression_script(config, project_dir / ccxml_files[0], selected_out, expression, halt=halt)
    started = _timestamp()
    completed = subprocess.run(
        [str(dss), "-dss.workspace", str(config.workspace), str(script_path)],
        cwd=project_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    diagnostics = _debug_diagnostics(completed.stdout, completed.stderr)
    exit_code = completed.returncode if not diagnostics else 2
    result = {
        "command": "read-expression",
        "project": project_name,
        "expression": expression,
        "value": _output_value(completed.stdout, "VALUE"),
        "halt": halt,
        "ccxml": _path(project_dir / ccxml_files[0]),
        "out_file": _path(selected_out) if selected_out else None,
        "script": _path(script_path),
        "started_at": started,
        "finished_at": _timestamp(),
        "process_exit_code": completed.returncode,
        "exit_code": exit_code,
        "diagnostics": diagnostics,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _write_log(config, result)
    return result


def read_expressions(
    config: Config,
    project_name: str,
    expressions: list[str],
    out_file: str | None = None,
    halt: bool = True,
) -> dict[str, Any]:
    validated = [_validate_read_expression(expression) for expression in expressions]
    if not validated:
        raise ValueError("At least one expression is required")
    project_dir = _project_dir(config, project_name)
    _ensure_project_exists(project_dir, project_name)
    selected_out = _select_symbol_out(project_dir, out_file)
    dss = config.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
    if not dss.exists():
        raise FileNotFoundError(f"DSS launcher not found: {dss}")
    ccxml_files = _relative_files(project_dir, "*.ccxml")
    if not ccxml_files:
        raise FileNotFoundError(f"No .ccxml file found for project: {project_name}")
    script_path = _write_expressions_script(config, project_dir / ccxml_files[0], selected_out, validated, halt=halt)
    started = _timestamp()
    completed = subprocess.run(
        [str(dss), "-dss.workspace", str(config.workspace), str(script_path)],
        cwd=project_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    diagnostics = _debug_diagnostics(completed.stdout, completed.stderr)
    exit_code = completed.returncode if not diagnostics else 2
    result = {
        "command": "read-expressions",
        "project": project_name,
        "expressions": validated,
        "values": _output_values(completed.stdout),
        "halt": halt,
        "ccxml": _path(project_dir / ccxml_files[0]),
        "out_file": _path(selected_out) if selected_out else None,
        "script": _path(script_path),
        "started_at": started,
        "finished_at": _timestamp(),
        "process_exit_code": completed.returncode,
        "exit_code": exit_code,
        "diagnostics": diagnostics,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _write_log(config, result)
    return result


def last_log(config: Config) -> dict[str, Any]:
    log_file = config.log_dir / "last.json"
    if not log_file.exists():
        return {"command": "last-log", "log_file": _path(log_file), "last_entry": None}
    return {
        "command": "last-log",
        "log_file": _path(log_file),
        "last_entry": json.loads(log_file.read_text(encoding="utf-8")),
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(_quick_start_text())
        _pause_if_double_clicked()
        return 0

    parser = argparse.ArgumentParser(description="Agent-safe local CCS control CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("list-projects")
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("project")
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("project")
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("path")
    read_parser = subparsers.add_parser("read-expression")
    read_parser.add_argument("project")
    read_parser.add_argument("expression")
    read_parser.add_argument("--out-file")
    read_parser.add_argument("--no-halt", action="store_true")
    subparsers.add_parser("last-log")
    args = parser.parse_args(argv)
    config = default_config()

    try:
        if args.command == "status":
            payload = status(config)
        elif args.command == "list-projects":
            payload = list_projects(config)
        elif args.command == "inspect":
            payload = inspect_project(config, args.project)
        elif args.command == "build":
            payload = build_project(config, args.project)
        elif args.command == "import":
            payload = import_project(config, args.path)
        elif args.command == "read-expression":
            payload = read_expression(config, args.project, args.expression, out_file=args.out_file, halt=not args.no_halt)
        elif args.command == "last-log":
            payload = last_log(config)
        else:
            raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:
        payload = {"command": args.command, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.command in {"build", "import", "read-expression"}:
        return int(payload["exit_code"])
    return 0


def _tool_exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def _is_hidden_project(name: str) -> bool:
    return name == "RemoteSystemsTempFiles" or name.endswith("'")


def _select_debug_out(project_dir: Path, out_file: str | None) -> Path | None:
    if out_file:
        if "FLASH" in out_file.upper():
            raise ValueError("Refusing to load FLASH output in safe simulation mode; use a RAM .out file.")
        candidate = project_dir / out_file
        if not candidate.exists():
            raise FileNotFoundError(f"Output file not found: {candidate}")
        return candidate
    ram_outputs = [project_dir / item for item in _relative_files(project_dir, "*.out") if "RAM" in item.upper()]
    return ram_outputs[0] if ram_outputs else None


def _select_symbol_out(project_dir: Path, out_file: str | None) -> Path | None:
    if out_file:
        candidate = project_dir / out_file
        if not candidate.exists():
            raise FileNotFoundError(f"Output file not found: {candidate}")
        return candidate
    outputs = [project_dir / item for item in _relative_files(project_dir, "*.out")]
    ram_outputs = [item for item in outputs if "RAM" in _slash(item.relative_to(project_dir)).upper()]
    return (ram_outputs or outputs)[0] if outputs else None


def _write_debug_script(config: Config, ccxml: Path, out_file: Path | None, action: str) -> Path:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    script_path = config.log_dir / f"dss_{action}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.js"
    load_line = ""
    if action == "load":
        if out_file is None:
            raise FileNotFoundError("No RAM .out file found for load action.")
        load_line = f'session.memory.loadProgram("{_js_path(out_file)}");\n    print("Loaded OUT={_js_path(out_file)}");'
    action_lines = {
        "connect": 'print("Connected");',
        "load": load_line,
        "run": 'session.target.runAsynch();\n    print("Run started");',
        "halt": 'session.target.halt();\n    print("Halted");',
        "reset": 'session.target.reset();\n    print("Reset complete");',
        "registers": 'session.target.halt();\n    print("PC=" + session.memory.readRegister("PC"));\n    print("SP=" + session.memory.readRegister("SP"));',
    }[action]
    script = f'''importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);

var env = ScriptingEnvironment.instance();
env.setScriptTimeout(20000);
var server = null;
var session = null;
try {{
    print("DSS_ACTION={action}");
    print("CCXML={_js_path(ccxml)}");
    server = env.getServer("DebugServer.1");
    server.setConfig("{_js_path(ccxml)}");
    session = server.openSession(".*C28.*");
    session.target.connect();
    session.options.setBoolean("AutoRunToLabelOnRestart", false);
    session.options.setBoolean("AutoRunToLabelOnReset", false);
    {action_lines}
}} finally {{
    if (session != null) {{
        try {{ session.target.disconnect(); }} catch (ignore1) {{}}
        try {{ session.terminate(); }} catch (ignore2) {{}}
    }}
    if (server != null) {{
        try {{ server.stop(); }} catch (ignore3) {{}}
    }}
}}
'''
    script_path.write_text(script, encoding="utf-8")
    return script_path


def _write_expression_script(config: Config, ccxml: Path, out_file: Path | None, expression: str, halt: bool = True) -> Path:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    script_path = config.log_dir / f"dss_read_expression_{datetime.now().strftime('%Y%m%d_%H%M%S')}.js"
    symbol_load_line = ""
    if out_file is not None:
        symbol_load_line = f'session.symbol.load("{_js_path(out_file)}");\n    print("SYMBOLS={_js_path(out_file)}");'
    halt_line = 'session.target.halt();\n    print("HALT_BEFORE_READ=1");' if halt else 'print("HALT_BEFORE_READ=0");'
    script = f'''importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);

var env = ScriptingEnvironment.instance();
env.setScriptTimeout(20000);
var server = null;
var session = null;
try {{
    print("DSS_ACTION=read-expression");
    print("CCXML={_js_path(ccxml)}");
    print("EXPRESSION={expression}");
    server = env.getServer("DebugServer.1");
    server.setConfig("{_js_path(ccxml)}");
    session = server.openSession(".*C28.*");
    session.target.connect();
    session.options.setBoolean("AutoRunToLabelOnRestart", false);
    session.options.setBoolean("AutoRunToLabelOnReset", false);
    {symbol_load_line}
    {halt_line}
    var value = session.expression.evaluateToString("{_js_string(expression)}");
    print("VALUE=" + value);
}} finally {{
    if (session != null) {{
        try {{ session.target.disconnect(); }} catch (ignore1) {{}}
        try {{ session.terminate(); }} catch (ignore2) {{}}
    }}
    if (server != null) {{
        try {{ server.stop(); }} catch (ignore3) {{}}
    }}
}}
'''
    script_path.write_text(script, encoding="utf-8")
    return script_path


def _write_expressions_script(
    config: Config,
    ccxml: Path,
    out_file: Path | None,
    expressions: list[str],
    halt: bool = True,
) -> Path:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    script_path = config.log_dir / f"dss_read_expressions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.js"
    symbol_load_line = ""
    if out_file is not None:
        symbol_load_line = f'session.symbol.load("{_js_path(out_file)}");\n    print("SYMBOLS={_js_path(out_file)}");'
    halt_line = 'session.target.halt();\n    print("HALT_BEFORE_READ=1");' if halt else 'print("HALT_BEFORE_READ=0");'
    read_lines = "\n".join(
        f'    print("VALUE[{_js_string(expression)}]=" + session.expression.evaluateToString("{_js_string(expression)}"));'
        for expression in expressions
    )
    script = f'''importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);

var env = ScriptingEnvironment.instance();
env.setScriptTimeout(20000);
var server = null;
var session = null;
try {{
    print("DSS_ACTION=read-expressions");
    print("CCXML={_js_path(ccxml)}");
    server = env.getServer("DebugServer.1");
    server.setConfig("{_js_path(ccxml)}");
    session = server.openSession(".*C28.*");
    session.target.connect();
    session.options.setBoolean("AutoRunToLabelOnRestart", false);
    session.options.setBoolean("AutoRunToLabelOnReset", false);
    {symbol_load_line}
    {halt_line}
{read_lines}
}} finally {{
    if (session != null) {{
        try {{ session.target.disconnect(); }} catch (ignore1) {{}}
        try {{ session.terminate(); }} catch (ignore2) {{}}
    }}
    if (server != null) {{
        try {{ server.stop(); }} catch (ignore3) {{}}
    }}
}}
'''
    script_path.write_text(script, encoding="utf-8")
    return script_path


def _write_live_debug_server_script(
    config: Config,
    ccxml: Path,
    out_file: Path,
    port: int,
    load_program: bool = True,
) -> Path:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    script_path = config.log_dir / f"dss_live_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.js"
    setup_line = (
        f'session.memory.loadProgram("{_js_path(out_file)}");\n    print("LOADED={_js_path(out_file)}");'
        if load_program
        else f'session.symbol.load("{_js_path(out_file)}");\n    print("SYMBOLS={_js_path(out_file)}");'
    )
    json2_path = config.base_dir / "ccs" / "ccs_base" / "scripting" / "examples" / "TestServer" / "json2.js"
    script = f'''importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);
importPackage(Packages.java.net);
importPackage(Packages.java.io);

load("{_js_path(json2_path)}");

var env = ScriptingEnvironment.instance();
env.setScriptTimeout(0);
var server = null;
var session = null;
var serverSocket = null;
try {{
    print("DSS_ACTION=live-debug");
    print("CCXML={_js_path(ccxml)}");
    server = env.getServer("DebugServer.1");
    server.setConfig("{_js_path(ccxml)}");
    session = server.openSession(".*C28.*");
    session.target.connect();
    session.options.setBoolean("AutoRunToLabelOnRestart", false);
    session.options.setBoolean("AutoRunToLabelOnReset", false);
    {setup_line}
    serverSocket = new ServerSocket({port});
    print("LIVE_READY={port}");
    var keepRunning = true;
    while (keepRunning) {{
        var client = serverSocket.accept();
        var input = new BufferedReader(new InputStreamReader(client.getInputStream()));
        var output = new PrintWriter(client.getOutputStream(), true);
        var line = input.readLine();
        try {{
            var command = eval("(" + line + ")");
            var response = handleCommand(command);
            output.println(JSON.stringify(response));
            if (command.name == "stop") {{
                keepRunning = false;
            }}
        }} catch (err) {{
            output.println(JSON.stringify({{status:"FAIL", message:String(err)}}));
        }}
        input.close();
        output.close();
        client.close();
    }}
}} finally {{
    if (serverSocket != null) {{
        try {{ serverSocket.close(); }} catch (ignore0) {{}}
    }}
    if (session != null) {{
        try {{ session.target.disconnect(); }} catch (ignore1) {{}}
        try {{ session.terminate(); }} catch (ignore2) {{}}
    }}
    if (server != null) {{
        try {{ server.stop(); }} catch (ignore3) {{}}
    }}
}}

function handleCommand(command) {{
    if (command.name == "run") {{
        session.target.runAsynch();
        return {{status:"OK", running:true}};
    }}
    if (command.name == "halt") {{
        session.target.halt();
        return {{status:"OK", halted:true}};
    }}
    if (command.name == "reset") {{
        session.target.reset();
        return {{status:"OK", reset:true}};
    }}
    if (command.name == "watch") {{
        var values = {{}};
        for (var i = 0; i < command.expressions.length; i++) {{
            var expr = command.expressions[i];
            values[expr] = String(session.expression.evaluateToString(expr));
        }}
        return {{status:"OK", values:values}};
    }}
    if (command.name == "stop") {{
        return {{status:"OK"}};
    }}
    return {{status:"FAIL", message:"Unsupported command: " + command.name}};
}}
'''
    script_path.write_text(script, encoding="utf-8")
    return script_path


def _js_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _js_string(value: str) -> str:
    return json.dumps(value)[1:-1]


def _validate_read_expression(expression: str) -> str:
    expression = expression.strip()
    if not expression:
        raise ValueError("Expression is required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\])*", expression):
        raise ValueError(
            "Expression must be a read-only symbol/register path like PC, SP, GpioDataRegs.GPADAT.all, or array[0]."
        )
    return expression


def _project_dir(config: Config, project_name: str) -> Path:
    if Path(project_name).name != project_name:
        raise ValueError("Project name must not contain path separators")
    return config.workspace / project_name


def _ensure_project_exists(project_dir: Path, project_name: str) -> None:
    if not project_dir.exists() or not project_dir.is_dir():
        raise FileNotFoundError(f"Project not found: {project_name}")


def _relative_files(root: Path, pattern: str) -> list[str]:
    return sorted(_slash(path.relative_to(root)) for path in root.rglob(pattern) if path.is_file())


def _build_command(
    config: Config,
    project_dir: Path,
    project_name: str,
    clean: bool = False,
    configuration: str | None = None,
) -> list[str]:
    makefile = project_dir / "Makefile"
    lower_makefile = project_dir / "makefile"
    if makefile.exists() or lower_makefile.exists():
        gmake = config.base_dir / "ccs" / "utils" / "bin" / "gmake.exe"
        if gmake.exists():
            return [str(gmake)]
        return ["make"]
    eclipsec = config.base_dir / "ccs" / "eclipse" / "eclipsec.exe"
    if eclipsec.exists():
        command = [
            str(eclipsec),
            "-noSplash",
            "-data",
            str(config.workspace),
            "-application",
            "com.ti.ccstudio.apps.projectBuild",
            "-ccs.autoImport",
            "-ccs.projects",
            project_name,
        ]
        if clean:
            command.append("-ccs.clean")
        if configuration:
            command.extend(["-ccs.configuration", configuration])
        return command
    raise FileNotFoundError("No Makefile or CCS eclipsec.exe found for build command")


def _write_log(config: Config, payload: dict[str, Any]) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    numbered_log = config.log_dir / f"{timestamp}_{payload['command']}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    numbered_log.write_text(text, encoding="utf-8")
    (config.log_dir / "last.json").write_text(text, encoding="utf-8")


def _build_diagnostics(project_name: str, stdout: str, stderr: str) -> list[str]:
    combined = f"{stdout}\n{stderr}"
    diagnostics: list[str] = []
    if f"Project '{project_name}' was not found in the workspace" in combined:
        diagnostics.append("CCS did not build the requested project because it was not found in the workspace.")
    if "0 out of 0 projects have errors" in combined:
        diagnostics.append("CCS did not build the requested project; headless build reported 0 projects.")
    return diagnostics


def _debug_diagnostics(stdout: str, stderr: str) -> list[str]:
    combined = f"{stdout}\n{stderr}"
    lower = combined.lower()
    diagnostics: list[str] = []
    failure_markers = [
        "severe:",
        "exception",
        "targetconnectionexception",
        "error connecting",
        "failed to connect",
    ]
    if any(marker in lower for marker in failure_markers):
        diagnostics.append("DSS reported a debug failure even though the launcher returned process exit code 0.")
    target_markers = [
        "target is held in reset",
        "target did not respond",
        "no response from the target",
        "unable to access the dap",
        "error connecting to the target",
    ]
    if any(marker in lower for marker in target_markers):
        diagnostics.append(
            "The target did not respond. Check board power, reset/boot pins, XDS100v2 connection, and that the .ccxml matches F28034."
        )
    return diagnostics


def _output_value(stdout: str, key: str) -> str | None:
    prefix = f"{key}="
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _output_values(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        match = re.match(r"VALUE\[(.+)\]=(.*)", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_live_port(port: int, process: subprocess.Popen[str], timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Live DSS process exited early with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for live DSS session on port {port}: {last_error}")


def _quick_start_text() -> str:
    return """CCS Agent Control

Usage:
  ccs-agent.exe status
  ccs-agent.exe list-projects
  ccs-agent.exe inspect 8065_d9_board_test_ccs
  ccs-agent.exe build 8065_d9_board_test_ccs
  ccs-agent.exe last-log

Note:
  Run this tool from PowerShell or let an agent call it with arguments.
  Double-clicking only shows this quick start; it does not build a project.
"""


def _pause_if_double_clicked() -> None:
    if getattr(sys, "frozen", False) and sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(path: Path) -> str:
    return str(path)


def _slash(path: Path) -> str:
    return path.as_posix()


if __name__ == "__main__":
    sys.exit(main())
