from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_readiness", ROOT / "packaging/check_release_readiness.py"
)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)

VERSION = "1.12.0"
TAG = "v" + VERSION
NOTES = f"docs/releases/{TAG}.md"
CONTENT = f"# FireLens {TAG}\n\n## 新增功能\n\n支援清冊表格與安全操作。\n"


def git(root, *args, input=None):
    return subprocess.check_output(["git", *args], cwd=root, input=input, stderr=subprocess.PIPE)


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "-qm", "Synthetic release")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "合成 發版專案"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Release Test")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "core.hooksPath", str(tmp_path / "empty-hooks"))
    git(root, "config", "core.autocrlf", "false")
    (root / "desktop").mkdir()
    (root / "desktop/version.py").write_text(f'__version__ = "{VERSION}"\n')
    notes = root / NOTES
    notes.parent.mkdir(parents=True)
    notes.write_text(CONTENT, encoding="utf-8")
    commit(root)
    git(root, "tag", TAG)
    return root


def test_committed_notes_and_tag_are_valid(repo):
    assert readiness.validate_release(repo, tag=TAG) == Path(NOTES)
    assert readiness.validate_release(repo) == Path(NOTES)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " \n",
        f"# FireLens {TAG}\n",
        "# FireLens v0.1.0\n\n版本不符。",
        f"# FireLens {TAG}\n\nFull Changelog: https://example.invalid/compare",
        f"# FireLens {TAG}\n\n## 新增功能\n",
    ],
)
def test_invalid_notes_fail_closed(repo, text):
    (repo / NOTES).write_text(text, encoding="utf-8")
    if text != CONTENT:
        commit(repo)
    with pytest.raises(readiness.ReleaseCheckError):
        readiness.validate_release(repo)


def test_missing_or_uncommitted_notes_are_rejected(repo):
    (repo / NOTES).unlink()
    with pytest.raises(readiness.ReleaseCheckError):
        readiness.validate_release(repo)
    (repo / NOTES).write_text(CONTENT + "新增未提交變更。", encoding="utf-8")
    with pytest.raises(readiness.ReleaseCheckError, match="提交"):
        readiness.validate_release(repo)
    git(repo, "rm", "--cached", NOTES)
    git(repo, "commit", "-qm", "Untrack synthetic notes")
    with pytest.raises(readiness.ReleaseCheckError, match="提交"):
        readiness.validate_release(repo)


@pytest.mark.parametrize("tag", ["v1.12.1", "v1.12.0-beta", "../v1.12.0", "-v1.12.0"])
def test_wrong_or_unsafe_tag_is_rejected(repo, tag):
    with pytest.raises(readiness.ReleaseCheckError):
        readiness.validate_release(repo, tag=tag)


def test_missing_tag_and_tag_pointing_to_another_commit_are_rejected(repo):
    git(repo, "tag", "-d", TAG)
    with pytest.raises(readiness.ReleaseCheckError):
        readiness.validate_release(repo, tag=TAG)
    git(repo, "tag", TAG)
    (repo / "later.txt").write_text("later")
    commit(repo)
    with pytest.raises(readiness.ReleaseCheckError, match="HEAD"):
        readiness.validate_release(repo, tag=TAG)


def test_git_symlink_notes_are_rejected_even_if_worktree_looks_like_text(repo):
    blob = git(repo, "hash-object", "-w", "--stdin", input=CONTENT.encode()).decode().strip()
    git(repo, "update-index", "--cacheinfo", f"120000,{blob},{NOTES}")
    git(repo, "commit", "-qm", "Synthetic symlink mode")
    with pytest.raises(readiness.ReleaseCheckError):
        readiness.validate_release(repo)


def test_working_version_must_match_the_committed_application_version(repo):
    (repo / "desktop/version.py").write_text('__version__ = "1.12.1"\n')
    next_notes = repo / "docs/releases/v1.12.1.md"
    next_notes.write_text(CONTENT.replace(VERSION, "1.12.1"), encoding="utf-8")
    git(repo, "add", "docs/releases/v1.12.1.md")
    git(repo, "commit", "-qm", "Prepare next notes only")
    with pytest.raises(readiness.ReleaseCheckError, match="版本.*提交"):
        readiness.validate_release(repo)


def signed_assets(repo):
    assets = repo / "release assets"
    assets.mkdir()
    exe = assets / f"FireLens-{VERSION}-windows-x64.exe"
    setup = assets / f"FireLens-{VERSION}-setup.exe"
    exe.write_bytes(b"synthetic executable")
    setup.write_bytes(b"synthetic installer")
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    payload = {
        "schema": 1,
        "version": VERSION,
        "asset": exe.name,
        "size": exe.stat().st_size,
        "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
    }

    def sign(value):
        raw = json.dumps(value).encode()
        (assets / "update-manifest.json").write_bytes(raw)
        (assets / "update-manifest.sig").write_bytes(base64.b64encode(key.sign(raw)))

    sign(payload)
    (assets / "SHA256SUMS.txt").write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (exe, setup))
    )
    return assets, public, payload, sign


