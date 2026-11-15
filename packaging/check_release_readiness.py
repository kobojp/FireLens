"""Check committed release notes and signed assets before publishing."""

from __future__ import annotations

import argparse
import json
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desktop.update import PUBLIC_KEY_PEM, UpdateError, verify_manifest  # noqa: E402
from desktop.update_protocol import sha256_file  # noqa: E402


class ReleaseCheckError(ValueError):
    pass


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    if result.returncode:
        raise ReleaseCheckError(f"Git 檢查失敗：{' '.join(args)}")
    return result.stdout


def _safe_file(root: Path, relative: Path) -> Path:
    path = relative if relative.is_absolute() else root / relative
    try:
        parts = path.relative_to(root).parts
        current = root
        for part in parts:
            if part in {".", ".."}:
                raise ReleaseCheckError("Release 路徑不安全")
            current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ReleaseCheckError("Release 檔案不可使用連結或 reparse point")
        if not parts or not stat.S_ISREG(current.stat().st_mode):
            raise ReleaseCheckError(f"找不到一般檔案：{relative}")
        return current
    except (OSError, ValueError) as exc:
        if isinstance(exc, ReleaseCheckError):
            raise
        raise ReleaseCheckError(f"找不到安全 Release 檔案：{relative}") from exc


def _version(source: str) -> str:
    match = re.search(r'^__version__\s*=\s*"(\d+\.\d+\.\d+)"\s*$', source, re.M)
    if match is None:
        raise ReleaseCheckError("desktop/version.py 缺少穩定版號")
    return match[1]


def _validate_assets(root: Path, version: str, assets: Path, public_key_pem: bytes) -> None:
    exe_name = f"FireLens-{version}-windows-x64.exe"
    setup_name = f"FireLens-{version}-setup.exe"
    names = [exe_name, setup_name, "SHA256SUMS.txt", "update-manifest.json", "update-manifest.sig"]
    paths = {name: _safe_file(root, assets / name) for name in names}
    if any(path.stat().st_size == 0 for path in paths.values()):
        raise ReleaseCheckError("Release 資產不可為空檔案")
    try:
        manifest = verify_manifest(
            paths["update-manifest.json"].read_bytes(),
            paths["update-manifest.sig"].read_bytes(),
            public_key_pem,
        )
    except (UpdateError, ValueError) as exc:
        raise ReleaseCheckError("Release manifest 簽章／格式驗證失敗") from exc
    if manifest.version != version or manifest.asset != exe_name:
        raise ReleaseCheckError("Release manifest 的版本／檔名不符")
    exe = paths[exe_name]
    if manifest.size != exe.stat().st_size or manifest.sha256 != sha256_file(exe):
        raise ReleaseCheckError("Release EXE 大小／SHA256 與簽章 manifest 不符")
    try:
        lines = paths["SHA256SUMS.txt"].read_text(encoding="ascii").splitlines()
    except UnicodeError as exc:
        raise ReleaseCheckError("SHA256SUMS 必須是 ASCII") from exc
    sums: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        if not match or match[2] in sums:
            raise ReleaseCheckError("SHA256SUMS 格式不合法或檔名重複")
        sums[match[2]] = match[1].lower()
    if set(sums) != {exe_name, setup_name}:
        raise ReleaseCheckError("SHA256SUMS 必須列出此版本兩個安裝資產")
    if any(sums[name] != sha256_file(paths[name]) for name in sums):
        raise ReleaseCheckError("Release 安裝資產 SHA256 不符")


def validate_release(
    root: Path,
    *,
    tag: str | None = None,
    assets: Path | None = None,
    public_key_pem: bytes = PUBLIC_KEY_PEM,
) -> Path:
    root = root.resolve()
    version = _version(_safe_file(root, Path("desktop/version.py")).read_text(encoding="utf-8"))
    if tag is not None and (not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or tag != f"v{version}"):
        raise ReleaseCheckError("Tag 必須與目前穩定版號一致")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    if tag is not None:
        tagged = _git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}").decode().strip()
        if tagged != head:
            raise ReleaseCheckError("Tag 不指向目前 HEAD，拒絕使用另一份來源發布")
    relative = Path(f"docs/releases/v{version}.md")
    try:
        text = _safe_file(root, relative).read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise ReleaseCheckError("Release Notes 必須為 UTF-8") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != f"# FireLens v{version}":
        raise ReleaseCheckError("Release Notes 標題與版本不符")
    body = "\n".join(line for line in lines[1:] if not line.lstrip().startswith("#"))
    if not re.search(r"[\u4e00-\u9fff]", body):
        raise ReleaseCheckError("Release Notes 不能空白、只有標題或 Full Changelog；需繁中更新內容")
    git_path = relative.as_posix()
    tree = _git(root, "ls-tree", head, "--", git_path).decode()
    if not tree.startswith("100644 blob ") and not tree.startswith("100755 blob "):
        raise ReleaseCheckError("Release Notes 尚未提交為一般檔案")
    committed = _git(root, "show", f"{head}:{git_path}").decode("utf-8-sig")
    if committed.replace("\r\n", "\n") != text.replace("\r\n", "\n"):
        raise ReleaseCheckError("Release Notes 有未提交變更")
    if _version(_git(root, "show", f"{head}:desktop/version.py").decode()) != version:
        raise ReleaseCheckError("應用程式版本有未提交變更")
    if assets is not None:
        _validate_assets(root, version, assets, public_key_pem)
    return relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tag")
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        notes = validate_release(args.root, tag=args.tag, assets=args.assets_dir)
        version = notes.stem.removeprefix("v")
        files = (
            []
            if args.assets_dir is None
            else [
                (args.assets_dir / name).as_posix()
                for name in [
                    f"FireLens-{version}-windows-x64.exe",
                    f"FireLens-{version}-setup.exe",
                    "SHA256SUMS.txt",
                    "update-manifest.json",
                    "update-manifest.sig",
                ]
            ]
        )
        if args.json:
            print(json.dumps({"version": version, "notes": notes.as_posix(), "assets": files}))
        else:
            print(f"Release preflight passed: v{version}, {notes.as_posix()}")
        return 0
    except (ReleaseCheckError, OSError, UnicodeError) as exc:
        print(f"Release preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
