"""Native catalog lifetime regression, directly in this checkout; no model/UI."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from computer_use.__main__ import STATE, write_json


def run_fixture(name, source):
    config = ROOT / "xs.json"
    write_json(config, {"services": [{"enabled": True, "class": "http", "name": "catalog-probe",
        "ip": "127.0.0.1", "port": 5392,
        "host_default": {"enabled": True, "name": "catalog-probe", "path": "app/web",
                         "devlang": "c", "devfile": source}}]})
    result = subprocess.run([str(ROOT / ".build/host/xs.exe"), str(config)], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    output = result.stdout.decode("utf-8", errors="replace")
    (STATE / (name + ".log")).write_text(output, encoding="utf-8")
    return result.returncode, output


def main():
    code, output = run_fixture("catalog-lifetime", "tests/fixtures/computer-use-catalog.c")
    print(output)
    return 0 if code == 0 and "catalog_lifetime=PASS" in output else 1


if __name__ == "__main__":
    raise SystemExit(main())
