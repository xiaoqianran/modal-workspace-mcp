import base64
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

from modal_workspace_mcp import realtime_agent


class RealtimeAgentTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.env = os.environ.copy()
        self.env["MODAL_WORKSPACE_REALTIME_ROOT"] = self.tempdir.name
        self.agent = pathlib.Path(realtime_agent.__file__).resolve()

    def tearDown(self):
        self.tempdir.cleanup()

    def run_agent(self, *args: str, timeout: float = 10) -> dict:
        proc = subprocess.run(
            [sys.executable, str(self.agent), *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            self.fail(f"agent failed rc={proc.returncode}: {proc.stderr or proc.stdout}")
        return json.loads(proc.stdout)

    @staticmethod
    def payload(command: str, *, pty: bool = False) -> str:
        raw = json.dumps({"command": command, "workdir": None, "pty": pty}).encode()
        return base64.urlsafe_b64encode(raw).decode()

    def test_incremental_events_arrive_before_process_finishes(self):
        exec_id = "ex-" + "1" * 32
        self.run_agent(
            "start",
            "--exec-id",
            exec_id,
            "--payload",
            self.payload("printf 'first\\n'; sleep 1.5; printf 'second\\n'"),
        )

        deadline = time.monotonic() + 1.2
        first_batch = None
        cursor = 0
        while time.monotonic() < deadline:
            result = self.run_agent(
                "events",
                "--exec-id",
                exec_id,
                "--cursor",
                str(cursor),
                "--wait-seconds",
                "0.3",
            )
            cursor = result["next_cursor"]
            text = "".join(e.get("data", "") for e in result["events"] if e["type"] == "stdout")
            if "first" in text:
                first_batch = result
                break
        self.assertIsNotNone(first_batch, "first stdout event should arrive while process is running")
        self.assertNotEqual(first_batch["state"], "finished")

        combined = ""
        deadline = time.monotonic() + 4
        state = None
        while time.monotonic() < deadline:
            result = self.run_agent(
                "events",
                "--exec-id",
                exec_id,
                "--cursor",
                str(cursor),
                "--wait-seconds",
                "0.5",
            )
            cursor = result["next_cursor"]
            combined += "".join(
                e.get("data", "") for e in result["events"] if e["type"] == "stdout"
            )
            state = result["state"]
            if state == "finished":
                break
        self.assertIn("second", combined)
        self.assertEqual(state, "finished")

    def test_stdin_roundtrip(self):
        exec_id = "ex-" + "2" * 32
        self.run_agent(
            "start",
            "--exec-id",
            exec_id,
            "--payload",
            self.payload("read line; printf 'got:%s\\n' \"$line\""),
        )
        time.sleep(0.2)
        encoded = base64.b64encode(b"hello-realtime\n").decode()
        self.run_agent(
            "input",
            "--exec-id",
            exec_id,
            "--data-b64",
            encoded,
        )

        cursor = 0
        output = ""
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            result = self.run_agent(
                "events",
                "--exec-id",
                exec_id,
                "--cursor",
                str(cursor),
                "--wait-seconds",
                "0.5",
            )
            cursor = result["next_cursor"]
            output += "".join(
                e.get("data", "") for e in result["events"] if e["type"] == "stdout"
            )
            if result["state"] == "finished":
                break
        self.assertIn("got:hello-realtime", output)


if __name__ == "__main__":
    unittest.main()
