from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from tools.ccs_agent_control import ccs_agent


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def make_handler(config: ccs_agent.Config):
    live_session = ccs_agent.LiveDebugSession(config)

    class CcsAgentHandler(BaseHTTPRequestHandler):
        server_version = "CcsAgentUi/1.0"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._send_html(INDEX_HTML)
                elif parsed.path == "/api/status":
                    self._send_json(ccs_agent.status(config))
                elif parsed.path == "/api/projects":
                    self._send_json(ccs_agent.list_projects(config))
                elif parsed.path == "/api/inspect":
                    project = _query_value(parsed.query, "project")
                    if not project:
                        self._send_json({"error": "Missing project query parameter"}, status=400)
                        return
                    self._send_json(ccs_agent.inspect_project(config, project))
                elif parsed.path == "/api/last-log":
                    self._send_json(ccs_agent.last_log(config))
                else:
                    self._send_json({"error": f"Not found: {parsed.path}"}, status=404)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/build":
                    body = self._read_json()
                    project = str(body.get("project", "")).strip()
                    clean = bool(body.get("clean", False))
                    configuration = str(body.get("configuration", "")).strip() or None
                    if not project:
                        self._send_json({"error": "Missing project"}, status=400)
                        return
                    payload = ccs_agent.build_project(config, project, clean=clean, configuration=configuration)
                    status = 200 if int(payload.get("exit_code", 1)) == 0 else 500
                    self._send_json(payload, status=status)
                elif parsed.path == "/api/import":
                    body = self._read_json()
                    project_path = str(body.get("path", "")).strip()
                    if not project_path:
                        self._send_json({"error": "Missing path"}, status=400)
                        return
                    payload = ccs_agent.import_project(config, project_path)
                    status = 200 if int(payload.get("exit_code", 1)) == 0 else 500
                    self._send_json(payload, status=status)
                elif parsed.path == "/api/open-project":
                    project = self._project_from_body()
                    if not project:
                        self._send_json({"error": "Missing project"}, status=400)
                        return
                    self._send_json(ccs_agent.open_project_folder(config, project))
                elif parsed.path == "/api/open-output":
                    project = self._project_from_body()
                    if not project:
                        self._send_json({"error": "Missing project"}, status=400)
                        return
                    self._send_json(ccs_agent.open_output_folder(config, project))
                elif parsed.path == "/api/debug":
                    body = self._read_json()
                    project = str(body.get("project", "")).strip()
                    action = str(body.get("action", "")).strip()
                    out_file = str(body.get("out_file", "")).strip() or None
                    if not project or not action:
                        self._send_json({"error": "Missing project or action"}, status=400)
                        return
                    payload = ccs_agent.debug_action(config, project, action, out_file=out_file)
                    status = 200 if int(payload.get("exit_code", 1)) == 0 else 500
                    self._send_json(payload, status=status)
                elif parsed.path == "/api/read-expression":
                    body = self._read_json()
                    project = str(body.get("project", "")).strip()
                    expression = str(body.get("expression", "")).strip()
                    out_file = str(body.get("out_file", "")).strip() or None
                    halt = bool(body.get("halt", True))
                    if not project or not expression:
                        self._send_json({"error": "Missing project or expression"}, status=400)
                        return
                    payload = ccs_agent.read_expression(config, project, expression, out_file=out_file, halt=halt)
                    status = 200 if int(payload.get("exit_code", 1)) == 0 else 500
                    self._send_json(payload, status=status)
                elif parsed.path == "/api/read-expressions":
                    body = self._read_json()
                    project = str(body.get("project", "")).strip()
                    expressions = [str(item).strip() for item in body.get("expressions", []) if str(item).strip()]
                    out_file = str(body.get("out_file", "")).strip() or None
                    halt = bool(body.get("halt", True))
                    if not project or not expressions:
                        self._send_json({"error": "Missing project or expressions"}, status=400)
                        return
                    payload = ccs_agent.read_expressions(config, project, expressions, out_file=out_file, halt=halt)
                    status = 200 if int(payload.get("exit_code", 1)) == 0 else 500
                    self._send_json(payload, status=status)
                elif parsed.path == "/api/live/start":
                    body = self._read_json()
                    project = str(body.get("project", "")).strip()
                    out_file = str(body.get("out_file", "")).strip() or None
                    load_program = bool(body.get("load_program", True))
                    if not project:
                        self._send_json({"error": "Missing project"}, status=400)
                        return
                    self._send_json(live_session.start(project, out_file=out_file, load_program=load_program))
                elif parsed.path == "/api/live/command":
                    body = self._read_json()
                    name = str(body.get("name", "")).strip()
                    expressions = [str(item).strip() for item in body.get("expressions", []) if str(item).strip()]
                    if not name:
                        self._send_json({"error": "Missing command name"}, status=400)
                        return
                    payload = live_session.command(name, expressions=expressions) if name == "watch" else live_session.command(name)
                    self._send_json({"command": f"live-{name}", **payload})
                elif parsed.path == "/api/live/stop":
                    self._send_json(live_session.stop())
                else:
                    self._send_json({"error": f"Not found: {parsed.path}"}, status=404)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)

        def _project_from_body(self) -> str:
            body = self._read_json()
            return str(body.get("project", "")).strip()

        def _send_html(self, body: str, status: int = 200) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return CcsAgentHandler


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> ThreadingHTTPServer:
    config = ccs_agent.default_config()
    server = ThreadingHTTPServer((host, port), make_handler(config))
    url = f"http://{host}:{server.server_address[1]}"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"CCS Agent Console running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping CCS Agent Console.")
    finally:
        server.server_close()
    return server


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="Local web UI for CCS Agent Control")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def _query_value(query: str, name: str) -> str:
    values = parse_qs(query).get(name, [])
    return values[0].strip() if values else ""


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CCS Agent Console</title>
  <style>
    :root {
      --bg: #f6f2ea;
      --panel: #fffaf0;
      --ink: #202124;
      --muted: #6a6257;
      --line: #d8cdbd;
      --green: #157a43;
      --red: #b42318;
      --blue: #175cd3;
      --dark: #181410;
      --gold: #b7791f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    header {
      min-height: 108px;
      padding: 24px 32px 18px;
      background: var(--dark);
      color: #fff8e8;
      border-bottom: 4px solid var(--gold);
    }
    h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 760;
    }
    .subtitle {
      margin-top: 8px;
      color: #d9c7a6;
      font-size: 14px;
    }
    main {
      display: grid;
      grid-template-columns: 330px minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
      max-width: 1440px;
      margin: 0 auto;
    }
    section, aside {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }
    aside {
      padding: 14px;
      height: calc(100vh - 148px);
      min-height: 520px;
      overflow: auto;
    }
    .workspace {
      padding: 14px;
      min-height: calc(100vh - 148px);
    }
    .toolbar {
      display: grid;
      grid-template-columns: repeat(7, minmax(104px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    button {
      border: 1px solid #ab9b82;
      background: #fff4d8;
      color: #20160c;
      border-radius: 6px;
      min-height: 42px;
      padding: 8px 10px;
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { background: #ffe9ad; }
    button.primary {
      background: #1f5f3b;
      color: white;
      border-color: #17472d;
    }
    button.danger {
      background: #7a271a;
      color: white;
      border-color: #5f1d13;
    }
    .label {
      margin: 14px 0 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .project-list {
      display: grid;
      gap: 8px;
    }
    input {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fffdf8;
      color: var(--ink);
      font: 13px "Segoe UI", "Microsoft YaHei", sans-serif;
    }
    select {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fffdf8;
      color: var(--ink);
      font: 13px "Segoe UI", "Microsoft YaHei", sans-serif;
    }
    .project {
      width: 100%;
      text-align: left;
      background: #fffaf0;
      border-color: var(--line);
      font-weight: 650;
      overflow-wrap: anywhere;
    }
    .project.active {
      border-color: var(--blue);
      background: #eaf1ff;
    }
    .status-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fffcf6;
      min-height: 72px;
    }
    .metric strong {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .ok { color: var(--green); font-weight: 800; }
    .bad { color: var(--red); font-weight: 800; }
    .split {
      display: grid;
      grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.4fr);
      gap: 14px;
    }
    .debug-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(120px, 1fr));
      gap: 8px;
      margin-top: 12px;
    }
    pre {
      margin: 0;
      min-height: 220px;
      max-height: calc(100vh - 520px);
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #151515;
      color: #f2eadf;
      border-radius: 8px;
      padding: 14px;
      font: 12px/1.55 Consolas, "Cascadia Mono", monospace;
    }
    .details {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fffcf6;
      padding: 12px;
      min-height: 360px;
    }
    .summary {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fffcf6;
      padding: 14px;
      margin-bottom: 12px;
      min-height: 126px;
    }
    .summary h2 {
      margin: 0 0 8px;
      font-size: 20px;
    }
    .summary p {
      margin: 5px 0;
      color: var(--muted);
    }
    .value-readout {
      display: block;
      margin-top: 10px;
      padding: 12px;
      border: 1px solid #c7b99e;
      border-radius: 6px;
      background: #fff7e6;
      color: #151515;
      font: 16px/1.5 Consolas, "Cascadia Mono", monospace;
      overflow-wrap: anywhere;
    }
    .watch-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      font-size: 13px;
    }
    .watch-table th,
    .watch-table td {
      border-bottom: 1px solid #eadfce;
      padding: 8px 6px;
      text-align: left;
      vertical-align: top;
    }
    .watch-table td:last-child {
      font-family: Consolas, "Cascadia Mono", monospace;
      overflow-wrap: anywhere;
    }
    details {
      border-radius: 8px;
    }
    summary {
      cursor: pointer;
      font-weight: 800;
      margin-bottom: 8px;
      color: var(--muted);
    }
    .details code {
      display: block;
      padding: 7px 0;
      border-bottom: 1px solid #eadfce;
      overflow-wrap: anywhere;
    }
    @media (max-width: 920px) {
      main, .split { grid-template-columns: 1fr; }
      aside { height: auto; min-height: 0; }
      .toolbar, .status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <h1>CCS 调试控制台</h1>
    <div class="subtitle">用于 F28034 工程构建、RAM 调试、变量和寄存器读取</div>
  </header>
  <main>
    <aside>
      <button class="primary" onclick="refreshAll()">刷新</button>
      <div class="label">工作区</div>
      <code id="workspacePath">正在加载...</code>
      <div class="label">导入工程目录</div>
      <input id="importPath" placeholder="C:\path\to\ccs_project">
      <button onclick="importProject()">导入</button>
      <div class="label">构建配置</div>
      <select id="buildConfig">
        <option value="CPU1_RAM">CPU1_RAM</option>
        <option value="CPU1_FLASH">CPU1_FLASH</option>
      </select>
      <div class="label">工程列表</div>
      <div id="projects" class="project-list"></div>
    </aside>
    <section class="workspace">
      <div class="toolbar">
        <button onclick="loadStatus()">状态</button>
        <button onclick="loadProjects()">工程</button>
        <button onclick="inspectSelected()">检查文件</button>
        <button class="danger" onclick="buildSelected()">构建</button>
        <button onclick="cleanSelected()">清理</button>
        <button onclick="rebuildSelected()">重新构建</button>
        <button onclick="loadLastLog()">最近日志</button>
        <button onclick="openProjectFolder()">打开工程</button>
        <button onclick="openOutputFolder()">打开输出</button>
      </div>
      <div class="status-grid" id="statusGrid"></div>
      <div class="split">
        <div class="details">
          <div class="label">当前工程</div>
          <code id="selectedProject">8065_d9_board_test_ccs</code>
          <div class="label">工程文件</div>
          <div id="fileSummary">还没有检查工程文件。</div>
          <div class="label">安全调试</div>
          <div class="debug-grid">
            <button onclick="debugAction('connect')">连接目标</button>
            <button onclick="debugAction('load')">加载 RAM</button>
            <button onclick="debugAction('registers')">读 PC/SP</button>
            <button onclick="debugAction('run')">运行</button>
            <button onclick="debugAction('halt')">暂停</button>
            <button onclick="debugAction('reset')">复位</button>
          </div>
          <div class="label">变量 / 寄存器</div>
          <input id="expressionInput" value="GpioDataRegs.GPADAT.all">
          <button onclick="readExpression()">读取</button>
          <div class="label">监视列表</div>
          <input id="watchInput" value="GpioDataRegs.GPADAT.all">
          <div class="debug-grid">
            <button onclick="addWatch()">加入</button>
            <button class="primary" onclick="startWatchMode()">开始观察</button>
            <button onclick="stopWatchMode()">停止观察</button>
            <button onclick="stopLiveSession()">退出快速会话</button>
          </div>
          <div id="watchStatus" class="label">未启动</div>
          <table class="watch-table">
            <thead><tr><th>变量/寄存器</th><th>当前值</th></tr></thead>
            <tbody id="watchTable"></tbody>
          </table>
        </div>
        <div>
          <div class="summary" id="summary">
            <h2>就绪</h2>
            <p>选择工程后，可以构建、加载 RAM、读取变量或寄存器。</p>
          </div>
          <details>
            <summary>原始日志</summary>
            <pre id="output">就绪。</pre>
          </details>
          <div class="toolbar" style="grid-template-columns: repeat(2, minmax(120px, 1fr)); margin-top: 10px;">
            <button onclick="copyRawLog()">复制日志</button>
            <button onclick="clearResult()">清空</button>
          </div>
        </div>
      </div>
    </section>
  </main>
  <script>
    let selectedProject = "8065_d9_board_test_ccs";
    let watchList = ["PC", "SP", "GpioDataRegs.GPADAT.all"];
    let watchTimer = null;
    let watchActive = false;
    let watchSampling = false;
    let liveActive = false;
    let cachedRamOut = "";

    function show(payload) {
      document.getElementById("output").textContent = JSON.stringify(payload, null, 2);
      renderSummary(payload);
    }

    function renderSummary(payload) {
      const box = document.getElementById("summary");
      if (payload.error) {
        box.innerHTML = `<h2 class="bad">错误</h2><p>${escapeHtml(payload.error)}</p>`;
        return;
      }
      if (payload.message) {
        box.innerHTML = `<h2>执行中</h2><p>${escapeHtml(payload.message)}</p>`;
        return;
      }
      if (payload.command === "status") {
        box.innerHTML = `<h2>状态正常</h2><p>工作区：${escapeHtml(payload.workspace || "")}</p><p>CCS 工具状态见上方。</p>`;
        document.getElementById("workspacePath").textContent = payload.workspace || "";
        return;
      }
      if (payload.command === "list-projects") {
        box.innerHTML = `<h2>工程已加载</h2><p>找到 ${(payload.projects || []).length} 个工程。</p><p>工作区：${escapeHtml(payload.workspace || "")}</p>`;
        return;
      }
      if (payload.command === "inspect") {
        box.innerHTML = `<h2>工程检查完成</h2><p>${escapeHtml(payload.project || "")}</p><p>${(payload.out_files || []).length} 个 .out，${(payload.cmd_files || []).length} 个 .cmd。</p>`;
        return;
      }
      if (payload.command === "build") {
        const ok = Number(payload.exit_code) === 0;
        const result = ok ? "构建成功" : "构建失败";
        const cls = ok ? "ok" : "bad";
        const line = summarizeBuild(payload);
        box.innerHTML = `<h2 class="${cls}">${result}</h2><p>工程：${escapeHtml(payload.project || "")}</p><p>${escapeHtml(line)}</p>`;
        return;
      }
      if (payload.command === "import") {
        const ok = Number(payload.exit_code) === 0;
        box.innerHTML = `<h2 class="${ok ? "ok" : "bad"}">${ok ? "导入成功" : "导入失败"}</h2><p>${escapeHtml(payload.project_path || "")}</p><p>工作区：${escapeHtml(payload.workspace || "")}</p>`;
        return;
      }
      if (payload.command === "debug") {
        const ok = Number(payload.exit_code) === 0;
        const title = ok ? `${debugActionName(payload.action)}成功` : `${debugActionName(payload.action)}失败`;
        const text = summarizeDebug(payload);
        box.innerHTML = `<h2 class="${ok ? "ok" : "bad"}">${escapeHtml(title)}</h2><p>工程：${escapeHtml(payload.project || "")}</p><p>${escapeHtml(text)}</p>`;
        return;
      }
      if (payload.command === "read-expression") {
        const ok = Number(payload.exit_code) === 0;
        const text = summarizeExpression(payload);
        box.innerHTML = `<h2 class="${ok ? "ok" : "bad"}">${ok ? "读取成功" : "读取失败"}</h2><p>${escapeHtml(payload.expression || "")}</p><span class="value-readout">${escapeHtml(text)}</span>`;
        return;
      }
      if (payload.command === "last-log") {
        box.innerHTML = `<h2>最近日志</h2><p>${payload.last_entry ? escapeHtml(payload.last_entry.command || "") : "还没有日志。"}</p>`;
        return;
      }
      if (payload.command === "copy") {
        box.innerHTML = `<h2>已复制</h2><p>${escapeHtml(payload.message || "原始日志已复制。")}</p>`;
        return;
      }
      box.innerHTML = `<h2>就绪</h2><p>命令已完成。</p>`;
    }

    function summarizeBuild(payload) {
      const stdout = payload.stdout || "";
      const match = stdout.match(/CCS headless build complete! ([^\n]+)/);
      if (match) return match[0];
      if (stdout.includes("is up to date")) return "输出文件已是最新。";
      if ((payload.diagnostics || []).length) return payload.diagnostics.join("; ");
      return `退出码：${payload.exit_code}`;
    }

    function summarizeDebug(payload) {
      if ((payload.diagnostics || []).length) return payload.diagnostics.join("; ");
      const stdout = payload.stdout || "";
      const pc = stdout.match(/PC=([^\r\n]+)/);
      const sp = stdout.match(/SP=([^\r\n]+)/);
      if (pc || sp) return `${pc ? "PC=" + pc[1] : ""} ${sp ? "SP=" + sp[1] : ""}`.trim();
      if (stdout.includes("Loaded OUT=")) return "RAM 程序已加载。";
      if (stdout.includes("Connected")) return "目标已通过 DSS 连接。";
      if (stdout.includes("Run started")) return "已发送运行命令。";
      if (stdout.includes("Halted")) return "目标已暂停。";
      if (stdout.includes("Reset complete")) return "目标复位完成。";
      return `退出码：${payload.exit_code}`;
    }

    function summarizeExpression(payload) {
      if ((payload.diagnostics || []).length) return payload.diagnostics.join("; ");
      if (payload.value !== null && payload.value !== undefined) return `${payload.expression} = ${formatValue(payload.value)}`;
      return `退出码：${payload.exit_code}`;
    }

    function formatValue(value) {
      const text = String(value).trim();
      if (/^-?\d+$/.test(text)) {
        const number = Number(text);
        if (Number.isSafeInteger(number) && number >= 0) {
          return `0x${number.toString(16).toUpperCase().padStart(8, "0")} (${text})`;
        }
      }
      return text;
    }

    function debugActionName(action) {
      return ({
        connect: "连接目标",
        load: "加载 RAM",
        registers: "读取 PC/SP",
        run: "运行",
        halt: "暂停",
        reset: "复位"
      })[action] || "调试命令";
    }

    async function api(path, options) {
      const response = await fetch(path, options);
      const payload = await response.json();
      show(payload);
      if (!response.ok) throw new Error(payload.error || "Request failed");
      return payload;
    }

    async function apiQuiet(path, options) {
      const response = await fetch(path, options);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Request failed");
      return payload;
    }

    async function loadStatus() {
      const payload = await api("/api/status");
      const tools = payload.tools || {};
      const cells = [
        ["CCS", payload.ccs_base_exists],
        ["工作区", payload.workspace_exists],
        ["cl2000", tools.cl2000],
        ["eclipsec", tools.eclipsec],
      ];
      document.getElementById("statusGrid").innerHTML = cells.map(([name, ok]) =>
        `<div class="metric"><strong>${name}</strong><span class="${ok ? "ok" : "bad"}">${ok ? "正常" : "缺失"}</span></div>`
      ).join("");
      document.getElementById("workspacePath").textContent = payload.workspace || "";
    }

    async function loadProjects() {
      const payload = await api("/api/projects");
      const projects = payload.projects || [];
      document.getElementById("projects").innerHTML = projects.map(project =>
        `<button class="project ${project.name === selectedProject ? "active" : ""}" onclick="selectProject('${escapeAttr(project.name)}')">${escapeHtml(project.name)}</button>`
      ).join("");
      return payload;
    }

    function selectProject(name) {
      selectedProject = name;
      document.getElementById("selectedProject").textContent = name;
      loadProjects();
      inspectSelected();
    }

    async function inspectSelected() {
      const payload = await api(`/api/inspect?project=${encodeURIComponent(selectedProject)}`);
      const lines = [];
      for (const name of payload.ccxml_files || []) lines.push(`ccxml: ${name}`);
      for (const name of payload.cmd_files || []) lines.push(`cmd: ${name}`);
      for (const name of payload.out_files || []) lines.push(`out: ${name}`);
      cachedRamOut = (payload.out_files || []).find(name => name.toUpperCase().includes("RAM")) || "";
      document.getElementById("fileSummary").innerHTML = lines.length
        ? lines.map(line => `<code>${escapeHtml(line)}</code>`).join("")
        : "没有找到工程文件。";
      renderWatchTable();
    }

    async function buildSelected() {
      show({ message: `正在构建 ${selectedProject}...` });
      await api("/api/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: selectedProject, configuration: selectedConfiguration() })
      });
    }

    async function cleanSelected() {
      show({ message: `正在清理 ${selectedProject}...` });
      await api("/api/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: selectedProject, clean: true, configuration: selectedConfiguration() })
      });
    }

    async function rebuildSelected() {
      await cleanSelected();
      await buildSelected();
    }

    async function importProject() {
      const path = document.getElementById("importPath").value.trim();
      if (!path) {
        show({ error: "请输入 CCS 工程目录。" });
        return;
      }
      show({ message: `正在导入 ${path}...` });
      await api("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path })
      });
      await loadProjects();
    }

    async function openProjectFolder() {
      await api("/api/open-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: selectedProject })
      });
    }

    async function openOutputFolder() {
      await api("/api/open-output", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: selectedProject })
      });
    }

    async function debugAction(action) {
      if (liveActive && ["run", "halt", "reset"].includes(action)) {
        await liveCommand(action);
        return;
      }
      const payload = await api(`/api/inspect?project=${encodeURIComponent(selectedProject)}`);
      const ramOut = (payload.out_files || []).find(name => name.toUpperCase().includes("RAM")) || "";
      show({ message: `${debugActionName(action)}中...` });
      await api("/api/debug", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: selectedProject, action, out_file: ramOut })
      });
    }

    async function readExpression() {
      const expression = document.getElementById("expressionInput").value.trim();
      if (!expression) {
        show({ error: "请输入变量或寄存器名。" });
        return;
      }
      const payload = await api(`/api/inspect?project=${encodeURIComponent(selectedProject)}`);
      const ramOut = (payload.out_files || []).find(name => name.toUpperCase().includes("RAM")) || "";
      show({ message: `正在读取 ${expression}...` });
      await api("/api/read-expression", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: selectedProject, expression, out_file: ramOut, halt: true })
      });
    }

    function addWatch() {
      const expression = document.getElementById("watchInput").value.trim();
      if (!expression) {
        show({ error: "请输入要观察的变量或寄存器名。" });
        return;
      }
      if (!watchList.includes(expression)) watchList.push(expression);
      renderWatchTable();
    }

    function startWatchMode() {
      if (watchTimer) return;
      watchActive = true;
      document.getElementById("watchStatus").textContent = "正在启动快速调试会话...";
      renderWatchTable(watchList.map(expression => [expression, "准备读取"]));
      startLiveSession().then(sampleWatches).catch(error => {
        document.getElementById("watchStatus").textContent = `快速会话失败，退回慢速读取：${error.message}`;
        sampleWatches();
      });
    }

    function stopWatchMode() {
      watchActive = false;
      if (watchTimer) {
        window.clearTimeout(watchTimer);
        watchTimer = null;
      }
      document.getElementById("watchStatus").textContent = "已停止";
    }

    async function stopLiveSession() {
      stopWatchMode();
      await api("/api/live/stop", { method: "POST" });
      liveActive = false;
      document.getElementById("watchStatus").textContent = "快速会话已退出";
    }

    async function startLiveSession() {
      if (liveActive) return;
      const payload = await apiQuiet(`/api/inspect?project=${encodeURIComponent(selectedProject)}`);
      cachedRamOut = (payload.out_files || []).find(name => name.toUpperCase().includes("RAM")) || "";
      const startPayload = await apiQuiet("/api/live/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: selectedProject, out_file: cachedRamOut, load_program: false })
      });
      liveActive = true;
      document.getElementById("watchStatus").textContent = `快速会话已启动：PID ${startPayload.pid}`;
    }

    async function liveCommand(name) {
      const payload = await api("/api/live/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
      });
      renderSummary({ command: "debug", action: name, exit_code: 0, project: selectedProject, stdout: JSON.stringify(payload), diagnostics: [] });
    }

    async function sampleWatches() {
      if (!watchActive || watchSampling) return;
      watchSampling = true;
      if (!cachedRamOut) {
        try {
          const payload = await apiQuiet(`/api/inspect?project=${encodeURIComponent(selectedProject)}`);
          cachedRamOut = (payload.out_files || []).find(name => name.toUpperCase().includes("RAM")) || "";
        } catch (error) {
          document.getElementById("watchStatus").textContent = `观察失败：${error.message}`;
          watchSampling = false;
          return;
        }
      }
      const rows = watchList.map(expression => [expression, "读取中..."]);
      renderWatchTable(rows);
      try {
        const path = liveActive ? "/api/live/command" : "/api/read-expressions";
        const body = liveActive
          ? { name: "watch", expressions: watchList }
          : { project: selectedProject, expressions: watchList, out_file: cachedRamOut, halt: false };
        const payload = await apiQuiet(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
        const values = payload.values || {};
        renderWatchTable(watchList.map(expression => [
          expression,
          values[expression] !== undefined ? formatValue(values[expression]) : "无数据"
        ]));
      } catch (error) {
        renderWatchTable(watchList.map(expression => [expression, `读取失败：${error.message}`]));
      }
      document.getElementById("watchStatus").textContent = `观察中：${new Date().toLocaleTimeString()} 刷新`;
      watchSampling = false;
      if (watchActive) watchTimer = window.setTimeout(sampleWatches, 1000);
    }

    function renderWatchTable(rows) {
      const data = rows || watchList.map(expression => [expression, "等待读取"]);
      document.getElementById("watchTable").innerHTML = data.map(([expression, value]) =>
        `<tr><td>${escapeHtml(expression)}</td><td>${escapeHtml(value)}</td></tr>`
      ).join("");
    }

    async function copyRawLog() {
      const text = document.getElementById("output").textContent;
      await navigator.clipboard.writeText(text);
      renderSummary({ command: "copy", message: "原始日志已复制。" });
    }

    function clearResult() {
      document.getElementById("output").textContent = "就绪。";
      document.getElementById("summary").innerHTML = "<h2>就绪</h2><p>选择工程后，可以构建、加载 RAM、读取变量或寄存器。</p>";
    }

    async function loadLastLog() {
      await api("/api/last-log");
    }

    function selectedConfiguration() {
      return document.getElementById("buildConfig").value;
    }

    async function refreshAll() {
      await loadStatus();
      await loadProjects();
      await inspectSelected();
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[char]));
    }

    function escapeAttr(value) {
      return String(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    }

    refreshAll().catch(error => show({ error: error.message }));
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
