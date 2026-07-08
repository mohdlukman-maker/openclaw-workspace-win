import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RetentionResult:
    scanned: int
    archived: int
    archive_dir: Path | None
    issues: list[str]


def iter_old_files(paths: list[Path], cutoff_timestamp: float) -> list[Path]:
    old_files: list[Path] = []
    for root in paths:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff_timestamp:
                    old_files.append(path)
            except OSError:
                logging.exception("Could not inspect retention candidate: %s", path)
    return old_files


def archive_old_files(
    roots: list[Path],
    archive_root: Path,
    older_than_days: int,
    dry_run: bool = False,
    now: datetime | None = None,
) -> RetentionResult:
    if older_than_days < 1:
        raise ValueError("older_than_days must be at least 1")

    current_time = now or datetime.now(timezone.utc)
    cutoff_timestamp = current_time.timestamp() - (older_than_days * 24 * 60 * 60)
    candidates = iter_old_files(roots, cutoff_timestamp)
    archive_dir = archive_root / current_time.strftime("%Y%m%d_%H%M%S")
    issues: list[str] = []
    archived = 0

    for source in candidates:
        try:
            if dry_run:
                continue
            root = next((candidate_root for candidate_root in roots if source.is_relative_to(candidate_root)), source.parent)
            relative_path = source.relative_to(root)
            target = archive_dir / root.name / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            archived += 1
        except Exception as exc:
            logging.exception("Could not archive old file: %s", source)
            issues.append(f"{source}: {exc}")

    return RetentionResult(
        scanned=len(candidates),
        archived=0 if dry_run else archived,
        archive_dir=None if dry_run else archive_dir if candidates else None,
        issues=issues,
    )
