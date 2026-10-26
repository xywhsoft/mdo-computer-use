"""Opt-in, project-local dependencies using unchanged upstream binaries."""
from __future__ import annotations

import json
import csv
import os
from pathlib import Path
import shutil
import subprocess
import re
import urllib.request
import zipfile

from .__main__ import STATE, write_json
from .driver import LOCK, file_hash, verify

PERCEPTION = {
    "release": "https://github.com/trycua/cua/releases/download/cua-perception-v0.2.1/",
    "archive": "cua-perception-0.2.1-x86_64-pc-windows-msvc.tar.gz",
    "archive_bytes": 421313686,
    "archive_sha256": "6709579aa3f938e8200c0a51b1abe450d4fda51b09e97517e0cb4c272b5bff37",
    "catalog": "cua-perception-0.2.1-x86_64-pc-windows-msvc.catalog.json",
    "catalog_bytes": 924,
    "catalog_sha256": "bfb2300ff9da054d522e73351f7b337ba6157ebbe30f029a95a471fc3d13a042",
    "installed_bytes": 449715762,
    "license": "Mixed: MIT, Apache-2.0, AGPL-3.0-only, BSD-3-Clause",
}
FFMPEG = {
    "url": "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip",
    "bytes": 114768076,
    "sha256": "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
    "files": {
        "ffmpeg.exe": (105423872, "3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec"),
        "ffprobe.exe": (105221120, "f0d36ecbbdd3bcfac3efa078c96c7271c2e68b3810595552ac3b7f17e9a65c52"),
        "LICENSE": (35147, "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903"),
        "README.txt": (41577, "0342de6bb39dd421cbec2c00d89ad274b640d75ad3f2cab09ffd647ce2d8f949"),
    },
    "license": "GPL-3.0-or-later (Gyan essentials build; separate executable)",
}


def checked(path, size, digest):
    return path.is_file() and not path.is_symlink() and path.stat().st_size == size and file_hash(path) == digest


def download(url, path, size, digest):
    if path.exists():
        if not checked(path, size, digest):
            raise ValueError(f"Cached dependency does not match its pin: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".download")
    try:
        with urllib.request.urlopen(url, timeout=60) as source, partial.open("wb") as output:
            count = 0
            while block := source.read(1024 * 1024):
                count += len(block)
                if count > size:
                    raise ValueError("Download exceeds the pinned size")
                output.write(block)
        if not checked(partial, size, digest):
            raise ValueError("Dependency download size or SHA-256 mismatch")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def environment():
    """Pass normal upstream dependency settings only to this launched process."""
    ffmpeg = STATE / "ffmpeg/9.0.2"
    for name, (size, digest) in FFMPEG["files"].items():
        if not checked(ffmpeg / name, size, digest):
            raise ValueError("Run python -m computer_use addons --install first")
    return {"PATH": str(ffmpeg) + os.pathsep + os.environ.get("PATH", ""),
            "CUA_DRIVER_RS_HOME": str(STATE / "cua-home"),
            "CUA_DRIVER_PERCEPTION_CATALOG": str(STATE / "perception" / PERCEPTION["catalog"])}


def prepare():
    if os.name != "nt":
        raise RuntimeError("Optional dependencies are pinned for Windows x64; add a reviewed platform pin first")
    if shutil.disk_usage(STATE).free < 2 * 1024**3:
        raise RuntimeError("At least 2 GiB free is required for bounded optional dependency installation")
    home = STATE / "cua-home"
    home.mkdir(exist_ok=True)
    if home.is_symlink() or home.resolve().parent != STATE.resolve():
        raise ValueError("Extension data must remain in the owned project runtime directory")
    if not (home / "extensions").exists():
        # Project directories on D: may inherit only Modify for the current
        # non-elevated user. Upstream needs WRITE_OWNER to harden its own store.
        # Grant only this user full control of this owned data directory; Cua
        # subsequently applies and verifies its own stricter extension ACLs.
        identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"])
        sid = next(csv.reader(identity.decode("utf-8", errors="replace").strip().splitlines()))[-1]
        if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
            raise RuntimeError("Cannot determine the current Windows user SID")
        subprocess.run(["icacls", str(home), "/grant", "*" + sid + ":(OI)(CI)F"],
                       stdout=subprocess.DEVNULL, check=True)
    archive = download(FFMPEG["url"], STATE / "downloads" / FFMPEG["url"].rsplit("/", 1)[1],
                       FFMPEG["bytes"], FFMPEG["sha256"])
    folder = STATE / "ffmpeg/9.0.2"
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for name, (size, digest) in FFMPEG["files"].items():
            path = folder / name
            if path.exists():
                if not checked(path, size, digest):
                    raise ValueError(f"Installed FFmpeg file differs from its pin: {name}")
                continue
            member = "ffmpeg-9.0.2-essentials_build/" + ("bin/" if name.endswith(".exe") else "") + name
            if source.getinfo(member).file_size != size:
                raise ValueError("Unexpected FFmpeg archive member size")
            with source.open(member) as inp, path.open("wb") as output:
                shutil.copyfileobj(inp, output, length=1024 * 1024)
            if not checked(path, size, digest):
                raise ValueError("FFmpeg member SHA-256 mismatch")
    for kind in ("catalog", "archive"):
        download(PERCEPTION["release"] + PERCEPTION[kind], STATE / "perception" / PERCEPTION[kind],
                 PERCEPTION[kind + "_bytes"], PERCEPTION[kind + "_sha256"])
    return environment()


def driver_command(*arguments):
    driver = verify(STATE / "cua" / LOCK["version"])
    result = subprocess.run([str(driver), *arguments, "--json"], env=dict(os.environ, **environment()),
        capture_output=True, text=True, encoding="utf-8", timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def install():
    prepare()
    catalog = str(STATE / "perception" / PERCEPTION["catalog"])
    review = driver_command("extension", "inspect", "cua-perception", "--catalog", catalog)
    if (not review["publisher_signature_verified"] or review["version"] != "0.2.1"
            or review["archive_sha256"] != PERCEPTION["archive_sha256"]
            or review["installed_size"] != PERCEPTION["installed_bytes"]):
        raise ValueError("Official signed perception review differs from the pinned plan")
    before = driver_command("extension", "status", "cua-perception")
    if not before["healthy"]:
        raise RuntimeError(before["detail"])
    if before["installed"]:
        if before["active_version"] != "0.2.1" or before["trust"] != "publisher-verified":
            raise ValueError("A different extension is installed; review it before updating")
        result = {"reused": True}
    else:
        result = driver_command("extension", "install", "cua-perception", "--catalog", catalog)
    status = driver_command("extension", "status", "cua-perception", "--self-test")
    write_json(STATE / "addons.json", {"perception_review": review, "install": result, "status": status,
                                     "ffmpeg": FFMPEG})
    return {"perception": status, "ffmpeg": str(STATE / "ffmpeg/9.0.2/ffmpeg.exe")}
