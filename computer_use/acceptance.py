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


def wait_account(app) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if app.request("/api/v1/account")["data"].get("state") == "signed_in":
            return
        time.sleep(.2)
    raise RuntimeError("Sign in to the project mdo Home before real-model acceptance")


def collect_evidence(report: dict) -> None:
    snapshot = HOME / "sessions/default" / report["session_id"] / "snapshot.json"
    entries = read_oracle(snapshot)["entries"]
    report["tool_names"] = [call.get("name") for entry in entries
                            for call in entry.get("tool_calls", [])]
    report["image_parts"] = [{"media_type": part.get("media_type"), "bytes": part.get("data_bytes")}
                             for entry in entries for part in entry.get("parts", [])
                             if part.get("kind") == 2]
    report["assistant_text"] = "\n".join(entry.get("content") or "" for entry in entries
                                          if entry.get("role") == 2)[-8192:]
    clicks = [i for i, entry in enumerate(entries) if any(
        c.get("name") == "mcp__cua-driver__click" for c in entry.get("tool_calls", []))]
    report["post_click_image"] = bool(clicks) and any(
        any(p.get("kind") == 2 for p in entry.get("parts", [])) for entry in entries[clicks[-1] + 1:])
    report["gui_tools_only"] = all(name in ("tool_search", "tool_load") or
        name.startswith("mcp__cua-driver__") for name in report["tool_names"])


def run_task(app, report: dict, title: str, prompt: str, timeout: float) -> dict:
    config = {
        "project_id": "default", "title": title, "agent_id": "mdo.default",
        "model_id": report["model"], "permission_profile": "full-access",
        "reasoning_effort": "medium", "max_output_tokens": 8192,
    }
    if report.get("protocol_requested"):
        config["protocol"] = report["protocol_requested"]
    session = app.request("/api/v1/sessions", "POST", config)["data"]
    sid = report["session_id"] = session["id"]
    report["user_task"] = prompt
    started = time.monotonic()
    active = app.request(f"/api/v1/projects/default/sessions/{sid}/runs", "POST",
                         {"prompt": prompt, "timeout_ms": int(timeout * 1000)})["data"]
    run_id = report["run_id"] = active["id"]
    write_json(STATE / "acceptance-active.json", report)
    previous = None
    try:
        while time.monotonic() - started < timeout + 10:
            active = app.request("/api/v1/runs/" + run_id)["data"]
            progress = (active.get("state"), active.get("model_calls"), active.get("tool_calls"))
            if progress != previous:
                print(f"model run: {progress[0]}, model calls={progress[1]}, tools={progress[2]}", flush=True)
                previous = progress
            if active.get("terminal"):
                break
            time.sleep(.5)
        else:
            raise RuntimeError("Acceptance run exceeded its deadline")
    finally:
        report["run"] = active
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        if not active.get("terminal"):
            app.request("/api/v1/runs/" + run_id, "DELETE")
    # Keep ordinary session history in Home; only duplicate compact evidence.
    collect_evidence(report)
    return active


def run(model: str = "ornith-1.5-35b", timeout: float = 300, protocol: str | None = None,
        scenario: str = "form") -> dict:
    if os.name != "nt":
        raise RuntimeError("This desktop acceptance fixture currently validates Windows only")
    STATE.mkdir(parents=True, exist_ok=True)
    binary = fixture_binary()
    oracle = STATE / "native-oracle.json"
    oracle.unlink(missing_ok=True)
    fixture = subprocess.Popen([str(binary), str(oracle)], cwd=ROOT)
    report = {"model": model, "backend": "official Cua 0.38.0 through mdo MCP",
              "prompt_workarounds": False, "fixture_pid": fixture.pid,
              "protocol_requested": protocol, "scenario": scenario}
    try:
        with Application() as app:
            app.ready()
            wait_account(app)
            prompt = (
                "请使用 Computer Use，在“MDO Computer Use Acceptance”窗口中输入“墨斗 Computer Use 验收”，"
                "点击 Increment counter 一次，勾选 Enable option，并将 Color 选择为 Green。"
                "最后查看窗口截图，读出蓝色画布里的六位 Visual code 并报告结果。只操作这个测试窗口。")
            if scenario == "click":
                prompt = ("请使用 Computer Use，点击“MDO Computer Use Acceptance”窗口中的 Increment counter 一次，"
                    "随后查看窗口截图，报告 Counter 的数值和蓝色画布里的六位 Visual code。只操作这个测试窗口。")
            try:
                active = run_task(app, report, "Computer Use native acceptance", prompt, timeout)
                state = report["oracle"] = read_oracle(oracle)
                report["checks"] = {"run_succeeded": active.get("state") == "succeeded",
                    "button_once": state.get("clicks") == 1,
                    "visual_code": state["visual_code"] in report["assistant_text"],
                    "screenshot_retained": bool(report["image_parts"])}
                if scenario == "form":
                    report["checks"].update(text=state.get("text") == "墨斗 Computer Use 验收",
                        checkbox=state.get("checked") is True, selection=state.get("selection") == "Green")
                else:
                    report["checks"].update(post_click_image=report["post_click_image"],
                        gui_tools_only=report["gui_tools_only"],
                        final_visual_code=state["visual_code"] in (active.get("final_text") or ""))
                report["passed"] = all(report["checks"].values())
            finally:
                app.request("/api/v1/mcp/cua-driver/disconnect", "POST")
            return report
    except (OSError, ValueError, RuntimeError) as error:
        report.update(passed=False, error=str(error))
        return report
    finally:
        suffix = ("-" + protocol if protocol else "") + ("-" + scenario if scenario != "form" else "")
        write_json(STATE / ("native-acceptance" + suffix + ".json"), report)
        if fixture.poll() is None:
            fixture.terminate()
            fixture.wait(timeout=5)


def summary(report: dict) -> dict:
    return {key: report.get(key) for key in ("passed", "checks", "elapsed_seconds", "session_id", "run_id", "oracle", "run", "error")}
