"""Deterministic native transport checks, separate from real-model acceptance."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time

from .__main__ import ROOT, STATE, write_json
from .acceptance import fixture_binary, read_oracle
from .driver import LOCK, verify


class NativeTransport:
    """Test-only harness in this checkout's existing native host executable."""

    def __init__(self, grant_existing_profile=False):
        self.grant_existing_profile = grant_existing_profile

    def __enter__(self):
        driver = verify(STATE / "cua" / LOCK["version"])
        write_json(ROOT / "xs.json", {"services": [{"enabled": True, "class": "http",
            "name": "transport-check", "ip": "127.0.0.1", "port": 5392,
            "host_default": {"enabled": True, "name": "transport-check", "path": "app/web",
                             "devlang": "c", "devfile": "tests/fixtures/computer-use-transport.c"}}]})
        self.capture = STATE / "native-transport-last.png"
        env = dict(os.environ, MDO_CUA_DRIVER=str(driver), MDO_CUA_CAPTURE=str(self.capture))
        env.pop("MDO_CUA_TEST_GRANT", None)
        if self.grant_existing_profile:
            env["MDO_CUA_TEST_GRANT"] = "1"
        self.log = (STATE / "native-transport.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen([str(ROOT / ".build/host/xs.exe"), str(ROOT / "xs.json")],
            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            self.tools = self.read("native_ready=")["tools"]
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def read(self, prefix):
        for line in self.process.stdout:
            self.log.write(line)
            self.log.flush()
            if line.startswith(prefix):
                return json.loads(line[len(prefix):])
        raise RuntimeError("Native transport harness exited; inspect native-transport.log")

    def call(self, tool: str, arguments: dict, *, require_success=True) -> dict:
        self.process.stdin.write(tool + "\n" + json.dumps(arguments, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        result = self.read("native_result=")
        text = result["content"]
        if "structured_content: " in text:
            result["structured"] = json.JSONDecoder().raw_decode(text.split("structured_content: ", 1)[1])[0]
        if require_success and not result["success"]:
            raise RuntimeError(f"{tool} failed: {text[:1200]}")
        return result

    def __exit__(self, *_):
        if self.process.poll() is None:
            try:
                self.process.stdin.write("quit\n")
                self.process.stdin.flush()
            except OSError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.close()


def wait_fixture(oracle: Path, fixture) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if fixture.poll() is not None:
            raise RuntimeError("The acceptance fixture exited")
        try:
            return read_oracle(oracle)
        except (OSError, ValueError):
            time.sleep(.1)
    raise RuntimeError("The acceptance fixture did not publish its oracle")


def token(state: dict, label: str, role: str) -> str:
    snapshot = state["structured"]
    matching = re.findall(r'^\s*- \[(\d+)\] ' + re.escape(role) + ' "' + re.escape(label) + '"',
                          snapshot["tree_markdown"], re.MULTILINE)
    if len(matching) != 1:
        raise RuntimeError(f"Expected exactly one {role} {label!r}; found {matching}")
    return snapshot["snapshot_id"] + ":" + matching[0]


def desktop() -> dict:
    oracle = STATE / "native-oracle.json"
    oracle.unlink(missing_ok=True)
    fixture = subprocess.Popen([str(fixture_binary()), str(oracle)], cwd=ROOT)
    report = {"model": False, "driver_version": LOCK["version"], "checks": {}}
    try:
        original = wait_fixture(oracle, fixture)
        target = {"pid": fixture.pid, "window_id": original["window_id"]}
        with NativeTransport() as transport:
            report["tools_loaded"] = len(transport.tools)
            state = transport.call("get_window_state", target)
            report["checks"]["window_image"] = state["image_bytes"] > 1000
            def act(tool, label, role, **arguments):
                current = transport.call("get_window_state", target)
                return transport.call(tool, dict(arguments, element_token=token(current, label, role)))
            act("set_value", "Input text", "Edit", value="墨斗 Computer Use 验收")
            act("click", "Increment counter", "Button")
            act("click", "Enable option", "CheckBox")
            act("set_value", "Color", "ComboBox", value="Green")
            # A real pixel target: this custom canvas has no accessible peer.
            state = transport.call("get_window_state", target)
            transport.call("click", dict(target, x=575, y=410,
                                          capture_id=state["structured"]["capture_id"]))
            final = transport.call("get_window_state", target)
            report["checks"]["final_image"] = final["image_bytes"] > 1000
            time.sleep(.2)  # fixture's 150 ms oracle publication timer
            actual = report["oracle"] = read_oracle(oracle)
            report["checks"].update(text=actual["text"] == "墨斗 Computer Use 验收",
                button_once=actual["clicks"] == 1, checkbox=actual["checked"] is True,
                selection=actual["selection"] == "Green", pixel_click=actual["canvas_clicks"] == 1,
                full_catalog=len(transport.tools) == 63)
            report["captured"] = str(transport.capture)
            report["passed"] = all(report["checks"].values())
        return report
    finally:
        write_json(STATE / "desktop-transport.json", report)
        if fixture.poll() is None:
            fixture.terminate()
            fixture.wait(timeout=5)
