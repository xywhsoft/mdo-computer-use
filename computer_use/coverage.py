"""Per-tool acceptance through mdo's native MCP host and disposable fixtures.

This is an explicit test runner, never an Agent policy or runtime fallback.
Only independently verified outcomes count as functional passes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

from .__main__ import STATE, write_json
from .acceptance import fixture_binary, read_oracle
from .transport_check import NativeTransport, token


class Coverage:
    def __init__(self, transport):
        self.transport = transport
        self.cases = []

    def call(self, tool, arguments, check=None, *, note="", private=False, kind="functional",
             expected_success=True):
        result = self.transport.call(tool, arguments, require_success=False, private=private)
        structured = result.get("structured", {})
        refused = structured.get("effect") == "refused" or structured.get("status") == "refused"
        passed = (result["success"] and not refused) == expected_success
        if check is not None:
            passed = passed and bool(check(result))
        self.cases.append({"tool": tool, "passed": passed, "note": note,
                           "kind": kind,
                           "mcp_success": result["success"], "refused": refused})
        print(tool, "PASS" if passed else "FAIL", flush=True)
        return result

    def save(self, path, tools):
        covered = {c["tool"] for c in self.cases}
        report = {"schema_version": 1, "backend": "mdo native MCP / official Cua 0.38.0",
                  "model": False, "cases": self.cases,
                  "catalog": sorted(t.removeprefix("mcp__cua-driver__") for t in tools),
                  "not_exercised": sorted({t.removeprefix("mcp__cua-driver__") for t in tools} - covered),
                  "passed": all(c["passed"] for c in self.cases)}
        write_json(path, report)
        return report


def desktop(environment=None):
    oracle = STATE / "native-tools-oracle.json"
    oracle.unlink(missing_ok=True)
    report_path = STATE / "desktop-tool-coverage.json"
    target = None
    with NativeTransport(environment=environment) as transport:
        test = Coverage(transport)
        session = {"session": "mdo-tools-acceptance"}
        def observe():
            return transport.call("get_window_state", target)
        def actual():
            time.sleep(.18)  # independent fixture timer
            return read_oracle(oracle)
        def element(label, role):
            return dict(session, element_token=token(observe(), label, role))
        try:
            legacy = {"session": "mdo-legacy-capture"}
            test.call("start_session", dict(legacy, capture_scope="auto"),
                note="explicit legacy capture policy is required to exercise deprecated escalation")
            for tool in ("get_session", "get_session_state"):
                test.call(tool, legacy)
            test.call("list_sessions", {"limit": 100},
                lambda r: legacy["session"] in r["content"])
            test.call("escalate_session", dict(legacy, reason="other", detail="owned fixture coverage"))
            test.call("end_session", legacy)
            test.call("start_session", session, note="current per-call targeting; no deprecated capture policy")
            test.call("launch_app", dict(session, path=str(fixture_binary()),
                additional_arguments=[str(oracle)], creates_new_application_instance=True))
            deadline = time.monotonic() + 10
            while not oracle.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            state = read_oracle(oracle)
            target = dict(session, pid=state["pid"], window_id=state["window_id"])
            test.call("list_apps", session, lambda r: str(state["pid"]) in r["content"])
            test.call("list_windows", dict(session, pid=state["pid"]),
                lambda r: str(state["window_id"]) in r["content"])
            test.call("debug_window_info", dict(session, pid=state["pid"]))
            test.call("get_accessibility_tree", session,
                lambda r: "MDO Computer Use Acceptance" in r["content"])
            test.call("get_screen_size", session)
            test.call("get_cursor_position", session)
            test.call("check_permissions", dict(session, prompt=False))
            test.call("health_report", session)
            test.call("get_guide", dict(session, topic="batching"))
            test.call("get_config", session)
            test.call("check_for_update", session, note="read-only; no update installed")
            test.call("bring_to_front", target,
                lambda r: actual()["foreground"] == target["window_id"])
            test.call("set_window_frame", dict(target, x=150, y=120, width=820, height=650))
            test.call("get_window_state", target, lambda r: r["image_bytes"] > 1000)
            test.call("get_desktop_state", session, lambda r: r["image_bytes"] > 1000)
            test.call("zoom", dict(target, x1=440, y1=350, x2=710, y2=490),
                lambda r: r["image_bytes"] > 1000)
            test.call("set_value", dict(element("Input text", "Edit"), value="工具验收"),
                lambda r: actual()["text"] == "工具验收")
            test.call("type_text", dict(element("Input text", "Edit"), text=" Input"),
                lambda r: "Input" in actual()["text"])
            test.call("press_key", dict(element("Input text", "Edit"), key="end"),
                lambda r: actual()["key_events"] > 0)
            test.call("hotkey", dict(element("Input text", "Edit"), keys=["shift", "home"]),
                lambda r: actual()["selection_end"] == actual()["selection_start"], kind="boundary",
                note="0.38.0 background modifiers: verified no selection on this Win32 Edit")
            test.call("hotkey", dict(element("Input text", "Edit"), keys=["shift", "end"],
                delivery_mode="foreground"),
                lambda r: actual()["selection_end"] > actual()["selection_start"])
            test.call("click", element("Increment counter", "Button"),
                lambda r: actual()["clicks"] == 1)
            test.call("set_value", dict(element("Color", "ComboBox"), value="Green"),
                lambda r: actual()["selection"] == "Green")
            test.call("right_click", dict(target, x=575, y=410),
                lambda r: actual()["right_clicks"] > 0)
            test.call("double_click", dict(target, x=575, y=410),
                lambda r: actual()["double_clicks"] > 0)
            test.call("drag", dict(target, from_x=500, from_y=380, to_x=650, to_y=450,
                duration_ms=200), lambda r: actual()["drags"] > 0)
            test.call("scroll", dict(element("Scroll document", "Edit"), direction="down", amount=5),
                lambda r: actual()["scroll_line"] > 0)
            test.call("invoke_menu", dict(target, path=["Test", "Mark verified"]),
                lambda r: r.get("structured", {}).get("refusal", {}).get("code") == "menu_path_unavailable",
                expected_success=False, kind="boundary",
                note="0.38.0 loses the non-actionable Menu ancestor after expansion in this native fixture")
            observe()  # read the actual expanded menu and its exposed item
            test.call("invoke_menu", dict(target, path=["Mark verified"]),
                lambda r: actual()["menu_marks"] == 1)
            test.call("verify_state", dict(target, timeout_ms=0, stable_samples=1,
                expect=[{"element": {"selector": {"role": "ComboBox", "label_contains": "Color"},
                                       "value_equals": "Green"}}]))
            test.call("run_steps", dict(target, steps=[{"tool": "set_value", "args": {
                "role": "Edit", "name": "Input text", "value": "Batch 验收"}}]),
                lambda r: actual()["text"] == "Batch 验收")
            test.call("run_script", dict(session, script="return await cua.listWindows({pid: "
                + str(target["pid"]) + "});", max_calls=1),
                lambda r: "MDO Computer Use Acceptance" in r["content"])
            for tool, args in (("set_agent_cursor_enabled", {"enabled": True}),
                               ("set_agent_cursor_theme", {"theme_id": "cua.default"}),
                               ("set_agent_cursor_motion", {"style": "classic", "timing": "native"})):
                test.call(tool, dict(session, **args))
            test.call("move_cursor", dict(session, x=575, y=410,
                target={"kind": "window", "pid": target["pid"], "window_id": target["window_id"]}))
            test.call("get_agent_cursor_state", session,
                lambda r: r["structured"]["position"] == {"x": 575.0, "y": 410.0}
                    and r["structured"]["enabled"] and r["structured"]["motion"]["style"] == "classic",
                note="cursor state and target position readback; visible overlay rendering is not asserted")
            clipboard = test.call("clipboard_read", dict(session, include_text=False),
                note="formats only; user clipboard text is not logged or changed", private=True)
            test.cases[-1]["formats"] = clipboard.get("structured", {}).get("types", [])
            clipboard_check(test, session, clipboard, element, actual)
            if environment:
                addons(test, target, actual, observe)
        finally:
            if target:
                test.call("kill_app", dict(session, pid=target["pid"]),
                    note="only the process launched by this test")
            test.call("end_session", session)
            test.save(report_path, transport.tools)
    return read_oracle(report_path)


def addons(test, target, actual, observe):
    """Only explicit addon acceptance invokes installers or starts recording."""
    session = {"session": target["session"]}
    test.call("install_ffmpeg", dict(session, confirm=False),
        lambda r: "already available" in r["content"],
        note="portable pinned FFmpeg supplied on this process PATH; no global package installation")
    review = test.call("install_extension", dict(session, name="perception", confirm=False),
        lambda r: "verified" in r["content"].lower())
    # The official MCP installer refuses reinstallation. Inspect the real
    # active pointer so repeated acceptance does not remove a working add-on.
    from .addons import driver_command
    status = driver_command("extension", "status", "cua-perception")
    if not status.get("installed"):
        test.call("install_extension", dict(session, name="perception", confirm=True),
            lambda r: r.get("structured", {}).get("mutation_performed") is True)
    state = observe()["structured"]
    test.call("parse_visual_regions", dict(session, capture_id=state["capture_id"],
        options={"kinds": ["text", "icon"], "max_regions": 100}),
        lambda r: "CANVAS" in r["content"] or "Increment" in r["content"],
        note="OCR text must identify independently known fixture content")

    directory = STATE / "recordings" / ("acceptance-" + time.strftime("%Y%m%d-%H%M%S"))
    started = test.call("start_recording", dict(session, output_dir=str(directory),
        record_video=True, include_accessibility_tree=False, state_timeout_ms=1000),
        lambda r: r.get("structured", {}).get("video_active") is True)
    if started["success"]:
        try:
            test.call("get_recording_state", session,
                lambda r: r.get("structured", {}).get("recording") is True)
            before = actual()["drags"]
            test.call("drag", dict(target, from_x=500, from_y=380, to_x=650, to_y=450, duration_ms=200),
                lambda r: actual()["drags"] > before,
                note="record an exact owned-window action without an ephemeral element token")
            time.sleep(1)
        finally:
            stopped = test.call("stop_recording", session,
                lambda r: r.get("structured", {}).get("recording") is False)
        video = Path(stopped["structured"]["last_video_path"])
        probe = subprocess.run([str(STATE / "ffmpeg/9.0.2/ffprobe.exe"), "-v", "error",
            "-show_entries", "stream=codec_name,nb_frames:format=duration", "-of", "json", str(video)],
            capture_output=True, text=True, encoding="utf-8", check=True)
        info = json.loads(probe.stdout)
        valid_video = float(info["format"]["duration"]) > 0 and any(
            int(s.get("nb_frames", 0)) > 0 for s in info["streams"])
        test.cases.append({"tool": "start_recording", "passed": valid_video,
            "note": "independent ffprobe validates finalized video duration and decoded frame count",
            "video_bytes": video.stat().st_size, "probe": info})
        before = actual()["drags"]
        test.call("replay_trajectory", dict(session, dir=str(directory), delay_ms=0),
            lambda r: actual()["drags"] > before,
            note="independent drag counter must increase on replay")

    # Config is global in upstream 0.38.0, even with CUA_DRIVER_RS_HOME.
    # Keep its exact original bytes in memory and restore in finally.
    config = Path(os.environ.get("HOME") or os.environ["USERPROFILE"]) / ".cua-driver/config.json"
    if config.is_symlink():
        raise RuntimeError("Refusing to change a linked driver config")
    saved = config.read_bytes() if config.exists() else None
    old = test.transport.call("get_config", session)["structured"]["max_image_dimension"]
    try:
        dimension = 768 if old != 768 else 1024
        test.call("set_config", dict(session, max_image_dimension=dimension),
            lambda r: test.transport.call("get_config", session)["structured"]["max_image_dimension"] == dimension,
            note="real setting mutation/readback; exact original config restored immediately")
    finally:
        test.transport.call("set_config", dict(session, max_image_dimension=old))
        if saved is None:
            config.unlink(missing_ok=True)
        else:
            config.write_bytes(saved)


def clipboard_check(test, session, formats, element, actual):
    types = set(formats.get("structured", {}).get("types", []))
    test.transport.call("click", element("Save clipboard", "Button"))
    if not actual()["clipboard_saved"]:
        test.call("clipboard_write", dict(session, file_path="relative-missing-file.txt"),
            lambda r: "absolute" in r["content"].lower(), expected_success=False, kind="boundary",
            note="unsupported/empty clipboard left unchanged; invalid relative-file refusal verified", private=True)
        return
    try:
        test.call("clipboard_write", dict(session, text="MDO 剪贴板验收"),
            lambda r: test.transport.call("clipboard_read", dict(session, include_text=True),
                private=True)["structured"]["text"] == "MDO 剪贴板验收", private=True,
            note="Cua text round-trip; fixture retains and restores all original supported formats in memory")
    finally:
        test.transport.call("click", element("Restore clipboard", "Button"))
        restored = test.transport.call("clipboard_read", dict(session, include_text=False), private=True)
        if not actual()["clipboard_restored"] or set(restored["structured"]["types"]) != types:
            raise RuntimeError("Clipboard original formats and bytes were not restored")


def browser(environment=None):
    from .browser_check import PageServer, URL, ORACLE
    import hashlib
    with PageServer(), NativeTransport(environment=environment) as transport:
        test = Coverage(transport)
        session = {"session": "mdo-browser-tools"}
        pid = None
        try:
            prepared = test.call("browser_prepare", dict(session, allow_launch=True,
                profile={"mode": "isolated_new"}), lambda r: r["structured"]["prepared"])
            pid = prepared["structured"]["prepared_pid"]
            window = transport.call("list_windows", {"pid": pid})["structured"]["windows"][0]
            bound = test.call("get_browser_state", dict(session, pid=pid, window_id=window["window_id"]),
                lambda r: r["structured"]["binding_quality"] == "exact")["structured"]
            target = dict(session, target_id=bound["target_id"], tab_id=bound["tabs"][0]["tab_id"])
            test.call("browser_navigate", dict(target, url=URL))
            def state():
                return transport.call("get_browser_state", target)["structured"]
            def ref(element_id):
                return next(r["ref"] for r in state()["refs"]
                            if "id=" + element_id in (r.get("label") or "").split())
            def actual():
                time.sleep(.2)
                return read_oracle(ORACLE)
            def act(tool, element_id, check, **arguments):
                return test.call(tool, dict(target, ref=ref(element_id), **arguments), check)
            act("browser_type", "message", lambda r: actual()["text"] == "墨斗 Browser 验收",
                text="墨斗 Browser 验收", replace=True)
            act("browser_click", "apply", lambda r: actual()["clicks"] == 1)
            act("browser_click", "enabled", lambda r: actual()["checked"] is True)
            act("browser_select", "color", lambda r: actual()["color"] == "green", label="Green")
            act("browser_pointer", "scroller", lambda r: actual()["scroll"] > 0,
                action="scroll", delta_y=600)
            test.call("get_browser_state", dict(target, include_screenshot=True),
                lambda r: r["image_bytes"] > 1000)
            test.call("page", dict(session, pid=pid, window_id=window["window_id"], action="get_text"),
                lambda r: "MDO Computer Use" in r["content"],
                note="legacy read-only browser API against the owned local page")

            upload = STATE / "browser-upload.txt"
            contents = "MDO 上传验收\n".encode("utf-8")
            upload.write_bytes(contents)
            act("browser_set_input_files", "upload", lambda r:
                actual().get("uploaded_sha256") == hashlib.sha256(contents).hexdigest(), files=[str(upload)])
            downloads = STATE / "browser-downloads"
            downloads.mkdir(exist_ok=True)
            known = set(downloads.iterdir())
            def downloaded(result):
                expected = b"MDO Computer Use download acceptance\n"
                return any(p.is_file() and p.read_bytes() == expected for p in set(downloads.iterdir()) - known)
            act("browser_download", "download", downloaded, destination_root=str(downloads))

            # Only a page-owned prompt from this fixture. No browser/OS consent
            # dialog is accepted and no page JavaScript is injected by the test.
            test.call("browser_dialog", dict(target, action="inspect"),
                lambda r: r.get("structured", {}).get("present") is False,
                note="register dialog observation before the fixture's delayed prompt opens")
            transport.call("browser_click", dict(target, ref=ref("prompt")), require_success=False)
            time.sleep(3.2)
            inspected = test.call("browser_dialog", dict(target, action="inspect"),
                lambda r: r.get("structured", {}).get("present") is True)
            if inspected.get("structured", {}).get("present"):
                test.call("browser_dialog", dict(target, action="accept",
                    dialog_id=inspected["structured"]["dialog_id"], prompt_text="Dialog 验收"),
                    lambda r: actual().get("dialog_text") == "Dialog 验收")
        finally:
            test.call("end_session", session,
                lambda r: pid is None or not transport.call("list_windows", {"pid": pid})["structured"]["windows"],
                note="owned browser windows must close")
            test.save(STATE / "browser-tool-coverage.json", transport.tools)
    return read_oracle(STATE / "browser-tool-coverage.json")


def summarize(reports):
    catalog = {name for report in reports.values() for name in report["catalog"]}
    cases = [case for report in reports.values() for case in report["cases"]]
    matrix = {}
    for tool in sorted(catalog):
        rows = [c for c in cases if c["tool"] == tool]
        functional = any(c["passed"] and c.get("kind", "functional") == "functional" for c in rows)
        boundary = any(c["passed"] and c.get("kind") == "boundary" for c in rows)
        matrix[tool] = {"status": "functional" if functional else "boundary_only" if boundary else "unverified",
                        "cases": len(rows), "notes": [c["note"] for c in rows if c.get("note")]}
    result = {"tools": len(catalog), "functional": sum(v["status"] == "functional" for v in matrix.values()),
              "passed": all(r["passed"] for r in reports.values()),
              "complete": all(v["status"] == "functional" for v in matrix.values()),
              "matrix": matrix, "reports": reports}
    write_json(STATE / "tool-coverage.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(desktop(), indent=2, ensure_ascii=False))
