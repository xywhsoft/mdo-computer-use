"""Own local browser fixture and its independent event oracle."""
from __future__ import annotations

import http.server
import json
import socket
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


if __name__ == "__main__":
    if sys.argv[1:] == ["serve"]:
        serve()
    else:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
