"""Install the pinned official driver; no code rewriting or runtime hooks."""
from __future__ import annotations

import hashlib
import json
import base64
import zlib
from pathlib import Path
import shutil
import urllib.request
import zipfile

PACKAGE = Path(__file__).resolve().parent
LOCK = json.loads((PACKAGE / "cua-driver.lock.json").read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(directory: Path) -> Path:
    for name, expected in LOCK["files"].items():
        path = directory / name
        if (not path.is_file() or path.is_symlink()
                or path.stat().st_size != expected["bytes"]
                or file_hash(path) != expected["sha256"]):
            raise ValueError(f"Official Cua {LOCK['version']} file missing or changed: {name}")
    return directory / "cua-driver.exe"


def install(root: Path, archive: Path | None = None) -> Path:
    root = root.resolve()
    target = root / "cua" / LOCK["version"]
    if target.exists():
        return verify(target)
    if archive is None:
        archive = root / "downloads" / LOCK["url"].rsplit("/", 1)[1]
        if not archive.exists():
            archive.parent.mkdir(parents=True, exist_ok=True)
            partial = archive.with_suffix(".download")
            try:
                with urllib.request.urlopen(LOCK["url"], timeout=60) as response, partial.open("wb") as output:
                    total = 0
                    while block := response.read(1024 * 1024):
                        total += len(block)
                        if total > LOCK["bytes"]:
                            raise ValueError("Cua download exceeds the pinned artifact size")
                        output.write(block)
                if total != LOCK["bytes"] or file_hash(partial) != LOCK["sha256"]:
                    raise ValueError("Cua download does not match the pinned release")
                partial.replace(archive)
            finally:
                partial.unlink(missing_ok=True)
    archive = archive.resolve(strict=True)
    if archive.stat().st_size != LOCK["bytes"] or file_hash(archive) != LOCK["sha256"]:
        raise ValueError("Cua archive size/SHA-256 does not match the pinned official release")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_name(target.name + ".installing")
    if stage.exists():
        raise ValueError(f"An incomplete install already exists; inspect {stage}")
    stage.mkdir()
    try:
        with zipfile.ZipFile(archive) as source:
            entries = source.infolist()
            if len(entries) != len(LOCK["files"]) or {i.filename for i in entries} != set(LOCK["files"]):
                raise ValueError("Cua archive file inventory differs from the pinned release")
            for item in entries:
                if item.file_size != LOCK["files"][item.filename]["bytes"]:
                    raise ValueError("Cua archive member size differs from the pinned release")
                with source.open(item) as input_file, (stage / item.filename).open("wb") as output:
                    shutil.copyfileobj(input_file, output, length=1024 * 1024)
        verify(stage)
        stage.rename(target)
    finally:
        # Only this call's own staging directory, anchored below the runtime root.
        if stage.exists() and stage.resolve().parent == (root / "cua").resolve() and not stage.is_symlink():
            shutil.rmtree(stage)
    return verify(target)


def connection(driver: Path, enabled: bool = False, grant_existing_profile: bool = False) -> dict:
    driver = driver.resolve(strict=True)
    if verify(driver.parent) != driver:
        raise ValueError("Choose the official cua-driver.exe entry point")
    template = json.loads((PACKAGE / "template.json").read_text(encoding="utf-8"))
    variant = "windows-existing-profile" if grant_existing_profile else "windows"
    config = next(item["config"] for item in template["variants"] if item["id"] == variant)
    config.update(id="cua-driver", enabled=enabled)
    config["transport"]["program"] = str(driver)
    return config


def extension_package(directory: Path | None = None) -> dict:
    template = (PACKAGE / "template.json").read_text(encoding="utf-8")
    package = {
        "format": "mdo.extension.v1",
        "manifest": {"slug": "mdo-computer-use", "name": "Computer Use（Cua Driver）",
                     "version": "0.1.2", "description": "通过官方 Cua Driver 操作当前设备的桌面。",
                     "readme": "先解压官方 Cua Driver 0.38.0，再安装本模板并填写 cua-driver.exe 路径。启用后使用现有 Agent 和支持图片及工具调用的模型。模板不含驱动、账号凭据、Skill 或额外提示词。Windows 优先；控制的是运行 mdo 的设备。Cua 已知窗口映射和取消问题保留原样。",
                     "license": "MIT", "platforms": ["windows-x86_64"]},
        "resources": [{"kind": "mcp", "id": "cua-driver", "content": template}],
    }
    if directory is None:
        return package  # Legacy template-only callers remain compatible.
    directory = directory.resolve(strict=True)
    verify(directory)
    recipe = json.loads(template)
    recipe.update(format="mdo.mcp-template.v2", inputs=[])
    for variant in recipe["variants"]:
        variant["config"]["transport"].update(program="./cua-driver.exe", working_directory=".")
    files = []
    for name, expected in LOCK["files"].items():
        data = (directory / name).read_bytes()
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError("Official Cua files changed while packaging")
        files.append(dict(path=name, encoding="zlib", size=len(data), sha256=expected["sha256"],
                          mode=0o755 if name.endswith(".exe") else 0o644,
                          base64=base64.b64encode(zlib.compress(data)).decode("ascii")))
    package["format"] = "mdo.extension.v2"
    package["manifest"].update(version="0.2.0", min_build_id=70000057,
        readme="随包附带官方 Cua Driver 0.38.0 全部六个文件。安装后检查配置并启用；无需手动解压或选择程序路径。现有浏览器访问须另行明确授权。")
    package["resources"][0].update(content=json.dumps(recipe, ensure_ascii=False), files=files)
    return package
