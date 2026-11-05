#!/usr/bin/env python3
"""Install this complete course PPT skill without merging with an older copy.

The bundled template is required. Installing or using this skill does not need
the original course decks, a Git checkout, or third-party Python packages.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
import zipfile


REQUIRED_FILES = (
    "SKILL.md",
    "assets/template.pptx",
    "references/profile.json",
    "scripts/pptx_engine.py",
    "scripts/run_dsh.py",
    "scripts/render_review.py",
    "scripts/install_skill.py",
)
IGNORED_NAMES = {
    ".git", "__pycache__", ".ds_store", ".work",
    "output", "outputs", "download", "downloads", "下载", "输出",
}


def validate_skill(source: Path) -> None:
    """Check that the installed copy includes all runtime inputs."""
    missing = [name for name in REQUIRED_FILES
               if not (source / name).is_file() or (source / name).stat().st_size == 0]
    if missing:
        raise ValueError(f"Incomplete skill at {source}; missing/empty: {', '.join(missing)}")
    profile = json.loads((source / "references/profile.json").read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or not isinstance(profile.get("layouts"), dict):
        raise ValueError(f"Invalid layout profile: {source / 'references/profile.json'}")
    template = source / "assets/template.pptx"
    if not zipfile.is_zipfile(template):
        raise ValueError(f"Bundled template is not a PPTX ZIP package: {template}")
    with zipfile.ZipFile(template) as package:
        if "ppt/presentation.xml" not in package.namelist():
            raise ValueError(f"Bundled template has no presentation: {template}")


def ignore_download_outputs(directory: str, names: list[str]) -> set[str]:
    """Copy the skill resources, omitting local caches and generated outputs."""
    return {name for name in names
            if name.casefold() in IGNORED_NAMES or name.lower().endswith((".pyc", ".pyo"))}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path,
                        default=Path.home() / ".dsh/skills/course-ppt-template",
                        help="Installation directory (default: ~/.dsh/skills/course-ppt-template)")
    parser.add_argument("--replace", action="store_true",
                        help="Back up an existing destination beside it, then install a fresh copy; never merge")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    source = Path(__file__).resolve().parent.parent
    destination = Path(os.path.abspath(args.dest.expanduser()))
    canonical_destination = destination.resolve()
    validate_skill(source)
    if canonical_destination == source:
        print(f"Already installed and validated: {destination}")
        return 0
    if canonical_destination.is_relative_to(source):
        raise ValueError("Destination must not be inside the source skill directory")
    if source.is_relative_to(canonical_destination):
        raise ValueError("Destination must not contain the source skill directory")
    present = destination.exists() or destination.is_symlink()
    if present and not args.replace:
        raise ValueError(f"Destination already exists: {destination}; use --replace to preserve a backup first")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.install-", dir=destination.parent))
    backup: Path | None = None
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True, ignore=ignore_download_outputs)
        validate_skill(stage)
        if present:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = destination.with_name(f"{destination.name}.backup-{stamp}-{uuid.uuid4().hex[:8]}")
            destination.rename(backup)
        try:
            stage.rename(destination)
        except OSError:
            if backup is not None and not destination.exists() and not destination.is_symlink():
                backup.rename(destination)
                backup = None
            raise
    except Exception:
        # Preserve both the source and any old installation. A failed staged
        # copy is retained for inspection rather than deleting user files.
        print(f"Installation did not finish; staged copy, if present: {stage}", file=sys.stderr)
        if backup is not None:
            print(f"Previous installation preserved at: {backup}", file=sys.stderr)
        raise
    print(f"Installed and validated: {destination}")
    if backup is not None:
        print(f"Previous installation preserved at: {backup}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print(f"install_skill: {error}", file=sys.stderr)
        raise SystemExit(1)
