import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from tools.ccs_agent_control import ccs_agent
from tools.ccs_agent_control import ccs_agent_ui


class CcsAgentControlTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ccs-agent-test-"))
        self.base_dir = self.temp_dir / "ccs1280"
        self.workspace = self.base_dir / "ccs" / "F28335_PID"
        self.log_dir = self.temp_dir / "logs"
        self.project = self.workspace / "DemoProject"
        self.project.mkdir(parents=True)
        (self.project / ".project").write_text("<projectDescription />", encoding="utf-8")
        (self.project / ".ccsproject").write_text("<ccsProject />", encoding="utf-8")
        (self.project / "F28034.cmd").write_text("MEMORY {}", encoding="utf-8")
        (self.project / "targetConfigs").mkdir()
        (self.project / "targetConfigs" / "TMS320F28034.ccxml").write_text("<configurations />", encoding="utf-8")
        (self.project / "Debug").mkdir()
        (self.project / "Debug" / "DemoProject.out").write_text("fake out", encoding="utf-8")
        (self.project / "Makefile").write_text("all:\n\t@echo building DemoProject\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def config(self):
        return ccs_agent.Config(
            base_dir=self.base_dir,
            workspace=self.workspace,
            log_dir=self.log_dir,
        )

    def test_status_reports_configured_paths_and_tool_presence(self):
        result = ccs_agent.status(self.config())

        self.assertEqual("status", result["command"])
        self.assertTrue(result["ccs_base_exists"])
        self.assertTrue(result["workspace_exists"])
        self.assertIn("cl2000", result["tools"])

    def test_list_projects_finds_ccs_projects_only(self):
        (self.workspace / "PlainFolder").mkdir()
        temp_project = self.workspace / "RemoteSystemsTempFiles"
        temp_project.mkdir()
        (temp_project / ".project").write_text("<projectDescription />", encoding="utf-8")
        odd_project = self.workspace / "OddProject'"
        odd_project.mkdir()
        (odd_project / ".project").write_text("<projectDescription />", encoding="utf-8")

        result = ccs_agent.list_projects(self.config())

        self.assertEqual("list-projects", result["command"])
        self.assertEqual(["DemoProject"], [item["name"] for item in result["projects"]])
        self.assertTrue(result["projects"][0]["has_project_file"])
        self.assertTrue(result["projects"][0]["has_ccsproject_file"])

    def test_inspect_project_returns_key_ccs_files(self):
        result = ccs_agent.inspect_project(self.config(), "DemoProject")

        self.assertEqual("inspect", result["command"])
        self.assertEqual("DemoProject", result["project"])
        self.assertEqual(["targetConfigs/TMS320F28034.ccxml"], result["ccxml_files"])
        self.assertEqual(["F28034.cmd"], result["cmd_files"])
        self.assertEqual(["Debug/DemoProject.out"], result["out_files"])
        self.assertTrue(result["build_entrypoints"]["makefile"])

    def test_build_project_runs_makefile_and_records_last_log(self):
        result = ccs_agent.build_project(self.config(), "DemoProject")

        self.assertEqual("build", result["command"])
        self.assertEqual(0, result["exit_code"])
        self.assertIn("building DemoProject", result["stdout"])

        last_log = ccs_agent.last_log(self.config())
        self.assertEqual("last-log", last_log["command"])
        self.assertEqual("build", last_log["last_entry"]["command"])
        self.assertEqual(0, last_log["last_entry"]["exit_code"])

    def test_build_project_falls_back_to_ccs_headless_build_without_makefile(self):
        (self.project / "Makefile").unlink()
        eclipsec = self.base_dir / "ccs" / "eclipse" / "eclipsec.exe"
        eclipsec.parent.mkdir(parents=True)
        eclipsec.write_text("fake eclipsec", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="ccs build ok",
            stderr="",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed) as run:
            result = ccs_agent.build_project(self.config(), "DemoProject")

        argv = run.call_args.args[0]
        self.assertEqual(str(eclipsec), argv[0])
        self.assertIn("com.ti.ccstudio.apps.projectBuild", argv)
        self.assertIn("-ccs.autoImport", argv)
        self.assertIn("-ccs.projects", argv)
        self.assertIn("DemoProject", argv)
        self.assertEqual(0, result["exit_code"])
        self.assertIn("ccs build ok", result["stdout"])

    def test_build_project_supports_clean_and_configuration(self):
        (self.project / "Makefile").unlink()
        eclipsec = self.base_dir / "ccs" / "eclipse" / "eclipsec.exe"
        eclipsec.parent.mkdir(parents=True)
        eclipsec.write_text("fake eclipsec", encoding="utf-8")
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="clean ok", stderr="")

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed) as run:
            result = ccs_agent.build_project(self.config(), "DemoProject", clean=True, configuration="CPU1_RAM")

        argv = run.call_args.args[0]
        self.assertIn("-ccs.clean", argv)
        self.assertIn("-ccs.configuration", argv)
        self.assertIn("CPU1_RAM", argv)
        self.assertEqual("build", result["command"])
        self.assertTrue(result["clean"])
        self.assertEqual("CPU1_RAM", result["configuration"])

    def test_build_project_marks_zero_project_ccs_build_as_failure(self):
        (self.project / "Makefile").unlink()
        eclipsec = self.base_dir / "ccs" / "eclipse" / "eclipsec.exe"
        eclipsec.parent.mkdir(parents=True)
        eclipsec.write_text("fake eclipsec", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="!WARNING: Project 'DemoProject' was not found in the workspace!\n0 out of 0 projects have errors.",
            stderr="",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed):
            result = ccs_agent.build_project(self.config(), "DemoProject")

        self.assertEqual(2, result["exit_code"])
        self.assertEqual(0, result["process_exit_code"])
        self.assertTrue(
            any("CCS did not build the requested project" in item for item in result["diagnostics"]),
            result["diagnostics"],
        )

    def test_import_project_uses_ccs_headless_import(self):
        eclipsec = self.base_dir / "ccs" / "eclipse" / "eclipsec.exe"
        eclipsec.parent.mkdir(parents=True)
        eclipsec.write_text("fake eclipsec", encoding="utf-8")
        source = self.temp_dir / "ExternalProject"
        source.mkdir()
        (source / ".project").write_text("<projectDescription />", encoding="utf-8")
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="import ok", stderr="")

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed) as run:
            result = ccs_agent.import_project(self.config(), source)

        argv = run.call_args.args[0]
        self.assertEqual(str(eclipsec), argv[0])
        self.assertIn("com.ti.ccstudio.apps.projectImport", argv)
        self.assertIn("-ccs.location", argv)
        self.assertIn(str(source), argv)
        self.assertEqual("import", result["command"])
        self.assertEqual(0, result["exit_code"])

    def test_open_project_folder_uses_os_startfile(self):
        with mock.patch.object(ccs_agent.os, "startfile", create=True) as startfile:
            result = ccs_agent.open_project_folder(self.config(), "DemoProject")

        self.assertEqual("open-project", result["command"])
        self.assertEqual("DemoProject", result["project"])
        startfile.assert_called_once_with(str(self.project))

    def test_open_output_folder_uses_first_output_parent(self):
        with mock.patch.object(ccs_agent.os, "startfile", create=True) as startfile:
            result = ccs_agent.open_output_folder(self.config(), "DemoProject")

        self.assertEqual("open-output", result["command"])
        self.assertEqual("DemoProject", result["project"])
        self.assertTrue(result["folder"].endswith("Debug"))
        startfile.assert_called_once_with(str(self.project / "Debug"))

    def test_debug_action_runs_dss_script_for_registers(self):
        dss = self.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
        dss.parent.mkdir(parents=True)
        dss.write_text("@echo off", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="DSS_ACTION=registers\nPC=0x3F0000\nSP=0x000400",
            stderr="",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed) as run:
            result = ccs_agent.debug_action(self.config(), "DemoProject", "registers")

        argv = run.call_args.args[0]
        self.assertEqual(str(dss), argv[0])
        self.assertIn("-dss.workspace", argv)
        self.assertEqual("debug", result["command"])
        self.assertEqual("registers", result["action"])
        self.assertEqual(0, result["exit_code"])
        self.assertIn("PC=0x3F0000", result["stdout"])

    def test_debug_action_marks_dss_severe_output_as_failure(self):
        dss = self.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
        dss.parent.mkdir(parents=True)
        dss.write_text("@echo off", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="SEVERE: Error connecting to the target: The target is held in reset.",
            stderr="com.ti.debug.engine.scripting.TargetConnectionException",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed):
            result = ccs_agent.debug_action(self.config(), "DemoProject", "connect")

        self.assertEqual(2, result["exit_code"])
        self.assertEqual(0, result["process_exit_code"])
        self.assertTrue(
            any("DSS reported a debug failure" in item for item in result["diagnostics"]),
            result["diagnostics"],
        )
        self.assertTrue(
            any("target did not respond" in item for item in result["diagnostics"]),
            result["diagnostics"],
        )

    def test_debug_action_rejects_flash_out_for_load(self):
        with self.assertRaises(ValueError):
            ccs_agent.debug_action(self.config(), "DemoProject", "load", out_file="CPU1_FLASH/DemoProject.out")

    def test_read_expression_runs_dss_expression_script(self):
        dss = self.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
        dss.parent.mkdir(parents=True)
        dss.write_text("@echo off", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="DSS_ACTION=read-expression\nEXPRESSION=GpioDataRegs.GPADAT.all\nVALUE=0x00400000\n",
            stderr="",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed):
            result = ccs_agent.read_expression(
                self.config(),
                "DemoProject",
                "GpioDataRegs.GPADAT.all",
                out_file="Debug/DemoProject.out",
            )

        script = Path(result["script"]).read_text(encoding="utf-8")
        self.assertEqual("read-expression", result["command"])
        self.assertEqual("GpioDataRegs.GPADAT.all", result["expression"])
        self.assertEqual("0x00400000", result["value"])
        self.assertEqual(0, result["exit_code"])
        self.assertIn('session.symbol.load("', script)
        self.assertIn('session.expression.evaluateToString("GpioDataRegs.GPADAT.all")', script)

    def test_read_expression_rejects_write_like_expression(self):
        with self.assertRaises(ValueError):
            ccs_agent.read_expression(self.config(), "DemoProject", "PC = 0x3F0000")

    def test_read_expression_can_skip_halting_target_for_watch_mode(self):
        dss = self.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
        dss.parent.mkdir(parents=True)
        dss.write_text("@echo off", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="DSS_ACTION=read-expression\nEXPRESSION=PC\nHALT_BEFORE_READ=0\nVALUE=0x3F0000\n",
            stderr="",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed):
            result = ccs_agent.read_expression(self.config(), "DemoProject", "PC", halt=False)

        script = Path(result["script"]).read_text(encoding="utf-8")
        self.assertFalse(result["halt"])
        self.assertIn('print("HALT_BEFORE_READ=0");', script)
        self.assertNotIn("session.target.halt();", script)

    def test_read_expressions_reads_watch_values_in_one_dss_script(self):
        dss = self.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
        dss.parent.mkdir(parents=True)
        dss.write_text("@echo off", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="DSS_ACTION=read-expressions\nVALUE[PC]=0x3FF8A1\nVALUE[SP]=0x0400\n",
            stderr="",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed):
            result = ccs_agent.read_expressions(self.config(), "DemoProject", ["PC", "SP"], halt=False)

        script = Path(result["script"]).read_text(encoding="utf-8")
        self.assertEqual("read-expressions", result["command"])
        self.assertEqual({"PC": "0x3FF8A1", "SP": "0x0400"}, result["values"])
        self.assertFalse(result["halt"])
        self.assertIn('session.expression.evaluateToString("PC")', script)
        self.assertIn('session.expression.evaluateToString("SP")', script)
        self.assertNotIn("session.target.halt();", script)

    def test_read_expression_uses_flash_out_for_symbols_when_no_ram_out_exists(self):
        dss = self.base_dir / "ccs" / "ccs_base" / "scripting" / "bin" / "dss.bat"
        dss.parent.mkdir(parents=True)
        dss.write_text("@echo off", encoding="utf-8")
        (self.project / "Debug" / "DemoProject.out").unlink()
        (self.project / "CPU1_FLASH").mkdir()
        (self.project / "CPU1_FLASH" / "DemoProject.out").write_text("fake flash out", encoding="utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="DSS_ACTION=read-expression\nEXPRESSION=GpioDataRegs.GPADAT.all\nVALUE=42\n",
            stderr="",
        )

        with mock.patch.object(ccs_agent.subprocess, "run", return_value=completed):
            result = ccs_agent.read_expression(self.config(), "DemoProject", "GpioDataRegs.GPADAT.all")

        self.assertTrue(result["out_file"].endswith("CPU1_FLASH\\DemoProject.out"), result["out_file"])
        script = Path(result["script"]).read_text(encoding="utf-8")
        self.assertIn('session.symbol.load("', script)
        self.assertNotIn("memory.loadProgram", script)

    def test_ui_uses_chinese_debug_labels_and_hex_value_formatting(self):
        html = ccs_agent_ui.INDEX_HTML

        self.assertIn("CCS 调试控制台", html)
        self.assertIn("连接目标", html)
        self.assertIn("变量 / 寄存器", html)
        self.assertIn("原始日志", html)
        self.assertIn('number.toString(16).toUpperCase().padStart(8, "0")', html)

    def test_cli_outputs_json_for_agent_consumption(self):
        env = os.environ.copy()
        env["CCS_AGENT_BASE"] = str(self.base_dir)
        env["CCS_AGENT_WORKSPACE"] = str(self.workspace)
        env["CCS_AGENT_LOG_DIR"] = str(self.log_dir)

        completed = subprocess.run(
            [sys.executable, "-m", "tools.ccs_agent_control.ccs_agent", "inspect", "DemoProject"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("inspect", payload["command"])
        self.assertEqual("DemoProject", payload["project"])

    def test_main_without_arguments_prints_quick_start_instead_of_error(self):
        stdout = StringIO()

        with mock.patch("sys.stdout", stdout):
            exit_code = ccs_agent.main([])

        self.assertEqual(0, exit_code)
        self.assertIn("CCS Agent Control", stdout.getvalue())
        self.assertIn("ccs-agent.exe status", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
