"""Real account-model -> mdo -> official Cua -> dedicated Windows fixture."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

from .__main__ import Application, HOME, ROOT, STATE, sha256, write_json


def fixture_binary() -> Path:
    source = ROOT / "tests/fixtures/computer-use-win32.c"
    binary = STATE / "computer-use-win32.exe"
    receipt = STATE / "fixture-build.json"
    digest = sha256(source)
    if (not binary.is_file() or not receipt.is_file()
            or json.loads(receipt.read_text())["source_sha256"] != digest):
        subprocess.run(["gcc", "-municode", "-mwindows", "-O2", "-Wall", "-Wextra",
                        str(source), "-o", str(binary), "-lgdi32", "-luser32"], check=True, cwd=ROOT)
        write_json(receipt, {"source_sha256": digest, "binary_sha256": sha256(binary)})
    return binary


def read_oracle(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(model: str = "ornith-1.5-35b", timeout: float = 300) -> dict:
    if os.name != "nt":
        raise RuntimeError("This desktop acceptance fixture currently validates Windows only")
    STATE.mkdir(parents=True, exist_ok=True)
    binary = fixture_binary()
    oracle = STATE / "native-oracle.json"
    oracle.unlink(missing_ok=True)
    fixture = subprocess.Popen([str(binary), str(oracle)], cwd=ROOT)
    run_id = None
    report = {"model": model, "backend": "official Cua 0.38.0 through mdo MCP",
              "prompt_workarounds": False, "fixture_pid": fixture.pid}
    try:
        with Application() as app:
            app.ready()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                account = app.request("/api/v1/account")["data"]
                if account.get("state") == "signed_in":
                    break
                time.sleep(.2)
            else:
                raise RuntimeError("Sign in to the project mdo Home before real-model acceptance")
            session = app.request("/api/v1/sessions", "POST", {
                "project_id": "default", "title": "Computer Use native acceptance",
                "agent_id": "mdo.default", "model_id": model,
                "permission_profile": "full-access", "reasoning_effort": "medium",
                "max_output_tokens": 8192,
            })["data"]
            sid = session["id"]
            report["session_id"] = sid
            prompt = (
                "请使用 Computer Use，在“MDO Computer Use Acceptance”窗口中输入“墨斗 Computer Use 验收”，"
                "点击 Increment counter 一次，勾选 Enable option，并将 Color 选择为 Green。"
                "最后查看窗口截图，读出蓝色画布里的文字并报告结果。只操作这个测试窗口。")
            report["user_task"] = prompt
            started = time.monotonic()
            active = app.request(f"/api/v1/projects/default/sessions/{sid}/runs", "POST",
                                 {"prompt": prompt, "timeout_ms": int(timeout * 1000)})["data"]
            run_id = active["id"]
            report["run_id"] = run_id
            write_json(STATE / "acceptance-active.json", report)
            previous = None
            while time.monotonic() - started < timeout + 10:
                active = app.request("/api/v1/runs/" + run_id)["data"]
                state = active.get("state")
                if state != previous:
                    print(f"model run: {state}", flush=True)
                    previous = state
                if state in ("succeeded", "failed", "cancelled", "interrupted"):
                    break
                time.sleep(.5)
            else:
                app.request("/api/v1/runs/" + run_id + "/cancel", "POST")
                raise RuntimeError("Acceptance run exceeded its deadline")
            report["run"] = active
            report["elapsed_seconds"] = round(time.monotonic() - started, 2)
            report["oracle"] = read_oracle(oracle)
            history = app.request(f"/api/v1/projects/default/sessions/{sid}/history")["data"]
            # Full history already belongs to this task's ordinary mdo Home;
            # don't duplicate image payloads or private account state in reports.
            report["history"] = history
            state = report["oracle"]
            report["checks"] = {"run_succeeded": active.get("state") == "succeeded",
                                "text": state.get("text") == "墨斗 Computer Use 验收",
                                "button_once": state.get("clicks") == 1,
                                "checkbox": state.get("checked") is True,
                                "selection": state.get("selection") == "Green"}
            report["passed"] = all(report["checks"].values())
            write_json(STATE / "native-acceptance.json", report)
            try:
                app.request("/api/v1/mcp/cua-driver/disconnect", "POST")
            except OSError:
                pass
            return report
    finally:
        if fixture.poll() is None:
            fixture.terminate()
            fixture.wait(timeout=5)


def summary(report: dict) -> dict:
    return {key: report.get(key) for key in ("passed", "checks", "elapsed_seconds", "session_id", "run_id", "oracle", "run")}
