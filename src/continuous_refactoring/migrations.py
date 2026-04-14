from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from continuous_refactoring.artifacts import ContinuousRefactorError

__all__ = [
    "MigrationManifest",
    "PhaseSpec",
    "approaches_dir",
    "intentional_skips_dir",
    "load_manifest",
    "migration_root",
    "phase_path",
    "save_manifest",
]

MigrationStatus = Literal["planning", "ready", "in-progress", "skipped", "done"]
_VALID_STATUSES: frozenset[str] = frozenset(
    {"planning", "ready", "in-progress", "skipped", "done"}
)


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    file: str
    done: bool
    ready_when: str


@dataclass(frozen=True)
class MigrationManifest:
    name: str
    created_at: str
    last_touch: str
    wake_up_on: str | None
    awaiting_human_review: bool
    status: MigrationStatus
    current_phase: int
    phases: tuple[PhaseSpec, ...]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def migration_root(live_dir: Path, name: str) -> Path:
    return live_dir / name


def phase_path(live_dir: Path, name: str, phase: PhaseSpec) -> Path:
    return migration_root(live_dir, name) / phase.file


def approaches_dir(live_dir: Path, name: str) -> Path:
    return migration_root(live_dir, name) / "approaches"


def intentional_skips_dir(live_dir: Path) -> Path:
    return live_dir / "__intentional_skips__"


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> MigrationManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    status = raw["status"]
    if status not in _VALID_STATUSES:
        raise ContinuousRefactorError(f"Unknown migration status: {status!r}")
    phases = tuple(
        PhaseSpec(
            name=p["name"],
            file=p["file"],
            done=p["done"],
            ready_when=p["ready_when"],
        )
        for p in raw.get("phases", ())
    )
    return MigrationManifest(
        name=raw["name"],
        created_at=raw["created_at"],
        last_touch=raw["last_touch"],
        wake_up_on=raw.get("wake_up_on"),
        awaiting_human_review=raw.get("awaiting_human_review", False),
        status=status,
        current_phase=raw["current_phase"],
        phases=phases,
    )


def save_manifest(manifest: MigrationManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(manifest)
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, str(path))
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
