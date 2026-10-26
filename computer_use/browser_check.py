"""Own local browser fixture and its independent event oracle."""
from __future__ import annotations

import http.server
import json
import socket
import shutil
import subprocess
import sys
import time
import urllib.request

from .__main__ import ROOT, STATE, write_json
from .transport_check import NativeTransport

PORT = 5393
URL = f"http://127.0.0.1:{PORT}/"
ORACLE = STATE / "browser-oracle.json"


def serve():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/download":
                body = b"MDO Computer Use download acceptance\n"
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="mdo-cua-check.txt"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = (ROOT / "tests/fixtures/computer-use-browser.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if self.path != "/state" or not 0 < length <= 4096:
                self.send_error(400)
                return
            write_json(ORACLE, json.loads(self.rfile.read(length)))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_):
            pass

    http.server.HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


class PageServer:
    def __enter__(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", PORT))
        ORACLE.unlink(missing_ok=True)
        self.process = subprocess.Popen([sys.executable, "-m", "computer_use.browser_check", "serve"],
            cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 5
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("Local browser test server exited")
                try:
                    with urllib.request.urlopen(URL, timeout=.5) as response:
                        if response.status == 200:
                            return self
                except OSError:
                    time.sleep(.1)
            raise RuntimeError("Local browser test server did not become ready")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)


def run() -> dict:
    report = {"model": False, "checks": {}}
    with PageServer(), NativeTransport() as transport:
        session = {"session": "mdo-browser-acceptance"}
        prepared = transport.call("browser_prepare", dict(session, allow_launch=True,
            profile={"mode": "isolated_new"}))["structured"]
        pid = prepared["prepared_pid"]
        windows = transport.call("list_windows", {"pid": pid})
        window = windows["structured"]["windows"][0]
        bound = transport.call("get_browser_state", dict(session, pid=pid,
            window_id=window["window_id"]))["structured"]
        target = dict(session, target_id=bound["target_id"], tab_id=bound["tabs"][0]["tab_id"])
        transport.call("browser_navigate", dict(target, url=URL))
        state = transport.call("get_browser_state", dict(target, include_screenshot=True))
        report["checks"]["initial_image"] = state["image_bytes"] > 1000

        def ref(snapshot, element_id):
            matching = [r["ref"] for r in snapshot["structured"]["refs"]
                        if ("id=" + element_id) in (r.get("label") or "").split()]
            if len(matching) != 1:
                raise RuntimeError(f"Expected one browser element {element_id}: {matching}")
            return matching[0]

        def act(tool, element_id, **arguments):
            current = transport.call("get_browser_state", target)
            return transport.call(tool, dict(target, ref=ref(current, element_id), **arguments))

        stale = ref(state, "apply")
        act("browser_type", "message", text="墨斗 Browser 验收", replace=True)
        refused = transport.call("browser_click", dict(target, ref=stale), require_success=False)
        report["checks"]["stale_ref_refused"] = (
            refused.get("structured", {}).get("error", {}).get("code") == "browser_ref_stale")
        act("browser_click", "apply")
        act("browser_click", "enabled")
        act("browser_select", "color", label="Green")
        act("browser_pointer", "scroller", action="scroll", delta_y=600)
        final = transport.call("get_browser_state", dict(target, include_screenshot=True))
        time.sleep(.2)  # allow the page's independent event POST to be written
        actual = report["oracle"] = json.loads(ORACLE.read_text(encoding="utf-8"))
        report["checks"].update(text=actual["text"] == "墨斗 Browser 验收",
            button_once=actual["clicks"] == 1, checkbox=actual["checked"] is True,
            selection=actual["color"] == "green", scroll=actual["scroll"] > 0,
            final_image=final["image_bytes"] > 1000, exact_binding=bound["binding_quality"] == "exact")
        transport.call("end_session", session)
        report["owned_browser_pid"] = pid
        report["checks"]["owned_windows_closed"] = not transport.call("list_windows", {"pid": pid})["structured"]["windows"]
        report["passed"] = all(report["checks"].values())
        write_json(STATE / "browser-transport.json", report)
        return report


def model_acceptance(model="ornith-1.5-35b", timeout=900, protocol=None) -> dict:
    from .__main__ import Application
    from .acceptance import wait_account, run_task
    report = {"model": model, "backend": "official Cua through mdo MCP",
              "prompt_workarounds": False, "protocol_requested": protocol}
    try:
        with PageServer(), Application() as app:
            app.ready()
            wait_account(app)
            prompt = (f"请使用 Computer Use 打开一个临时浏览器窗口，访问验收页 {URL}。"
                "在消息 Message 中输入“墨斗 Browser 验收”，点击 Apply 应用一次，"
                "勾选 Enable option 启用选项，将颜色 Color 选为 Green，向下滚动 Scroll area，"
                "最后查看页面截图并报告结果。只操作此验收页。")
            try:
                active = run_task(app, report, "Computer Use browser acceptance", prompt, timeout)
                actual = report["oracle"] = json.loads(ORACLE.read_text(encoding="utf-8")) if ORACLE.exists() else {}
                report["checks"] = {"run_succeeded": active.get("state") == "succeeded",
                    "text": actual.get("text") == "墨斗 Browser 验收", "button_once": actual.get("clicks") == 1,
                    "checkbox": actual.get("checked") is True, "selection": actual.get("color") == "green",
                    "scroll": actual.get("scroll", 0) > 0, "screenshot_retained": bool(report["image_parts"])}
                report["passed"] = all(report["checks"].values())
            finally:
                app.request("/api/v1/mcp/cua-driver/disconnect", "POST")
    except (OSError, ValueError, RuntimeError) as error:
        report.update(passed=False, error=str(error))
    finally:
        write_json(STATE / ("browser-acceptance" + ("-" + protocol if protocol else "") + ".json"), report)
    return report


def grant_check() -> dict:
    """Test official existing-profile authorization on an owned empty profile."""
    import os
    from pathlib import Path
    chrome = next((Path(base) / "Google/Chrome/Application/chrome.exe" for base in
                   (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""))
                   if (Path(base) / "Google/Chrome/Application/chrome.exe").is_file()), None)
    if chrome is None:
        raise RuntimeError("A system Google Chrome installation is required for this owned-profile test")
    profile = STATE / "browser-grant-profile"
    if profile.exists():
        raise RuntimeError(f"Inspect the previous owned test profile before rerunning: {profile}")
    profile.mkdir()
    process = None
    report = {"model": False, "checks": {}}
    completed = False
    try:
        with PageServer():
            process = subprocess.Popen([str(chrome), "--user-data-dir=" + str(profile),
                "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check",
                "--disable-component-update", "--new-window", URL], cwd=ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with NativeTransport() as transport:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    windows = transport.call("list_windows", {"pid": process.pid})["structured"]["windows"]
                    if len(windows) == 1:
                        break
                    if process.poll() is not None:
                        raise RuntimeError("Owned test browser exited before discovery")
                    time.sleep(.1)
                else:
                    raise RuntimeError("Owned test browser window did not appear")
                target = {"pid": process.pid, "window_id": windows[0]["window_id"],
                          "session": "mdo-existing-profile-test"}
                arguments = dict(target, strategy={"kind": "existing_profile"})
                denied = transport.call("browser_prepare", arguments, require_success=False)
                report["checks"]["ungranted_refused"] = "browser_consent_required" in denied["content"]
            with NativeTransport(grant_existing_profile=True) as transport:
                prepared = transport.call("browser_prepare", arguments)
                report["checks"]["explicit_grant_accepted"] = prepared["structured"].get("prepared") is True
                bound = transport.call("get_browser_state", target)["structured"]
                tab = dict(session=target["session"], target_id=bound["target_id"],
                           tab_id=bound["tabs"][0]["tab_id"])
                state = transport.call("get_browser_state", dict(tab, include_screenshot=True))
                field = next(r["ref"] for r in state["structured"]["refs"]
                             if "id=message" in (r.get("label") or "").split())
                transport.call("browser_type", dict(tab, ref=field, text="现有配置授权验收", replace=True))
                time.sleep(.2)
                actual = report["oracle"] = json.loads(ORACLE.read_text(encoding="utf-8"))
                report["checks"].update(text=actual["text"] == "现有配置授权验收",
                    exact_binding=bound["binding_quality"] == "exact", screenshot=state["image_bytes"] > 1000)
            report["checks"]["external_browser_preserved"] = process.poll() is None
            completed = True
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        # Delete only this call's new profile, after checking the final target.
        resolved = profile.resolve()
        if resolved.parent != STATE.resolve() or profile.is_symlink():
            raise RuntimeError("Refusing cleanup outside this test's owned profile directory")
        for attempt in range(50):
            try:
                shutil.rmtree(resolved)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(.1)
        report["checks"]["owned_profile_removed"] = not profile.exists()
        report["passed"] = completed and all(report["checks"].values())
        write_json(STATE / "browser-grant-check.json", report)
    return report


if __name__ == "__main__":
    if sys.argv[1:] == ["serve"]:
        serve()
    else:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
