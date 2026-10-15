from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)")
HISTORICAL_MARKERS = ("Release", "當時", "歷史", "起內建", "起支援", "舊版", "首次")
FUTURE_MARKERS = ("預計", "規劃版本", "下一版")


def _configure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _version_tuple(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _desktop_version() -> str:
    match = re.search(r'__version__\s*=\s*"([^"]+)"', _text("desktop/version.py"))
    if not match:
        raise ValueError("desktop/version.py 找不到 __version__")
    return match.group(1)


def _pyproject_version() -> str:
    data = tomllib.loads(_text("pyproject.toml"))
    return str(data["project"]["version"])


def _lock_version() -> str:
    data = tomllib.loads(_text("uv.lock"))
    matches = [
        package
        for package in data.get("package", [])
        if package.get("name") == "firelens" and package.get("source", {}).get("virtual") == "."
    ]
    if len(matches) != 1:
        raise ValueError("uv.lock 找不到唯一的 firelens virtual package")
    return str(matches[0]["version"])


def _frontend_fallback_version() -> str:
    match = re.search(
        r"appInfo\?\.version\s*\?\?\s*['\"](\d+\.\d+\.\d+)['\"]",
        _text("frontend/src/App.tsx"),
    )
    if not match:
        raise ValueError("frontend/src/App.tsx 找不到 appInfo.version fallback 版本")
    return match.group(1)


def _tasks_current_version() -> str:
    match = re.search(r"目前版本\s+v(\d+\.\d+\.\d+)", _text("TASKS.md"))
    if not match:
        raise ValueError("TASKS.md 找不到「目前版本 vX.Y.Z」")
    return match.group(1)


def _readme_release_versions() -> tuple[str, str]:
    text = _text("README.md")
    tag = re.search(r"git tag v(\d+\.\d+\.\d+)", text)
    push = re.search(r"git push origin v(\d+\.\d+\.\d+)", text)
    if not tag or not push:
        raise ValueError("README.md 找不到正式版本 git tag / git push 範例")
    return tag.group(1), push.group(1)


def _documentation_errors(path: str, current: str) -> list[str]:
    errors: list[str] = []
    current_tuple = _version_tuple(current)
    for line_number, line in enumerate(_text(path).splitlines(), start=1):
        for match in SEMVER_RE.finditer(line):
            version = match.group(1)
            version_tuple = _version_tuple(version)
            if any(marker in line for marker in FUTURE_MARKERS):
                if version_tuple <= current_tuple:
                    errors.append(
                        f"{path}:{line_number} 的預計版本 v{version} 已不高於目前版本 v{current}，"
                        "請更新或移除預計版本文字"
                    )
                continue
            if version == current:
                continue
            if any(marker in line for marker in HISTORICAL_MARKERS):
                continue
            errors.append(
                f"{path}:{line_number} 出現未標示為歷史用途的舊版本 v{version}；"
                "若是歷史事實請明確標示 Release／當時／歷史／起，否則請同步更新"
            )
    return errors


def validate(tag: str | None = None) -> list[str]:
    errors: list[str] = []
    try:
        current = _desktop_version()
    except (OSError, ValueError) as exc:
        return [str(exc)]

    if not SEMVER_RE.fullmatch(current):
        errors.append(f"desktop/version.py 不是穩定 SemVer：{current}")

    checks = {
        "pyproject.toml": _pyproject_version,
        "uv.lock": _lock_version,
        "frontend/src/App.tsx fallback": _frontend_fallback_version,
        "TASKS.md 目前版本": _tasks_current_version,
    }
    for label, reader in checks.items():
        try:
            value = reader()
        except (KeyError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{label} 無法驗證：{exc}")
            continue
        if value != current:
            errors.append(f"版本不一致：desktop/version.py={current}，{label}={value}")

    try:
        readme_tag, readme_push = _readme_release_versions()
        if readme_tag != current:
            errors.append(f"README git tag 範例仍是 v{readme_tag}，目前版本是 v{current}")
        if readme_push != current:
            errors.append(f"README git push 範例仍是 v{readme_push}，目前版本是 v{current}")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))

    for document in ("TASKS.md", "README.md"):
        try:
            errors.extend(_documentation_errors(document, current))
        except OSError as exc:
            errors.append(f"無法讀取 {document}：{exc}")

    if tag is not None and tag != f"v{current}":
        errors.append(f"Tag 不一致：收到 {tag}，目前版本應為 v{current}")

    return errors


def main() -> int:
    _configure_utf8_console()
    parser = argparse.ArgumentParser(description="檢查 FireLens 所有受管版本來源是否一致")
    parser.add_argument("--tag", help="Release Tag，例如 v1.3.0")
    args = parser.parse_args()

    errors = validate(args.tag)
    if errors:
        print("FireLens 版本一致性檢查失敗：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"FireLens 版本一致性檢查通過：v{_desktop_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
