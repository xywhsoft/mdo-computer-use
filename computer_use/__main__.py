"""Run with python -m computer_use; credentials never enter deployment receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".build/computer-use"
HOME = ROOT / "mdo-home"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def deploy(source: Path) -> dict:
    source = source.resolve(strict=True)
    target = ROOT / ("mdo.exe" if os.name == "nt" else "mdo")
    digest = sha256(source)
    if not target.is_file() or sha256(target) != digest:
        shutil.copy2(source, target)
    receipt = {"schema_version": 1, "source": str(source),
               "path": str(target), "sha256": digest, "bytes": target.stat().st_size}
    write_json(STATE / "deployment.json", receipt)
    return receipt


def configuration(port: int, headless: bool) -> dict:
    service = {"enabled": True, "class": "http" if headless else "app",
               "name": "mdo", "ip": "127.0.0.1", "port": port,
               "recv_limit": 104988672, "body_limit": 104873984,
               "host_default": {"enabled": True, "name": "mdo", "path": "web",
                                "devlang": "c", "devfile": "generated/mdo_unity.c"}}
    if not headless:
        upstream = json.loads((ROOT / "app/xs.json").read_text(encoding="utf-8"))
        service["window"] = upstream["services"][0]["window"]
    return {"services": [service]}


class Application:
    """One project-local application process, with explicit ownership and cleanup."""

    def __init__(self, port: int = 5391, headless: bool = True, environment=None):
        self.port, self.headless = port, headless
        self.environment = environment or {}
        self.process: subprocess.Popen | None = None
        self.log = None

    def __enter__(self):
        executable = ROOT / ("mdo.exe" if os.name == "nt" else "mdo")
        if not executable.is_file():
            raise RuntimeError("Deploy mdo first: python -m computer_use deploy --mdo PATH")
        # Refuse an occupied port rather than accidentally validating another app.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", self.port))
        STATE.mkdir(parents=True, exist_ok=True)
        write_json(ROOT / "xs.json", configuration(self.port, self.headless))
        self.log = (STATE / "mdo.log").open("wb")
        env = dict(os.environ)
        env.update(self.environment)
        if self.headless:
            env["USE_WEBVIEW"] = "0"
        try:
            self.process = subprocess.Popen(
                [str(executable), "--", "--home", str(HOME)], cwd=ROOT, env=env,
                stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def request(self, path: str, method: str = "GET", body: dict | None = None,
                headers: dict | None = None):
        headers = dict(headers or {})
        if method not in ("GET", "HEAD", "OPTIONS"):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/v1/bootstrap", timeout=3) as response:
                headers["X-Mdo-Write-Token"] = response.headers["X-Mdo-Write-Token"]
        data = None if body is None else json.dumps(body).encode("utf-8")
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}" + path,
                                     data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=35) as response:
            return json.load(response)

    def ready(self, timeout: float = 20) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("mdo exited; inspect .build/computer-use/mdo.log")
            try:
                result = self.request("/api/v1/bootstrap")
                if result.get("data", {}).get("ready"):
                    expected = json.loads((ROOT / "app/release.json").read_text(encoding="utf-8"))["version_name"]
                    actual = result["data"].get("version")
                    if actual != expected:
                        raise RuntimeError(f"Deployed mdo version {actual} differs from source {expected}; run computer_use build")
                    return result["data"]
                if result.get("data", {}).get("stage") == "failed":
                    raise RuntimeError("mdo bootstrap failed; inspect local log")
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        raise RuntimeError("mdo readiness deadline exceeded; inspect local log")

    def __exit__(self, *_):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    deploy_parser = commands.add_parser("deploy", help="Reuse one existing mdo executable")
    deploy_parser.add_argument("--mdo", type=Path, required=True)
    build_parser = commands.add_parser("build", help="Build this checkout with one locked SDK export")
    build_parser.add_argument("--xserver-repository", type=Path, required=True)
    driver_parser = commands.add_parser("driver", help="Install/verify the pinned official Cua ZIP")
    driver_parser.add_argument("--archive", type=Path, help="Reuse an existing official archive")
    config_parser = commands.add_parser("configure", help="Configure the project-local Cua connection")
    config_parser.add_argument("--driver", type=Path)
    config_parser.add_argument("--enable", action="store_true")
    config_parser.add_argument("--replace", action="store_true")
    config_parser.add_argument("--grant-existing-profile", action="store_true",
        help="Explicitly authorize official Cua to attach existing Chromium profiles")
    commands.add_parser("package", help="Build an importable mdo MCP service template")
    commands.add_parser("probe", help="Verify real mdo/Cua discovery and disconnect")
    commands.add_parser("install-template", help="Import the public template through the native mdo API")
    commands.add_parser("verify-template", help="Verify native template connection creation and removal")
    addons_parser = commands.add_parser("addons", help="Inspect or install pinned optional local dependencies")
    addons_parser.add_argument("--install", action="store_true")
    tools_parser = commands.add_parser("tool-check", help="Run per-tool native acceptance on owned fixtures")
    tools_parser.add_argument("--addons", action="store_true")
    tools_parser.add_argument("--scope", choices=("desktop", "browser", "all"), default="all")
    acceptance_parser = commands.add_parser("acceptance", help="Run the real account model on the project test window")
    acceptance_parser.add_argument("--model", default="ornith-1.5-35b")
    acceptance_parser.add_argument("--timeout", type=int, default=900)
    acceptance_parser.add_argument("--scope", choices=("desktop", "browser"), default="desktop")
    acceptance_parser.add_argument("--protocol", choices=("openai-responses", "openai-chat-completions", "anthropic-messages"))
    acceptance_parser.add_argument("--scenario", choices=("form", "click"), default="form")
    check_parser = commands.add_parser("transport-check", help="Exercise native Cua desktop/browser actions without a model")
    check_parser.add_argument("--scope", choices=("desktop", "browser", "browser-grant", "all"), default="all")
    for name in ("smoke", "run"):
        command = commands.add_parser(name)
        command.add_argument("--port", type=int, default=5391)
        command.add_argument("--headless", action="store_true")
        command.add_argument("--addons", action="store_true",
            help="Use the explicitly installed project-local FFmpeg and perception extension")
    args = parser.parse_args()
    try:
        if args.command == "deploy":
            print(json.dumps(deploy(args.mdo), indent=2))
        elif args.command == "build":
            from .build import build
            print(build(args.xserver_repository))
        elif args.command == "addons":
            from .addons import FFMPEG, PERCEPTION, install
            print(json.dumps(install() if args.install else {"ffmpeg": FFMPEG, "perception": PERCEPTION},
                             ensure_ascii=False, indent=2))
        elif args.command == "tool-check":
            from .coverage import desktop, browser, summarize
            from .addons import environment
            env = environment() if args.addons else None
            reports = {}
            if args.scope in ("desktop", "all"):
                reports["desktop"] = desktop(env)
            if args.scope in ("browser", "all"):
                reports["browser"] = browser(env)
            result = summarize(reports)
            print(json.dumps({k: result[k] for k in ("passed", "complete", "tools", "functional")}, indent=2))
            return 0 if result["passed"] else 1
        elif args.command == "acceptance":
            from .acceptance import run, summary
            if args.scope == "browser":
                from .browser_check import model_acceptance as run
                if args.scenario != "form":
                    raise ValueError("The click scenario applies to desktop acceptance only")
                report = run(args.model, args.timeout, args.protocol)
            else:
                report = run(args.model, args.timeout, args.protocol, args.scenario)
            print(json.dumps(summary(report), ensure_ascii=False, indent=2))
            return 0 if report["passed"] else 1
        elif args.command == "transport-check":
            from .transport_check import desktop
            from .browser_check import run as browser, grant_check
            reports = {}
            if args.scope in ("desktop", "all"):
                reports["desktop"] = desktop()
            if args.scope in ("browser", "all"):
                reports["browser"] = browser()
            if args.scope == "browser-grant":
                reports["browser_grant"] = grant_check()
            write_json(STATE / "transport-check.json", reports)
            print(json.dumps(reports, ensure_ascii=False, indent=2))
            return 0 if all(r["passed"] for r in reports.values()) else 1
        elif args.command in ("driver", "configure", "package", "probe", "install-template", "verify-template"):
            from . import driver
            if args.command == "driver":
                executable = driver.install(STATE, args.archive)
                write_json(STATE / "driver.json", {"version": driver.LOCK["version"],
                           "path": str(executable), "sha256": sha256(executable)})
                print(executable)
            elif args.command == "package":
                path = STATE / "computer-use.mdo-extension.json"
                write_json(path, driver.extension_package())
                print(path)
            elif args.command in ("probe", "install-template", "verify-template"):
                from .integration import probe, install_template, verify_template
                with Application() as app:
                    app.ready()
                    result = {"probe": probe, "install-template": install_template,
                              "verify-template": verify_template}[args.command](app)
                    write_json(STATE / (args.command + ".json"), result)
                    if args.command == "install-template":
                        result = {"installed": result["installed"], "template_id": result["template_id"],
                                  "receipt_key": result["item"]["receipt"]["key"]}
                    print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                executable = args.driver or STATE / "cua" / driver.LOCK["version"] / "cua-driver.exe"
                config = driver.connection(executable, args.enable, args.grant_existing_profile)
                path = HOME / "mcp/cua-driver.json"
                if path.exists() and not args.replace and json.loads(path.read_text(encoding="utf-8")) != config:
                    raise ValueError("Connection already differs; use --replace to explicitly replace it")
                write_json(path, config)
                print(path)
        else:
            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            environment = None
            if args.addons:
                from .addons import environment as addon_environment
                environment = addon_environment()
            with Application(args.port, args.command == "smoke" or args.headless, environment) as app:
                state = app.ready()
                if args.command == "smoke":
                    result = {"ready": state["ready"], "stage": state["stage"],
                              "version": state["version"], "port": args.port, "home": str(HOME)}
                    write_json(STATE / "smoke.json", result)
                    print(json.dumps(result, indent=2))
                else:
                    print(f"mdo ready at http://127.0.0.1:{args.port}; Ctrl+C stops this process", flush=True)
                    app.process.wait()
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"computer-use: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
