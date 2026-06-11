import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tools.ccs_agent_control import ccs_agent, ccs_agent_ui


class CcsAgentUiTests(unittest.TestCase):
    def setUp(self):
        self.config = ccs_agent.Config(
            base_dir=Path("C:/fake/ccs1280"),
            workspace=Path("C:/fake/ccs1280/ccs/F28335_PID"),
            log_dir=Path("C:/fake/logs"),
        )
        handler = ccs_agent_ui.make_handler(self.config)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        encoded = None
        headers = {}
        if body is not None:
            encoded = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        data = response.read().decode("utf-8")
        connection.close()
        return response.status, response.getheader("Content-Type"), data

    def test_index_page_contains_app_shell(self):
        status, content_type, body = self.request("GET", "/")

        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertIn("CCS 调试控制台", body)
        self.assertIn("构建", body)
        self.assertIn("开始观察", body)

    def test_status_api_returns_json(self):
        with mock.patch.object(ccs_agent_ui.ccs_agent, "status", return_value={"command": "status", "ok": True}):
            status, content_type, body = self.request("GET", "/api/status")

        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual({"command": "status", "ok": True}, json.loads(body))

    def test_inspect_api_requires_project_query(self):
        status, content_type, body = self.request("GET", "/api/inspect")

        self.assertEqual(400, status)
        self.assertIn("application/json", content_type)
        self.assertIn("Missing project", json.loads(body)["error"])

    def test_build_api_posts_project_name(self):
        payload = {"command": "build", "project": "DemoProject", "exit_code": 0}
        with mock.patch.object(ccs_agent_ui.ccs_agent, "build_project", return_value=payload) as build:
            status, content_type, body = self.request(
                "POST",
                "/api/build",
                {"project": "DemoProject", "clean": True, "configuration": "CPU1_RAM"},
            )

        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload, json.loads(body))
        build.assert_called_once()
        self.assertEqual("DemoProject", build.call_args.args[1])
        self.assertTrue(build.call_args.kwargs["clean"])
        self.assertEqual("CPU1_RAM", build.call_args.kwargs["configuration"])

    def test_import_api_posts_project_path(self):
        payload = {"command": "import", "project_path": "C:/Projects/DemoProject", "exit_code": 0}
        with mock.patch.object(ccs_agent_ui.ccs_agent, "import_project", return_value=payload) as import_project:
            status, content_type, body = self.request("POST", "/api/import", {"path": "C:/Projects/DemoProject"})

        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload, json.loads(body))
        import_project.assert_called_once()
        self.assertEqual("C:/Projects/DemoProject", import_project.call_args.args[1])

    def test_open_project_api_posts_project_name(self):
        payload = {"command": "open-project", "project": "DemoProject"}
        with mock.patch.object(ccs_agent_ui.ccs_agent, "open_project_folder", return_value=payload) as open_project:
            status, content_type, body = self.request("POST", "/api/open-project", {"project": "DemoProject"})

        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload, json.loads(body))
        open_project.assert_called_once()
        self.assertEqual("DemoProject", open_project.call_args.args[1])

    def test_open_output_api_posts_project_name(self):
        payload = {"command": "open-output", "project": "DemoProject"}
        with mock.patch.object(ccs_agent_ui.ccs_agent, "open_output_folder", return_value=payload) as open_output:
            status, content_type, body = self.request("POST", "/api/open-output", {"project": "DemoProject"})

        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload, json.loads(body))
        open_output.assert_called_once()
        self.assertEqual("DemoProject", open_output.call_args.args[1])

    def test_debug_api_posts_project_and_action(self):
        payload = {"command": "debug", "project": "DemoProject", "action": "registers", "exit_code": 0}
        with mock.patch.object(ccs_agent_ui.ccs_agent, "debug_action", return_value=payload) as debug_action:
            status, content_type, body = self.request(
                "POST",
                "/api/debug",
                {"project": "DemoProject", "action": "registers", "out_file": "Debug/DemoProject.out"},
            )

        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload, json.loads(body))
        debug_action.assert_called_once()
        self.assertEqual("DemoProject", debug_action.call_args.args[1])
        self.assertEqual("registers", debug_action.call_args.args[2])
        self.assertEqual("Debug/DemoProject.out", debug_action.call_args.kwargs["out_file"])


if __name__ == "__main__":
    unittest.main()
