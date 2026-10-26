"""Build this checkout with one SDK export and the existing locked mdo toolchain."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tarfile

from .__main__ import ROOT, STATE, write_json


def build(repository: Path) -> Path:
    repository = repository.resolve(strict=True)
    lock = json.loads((ROOT / "deps.lock").read_text(encoding="utf-8"))
    sdk = STATE / "sdk"
    marker = sdk / ".mdo-sdk-overlay.json"
    sys.path.insert(0, str(ROOT / "tools"))
    import build_mdo
    if not marker.exists():
        if sdk.exists():
            raise RuntimeError(f"Incomplete SDK export exists; inspect {sdk}")
        subprocess.run(["git", "cat-file", "-e", lock["xserver"]["commit"]], cwd=repository, check=True)
        sdk.mkdir(parents=True)
        # Stream the one dependency export; no worktree, clone, or tar copy.
        process = subprocess.Popen(["git", "archive", "--format=tar", lock["xserver"]["commit"]],
                                   cwd=repository, stdout=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                archive.extractall(sdk, filter="data")
            if process.wait() != 0:
                raise RuntimeError("The locked SDK source export failed")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()
        # This is mdo's already-locked dependency overlay, not a Cua patch.
        subprocess.run(["git", "apply", "--whitespace=nowarn",
                        str(ROOT / lock["sdk_overlay"]["path"])], cwd=sdk, check=True)
        build_mdo.verify_dependencies(sdk, lock)
        write_json(marker, lock["sdk_overlay"])
    if json.loads(marker.read_text(encoding="utf-8")) != lock["sdk_overlay"]:
        raise RuntimeError("SDK export differs from the current dependency lock")
    print("Building the current mdo source; details: .build/computer-use/build.log", flush=True)
    with (STATE / "build.log").open("wb") as log:
        subprocess.run([sys.executable, str(ROOT / "tools/build_mdo.py"),
                        "--xserver-root", str(sdk)], cwd=ROOT, check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    from .__main__ import sha256
    binary = ROOT / "mdo.exe"
    write_json(STATE / "deployment.json", {
        "schema_version": 1, "source": "current checkout via tools/build_mdo.py",
        "path": str(binary), "sha256": sha256(binary), "bytes": binary.stat().st_size,
        "version": json.loads((ROOT / "app/release.json").read_text(encoding="utf-8"))["version_name"],
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    })
    return ROOT / "mdo.exe"
