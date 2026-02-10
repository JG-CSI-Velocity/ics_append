"""Organize incoming files into client folders by 4-digit prefix."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

CLIENT_PREFIX = re.compile(r"^(\d{4})")
SKIP_DIRS = {"log", "trends", "incoming", "processed", "__pycache__"}


def classify_files(filenames: list[str]) -> dict[str, list[str]]:
    """Classify filenames by client ID prefix.

    Returns dict mapping client_id -> [filenames] plus special key
    "incoming" for files without a 4-digit prefix.
    """
    result: dict[str, list[str]] = {}
    for name in filenames:
        match = CLIENT_PREFIX.match(name)
        if match:
            client_id = match.group(1)
            result.setdefault(client_id, []).append(name)
        else:
            result.setdefault("incoming", []).append(name)
    return result


def organize_directory(
    base_dir: Path,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Organize loose files in base_dir into client folders.

    Files with 4-digit prefix -> client folders.
    Other files -> incoming/ folder.
    Uses copy-verify-delete for safety.

    Returns dict of client_id -> [moved filenames].
    """
    moved: dict[str, list[str]] = {}

    files = [f.name for f in base_dir.iterdir() if f.is_file() and f.name not in SKIP_DIRS]

    classified = classify_files(files)

    for target, filenames in classified.items():
        target_dir = base_dir / target
        for filename in filenames:
            src = base_dir / filename
            dst = target_dir / filename

            if dry_run:
                logger.info("DRY-RUN: Would move %s to %s/", filename, target)
                moved.setdefault(target, []).append(filename)
                continue

            target_dir.mkdir(exist_ok=True)
            try:
                # Copy-verify-delete pattern
                shutil.copy2(str(src), str(dst))
                if dst.stat().st_size == src.stat().st_size:
                    src.unlink()
                    logger.info("Moved %s to %s/", filename, target)
                    moved.setdefault(target, []).append(filename)
                else:
                    dst.unlink()
                    logger.error("Size mismatch after copy: %s", filename)
            except Exception as e:
                logger.error("Failed to move %s: %s", filename, e)

    return moved


def list_client_dirs(base_dir: Path) -> list[str]:
    """List 4-digit client directory names in base_dir."""
    return sorted(
        d.name
        for d in base_dir.iterdir()
        if d.is_dir() and CLIENT_PREFIX.match(d.name) and d.name not in SKIP_DIRS
    )