def test_all_five_assets_have_matching_signature_version_size_and_hashes(repo):
    assets, public, _, _ = signed_assets(repo)
    assert readiness.validate_release(repo, tag=TAG, assets=assets, public_key_pem=public) == Path(
        NOTES
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing_setup",
        "missing_signature",
        "empty_signature",
        "bad_signature",
        "exe_hash",
        "setup_hash",
        "manifest_version",
        "manifest_size",
        "checksums_missing",
        "checksums_duplicate",
    ],
)
def test_bad_release_assets_block_publication(repo, fault):
    assets, public, payload, sign = signed_assets(repo)
    if fault.startswith("missing_"):
        (
            assets
            / (
                f"FireLens-{VERSION}-setup.exe"
                if fault == "missing_setup"
                else "update-manifest.sig"
            )
        ).unlink()
    elif fault in {"empty_signature", "bad_signature"}:
        (assets / "update-manifest.sig").write_bytes(
            b"" if fault == "empty_signature" else base64.b64encode(b"x" * 64)
        )
    elif fault in {"exe_hash", "setup_hash"}:
        name = f"FireLens-{VERSION}-" + ("windows-x64.exe" if fault == "exe_hash" else "setup.exe")
        (assets / name).write_bytes(b"tampered bytes")
    elif fault.startswith("manifest_"):
        payload["version" if fault == "manifest_version" else "size"] = (
            "9.9.9" if fault == "manifest_version" else 1
        )
        sign(payload)
    else:
        sums = assets / "SHA256SUMS.txt"
        lines = sums.read_text().splitlines()
        sums.write_text(
            lines[0] + "\n" if fault == "checksums_missing" else "\n".join(lines + [lines[0]])
        )
    with pytest.raises(readiness.ReleaseCheckError):
        readiness.validate_release(repo, tag=TAG, assets=assets, public_key_pem=public)


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell release wrapper")
@pytest.mark.parametrize("check_exit,gh_exit", [(0, 0), (0, 37), (19, 0)])
def test_publish_wrapper_uses_verified_notes_and_propagates_native_failure(
    repo, tmp_path, check_exit, gh_exit
):
    scripts = repo / "packaging"
    scripts.mkdir()
    (scripts / "publish_release.ps1").write_bytes(
        (ROOT / "packaging/publish_release.ps1").read_bytes()
    )
    commands = tmp_path / "commands"
    commands.mkdir()
    response = tmp_path / "response.json"
    files = [
        f"release assets/FireLens-{VERSION}-windows-x64.exe",
        f"release assets/FireLens-{VERSION}-setup.exe",
        "release assets/SHA256SUMS.txt",
        "release assets/update-manifest.json",
        "release assets/update-manifest.sig",
    ]
    response.write_text(
        json.dumps({"version": VERSION, "notes": NOTES, "assets": files}), encoding="ascii"
    )
    (commands / "uv.cmd").write_text(
        '@echo off\ntype "%CHECK_RESPONSE%"\nexit /b %CHECK_EXIT%\n', encoding="ascii"
    )
    calls = tmp_path / "gh-calls.txt"
    (commands / "gh.cmd").write_text(
        '@echo off\n:next\nif "%~1"=="" goto done\n'
        '>>"%GH_CALLS%" echo(%~1\nshift\ngoto next\n:done\nexit /b %GH_EXIT%\n',
        encoding="ascii",
    )
    env = dict(
        os.environ,
        PATH=str(commands) + os.pathsep + os.environ["PATH"],
        CHECK_RESPONSE=str(response),
        CHECK_EXIT=str(check_exit),
        GH_CALLS=str(calls),
        GH_EXIT=str(gh_exit),
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(scripts / "publish_release.ps1"),
            "-Tag",
            TAG,
        ],
        env=env,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == (check_exit or gh_exit), result.stdout + result.stderr
    if check_exit:
        assert not calls.exists()
    else:
        assert calls.read_text().splitlines() == [
            "release",
            "create",
            TAG,
            *files,
            "--title",
            "FireLens " + TAG,
            "--notes-file",
            NOTES,
            "--verify-tag",
        ]


def test_workflow_checks_notes_before_build_and_signed_assets_before_upload():
    workflow = (ROOT / ".github/workflows/release-windows.yml").read_text(encoding="utf-8")
    assert "--generate-notes" not in workflow
    assert "ref: ${{ inputs.tag || github.ref }}" in workflow
    assert workflow.index("check_release_readiness.py") < workflow.index("name: Build and test")
    assert (
        workflow.index("name: Sign update manifest")
        < workflow.index("name: Validate signed release assets")
        < workflow.index("name: Upload build artifact")
    )
    assert "publish_release.ps1" in workflow
    assert "REQUESTED_TAG: ${{ inputs.tag }}" in workflow
