"""Run with python -m computer_use; credentials never enter deployment receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
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

    def __init__(self, port: int = 5391, headless: bool = True):
        self.port, self.headless = port, headless
        self.process: subprocess.Popen | None = None
        self.log = None

    def __enter__(self):
        executable = ROOT / ("mdo.exe" if os.name == "nt" else "mdo")
        if not executable.is_file():
            raise RuntimeError("Deploy mdo first: python -m computer_use deploy --mdo PATH")
        STATE.mkdir(parents=True, exist_ok=True)
        write_json(ROOT / "xs.json", configuration(self.port, self.headless))
        self.log = (STATE / "mdo.log").open("wb")
        env = dict(os.environ)
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

    def request(self, path: str, method: str = "GET", body: dict | None = None):
        headers = {}
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
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    deploy_parser = commands.add_parser("deploy", help="Reuse one existing mdo executable")
    deploy_parser.add_argument("--mdo", type=Path, required=True)
    for name in ("smoke", "run"):
        command = commands.add_parser(name)
        command.add_argument("--port", type=int, default=5391)
        command.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "deploy":
            print(json.dumps(deploy(args.mdo), indent=2))
        else:
            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            with Application(args.port, args.command == "smoke" or args.headless) as app:
                state = app.ready()
                if args.command == "smoke":
                    result = {"ready": state["ready"], "stage": state["stage"],
                              "port": args.port, "home": str(HOME)}
                    write_json(STATE / "smoke.json", result)
                    print(json.dumps(result, indent=2))
                else:
                    print(f"mdo ready at http://127.0.0.1:{args.port}; Ctrl+C stops this process", flush=True)
                    app.process.wait()
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f"computer-use: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
