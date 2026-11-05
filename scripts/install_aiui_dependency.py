#!/usr/bin/env python3
"""Install the optional aiui-dev dependency from local skills or pinned upstream.

No upstream skill content is bundled with the course skill. Existing valid
installations are reused. Replacing one requires --replace and keeps a backup
outside the skills search root. Local SKILL.md overlays are copied unchanged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid


UPSTREAM_URL = "https://github.com/jsar-project/AIUI.git"
UPSTREAM_COMMIT = "07db37b3f3ea44cc4efe669cd3456b0221195189"
UPSTREAM_SUBDIRECTORY = "skills/aiui-dev"
REQUIRED_FILES = (
    "SKILL.md", "references/framework.md", "references/events.md",
    "references/components.md", "references/wxss.md",
    "references/apis/index.md", "references/design/monochrome-green.md",
)
IGNORED_NAMES = {".git", "__pycache__", ".ds_store", "upstream.json", "provenance.json"}


def ignored(directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name.casefold() in IGNORED_NAMES
            or name.lower().endswith((".pyc", ".pyo"))}


def validate_skill(source: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"aiui-dev directory is missing: {source}")
    missing = [name for name in REQUIRED_FILES if not (source / name).is_file()
               or (source / name).stat().st_size == 0]
    if missing:
        raise ValueError(f"aiui-dev is incomplete; missing/empty: {', '.join(missing)}")
    text = (source / "SKILL.md").read_text(encoding="utf-8-sig")
    frontmatter = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.S)
    if not frontmatter or not re.search(
        r"(?m)^name:[ \t]*(?:aiui-dev|'aiui-dev'|\"aiui-dev\")[ \t]*(?:#.*)?$",
        frontmatter.group(1),
    ):
        raise ValueError("SKILL.md frontmatter must declare name: aiui-dev")
    # Plain directories avoid symlink cycles and accidental copying of files
    # outside the selected dependency. The source itself may be an alias.
    for directory, dirs, files in os.walk(source, followlinks=False):
        excluded = ignored(directory, dirs + files)
        dirs[:] = [name for name in dirs if name not in excluded]
        for name in dirs + [n for n in files if n not in excluded]:
            if (Path(directory) / name).is_symlink():
                raise ValueError("aiui-dev contains a symlink; use a plain dependency directory")


def check_no_recursion(source: Path, destination: Path) -> None:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Source and destination must be separate, non-nested directories")


def workspace_paths(destination: Path, source: Path | None = None) -> tuple[Path, Path]:
    workspace = destination.parent.parent
    backup_root = workspace / "skill-backups"
    staging_root = workspace / "skill-install-staging"
    for directory in (backup_root, staging_root):
        resolved = directory.resolve()
        if resolved.is_relative_to(destination.parent.resolve()):
            raise ValueError("Dependency backup/staging must stay outside the skills search root")
        if source is not None and (resolved == source.resolve() or resolved.is_relative_to(source.resolve())):
            raise ValueError("Dependency backup/staging must stay outside the source directory")
    return backup_root, staging_root


def local_source(explicit: Path | None) -> tuple[Path, str] | None:
    if explicit is not None:
        source = explicit.expanduser().resolve()
        validate_skill(source)
        return source, "explicit-local-directory"
    candidates = (
        (Path.home() / ".codex/skills/aiui-dev", "~/.codex/skills/aiui-dev"),
        (Path.home() / ".agents/skills/aiui-dev", "~/.agents/skills/aiui-dev"),
    )
    invalid = []
    for source, label in candidates:
        if not source.exists():
            continue
        try:
            validate_skill(source)
        except (ValueError, OSError):
            invalid.append(label)
            continue
        return source.resolve(), label
    if invalid:
        print("No valid local aiui-dev in: " + ", ".join(invalid), file=sys.stderr)
    return None


def git(command: list[str], repository: Path) -> str:
    env = os.environ.copy()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
    result = subprocess.run(
        ["git", "-c", "http.version=HTTP/1.1", "-c", "core.hooksPath=/dev/null",
         "-C", str(repository), *command], env=env, capture_output=True, text=True, timeout=240,
    )
    if result.returncode:
        # Git diagnostics can include credential helpers or private proxy URLs.
        # Capture them, but never echo those strings from this installer.
        raise ValueError(f"Pinned aiui-dev download failed during {command[0]} "
                         f"(git exit {result.returncode}); check Git/network access and retry")
    return result.stdout.strip()


def download_source(staging_root: Path) -> Path:
    if not shutil.which("git"):
        raise ValueError("--download requires Git; install Git or supply --source")
    checkout = Path(tempfile.mkdtemp(prefix="aiui-upstream-", dir=staging_root))
    git(["init", "--quiet"], checkout)
    git(["remote", "add", "origin", UPSTREAM_URL], checkout)
    git(["fetch", "--depth=1", "--filter=blob:none", "origin", UPSTREAM_COMMIT], checkout)
    if git(["rev-parse", "FETCH_HEAD"], checkout) != UPSTREAM_COMMIT:
        raise ValueError("Downloaded AIUI revision does not match the pinned commit")
    git(["sparse-checkout", "init", "--no-cone"], checkout)
    git(["sparse-checkout", "set", "--no-cone", "/" + UPSTREAM_SUBDIRECTORY + "/"], checkout)
    git(["checkout", "--detach", "FETCH_HEAD"], checkout)
    source = checkout / UPSTREAM_SUBDIRECTORY
    validate_skill(source)
    return source


def tree_hash(source: Path) -> str:
    digest = hashlib.sha256()
    paths = []
    for directory, dirs, files in os.walk(source):
        excluded = ignored(directory, dirs + files)
        dirs[:] = [name for name in dirs if name not in excluded]
        paths.extend(Path(directory) / name for name in files if name not in excluded)
    for path in sorted(paths, key=lambda p: p.relative_to(source).as_posix()):
        digest.update(path.relative_to(source).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def provenance(source: Path, label: str, downloaded: bool) -> dict:
    declared_commit = None
    metadata = source / "UPSTREAM.json"
    if metadata.is_file():
        try:
            candidate = json.loads(metadata.read_text(encoding="utf-8")).get("commit")
            if isinstance(candidate, str) and re.fullmatch(r"[0-9a-fA-F]{40}", candidate):
                declared_commit = candidate.lower()
        except (ValueError, OSError, AttributeError):
            pass
    # Only approved provenance fields are written. Private backup paths and
    # other local UPSTREAM.json data are neither copied nor reproduced.
    return {
        "version": 1, "dependency": "aiui-dev",
        "installed_from": "pinned-upstream-download" if downloaded else "local-skill-copy",
        "source_locator": label,
        "upstream_repository": UPSTREAM_URL.removesuffix(".git"),
        "upstream_subdirectory": UPSTREAM_SUBDIRECTORY,
        "upstream_commit": UPSTREAM_COMMIT if downloaded else declared_commit,
        "content_sha256": tree_hash(source),
        "local_skill_overlay_preserved": not downloaded,
        "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "distribution_note": "Upstream content is acquired only at installation time and is not bundled with the course skill; no upstream LICENSE declaration is assumed.",
    }


def install(source: Path, destination: Path, label: str, downloaded: bool, replace: bool) -> dict:
    validate_skill(source)
    check_no_recursion(source, destination)
    present = destination.exists() or destination.is_symlink()
    if present and not replace:
        validate_skill(destination)
        return {"status": "ready", "action": "reused", "destination": str(destination)}
    backup_root, staging_root = workspace_paths(destination, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="aiui-dev.install-", dir=staging_root))
    backup = None
    installed_new = False
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True, ignore=ignored)
        validate_skill(stage)
        record = provenance(source, label, downloaded)
        if tree_hash(stage) != record["content_sha256"]:
            raise ValueError("Dependency copy differs from source; installation stopped")
        (stage / "PROVENANCE.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if present:
            backup_root.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = backup_root / f"aiui-dev.backup-{stamp}-{uuid.uuid4().hex[:8]}"
            destination.rename(backup)
        stage.rename(destination)
        installed_new = True
        validate_skill(destination)
    except Exception:
        if installed_new and destination.exists() and not stage.exists():
            destination.rename(stage)
        if backup is not None and not destination.exists() and not destination.is_symlink():
            backup.rename(destination)
            backup = None
        print(f"AIUI installation failed; staged copy retained at: {stage}", file=sys.stderr)
        if backup is not None:
            print(f"Previous AIUI installation preserved at: {backup}", file=sys.stderr)
        raise
    result = {"status": "ready", "action": "installed", "destination": str(destination)}
    if backup is not None:
        result["backup"] = str(backup)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path.home() / ".dsh/skills/aiui-dev")
    parser.add_argument("--source", type=Path, help="Explicit local aiui-dev directory")
    parser.add_argument("--download", action="store_true", help="Allow pinned upstream download if no local skill is available")
    parser.add_argument("--replace", action="store_true", help="Back up and replace an existing dependency; default: reuse a valid copy")
    args = parser.parse_args()
    destination = Path(os.path.abspath(args.dest.expanduser()))
    present = destination.exists() or destination.is_symlink()
    if present and not args.replace:
        if args.source is not None:
            check_no_recursion(args.source.expanduser(), destination)
        try:
            validate_skill(destination)
        except (ValueError, OSError) as error:
            raise ValueError(f"Existing AIUI dependency is invalid ({error}); use --replace to back it up first") from error
        print("AIUI ready: " + json.dumps({"action": "reused", "destination": str(destination)}, ensure_ascii=False))
        return 0
    local = local_source(args.source)
    downloaded = False
    if local:
        source, label = local
    elif args.download:
        _, staging_root = workspace_paths(destination)
        staging_root.mkdir(parents=True, exist_ok=True)
        source = download_source(staging_root)
        label = UPSTREAM_URL.removesuffix(".git") + "/tree/" + UPSTREAM_COMMIT + "/" + UPSTREAM_SUBDIRECTORY
        downloaded = True
    else:
        raise ValueError("No valid local aiui-dev found in ~/.codex/skills or ~/.agents/skills; supply --source or use --download")
    result = install(source, destination, label, downloaded, args.replace)
    print("AIUI ready: " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        message = "Git operation timed out; retry or supply a local --source" if isinstance(error, subprocess.TimeoutExpired) else str(error)
        print(f"AIUI failed: {message}", file=sys.stderr)
        raise SystemExit(1)
