from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
from continuous_refactoring.git import run_command
from continuous_refactoring.migration_consistency import (
    ConsistencyMode,
    MigrationConsistencyFinding,
    check_migration_consistency,
    has_blocking_consistency_findings,
)

__all__ = [
    "PlanningPublishError",
    "PlanningPublishRequest",
    "PlanningPublishResult",
    "PlanningWorkspace",
    "capture_live_snapshot",
    "prepare_planning_workspace",
    "publish_lock_path",
    "publish_planning_workspace",
    "snapshot_tree_digest",
]

PublishStatus = Literal["published", "blocked", "failed"]

_TRANSACTIONS_DIR_NAME = "__transactions__"
_LOCK_DIR_NAME = ".lock"
_LOCK_OWNER_FILE = "owner.json"
_DIGEST_VERSION = b"continuous-refactoring-tree-v1\n"
_MISSING_TREE_DIGEST_INPUT = b"missing\n"
_FS_ERRORS = (OSError, shutil.Error)


@dataclass(frozen=True)
class PlanningWorkspace:
    root: Path
    slug: str
    run_id: str


@dataclass(frozen=True)
class PlanningPublishRequest:
    repo_root: Path
    live_migrations_dir: Path
    slug: str
    workspace_dir: Path
    base_snapshot_id: str
    validation_mode: ConsistencyMode = "ready-publish"
    operation: str = "planning-publish"
    now: str | None = None


@dataclass(frozen=True)
class PlanningPublishResult:
    status: PublishStatus
    reason: str
    snapshot_id: str | None
    live_dir: Path
    transaction_dir: Path | None
    staged_dir: Path | None
    rollback_dir: Path | None
    failed_dir: Path | None
    findings: tuple[MigrationConsistencyFinding, ...] = ()
    dirty_paths: tuple[str, ...] = ()
    lock_path: Path | None = None
    cleanup_error: str | None = None


class PlanningPublishError(ContinuousRefactorError):
    def __init__(self, result: PlanningPublishResult) -> None:
        self.result = result
        super().__init__(_result_message(result))


@dataclass(frozen=True)
class _TransactionPaths:
    transaction_dir: Path
    staged_dir: Path
    rollback_dir: Path
    failed_dir: Path


@dataclass(frozen=True)
class _PublishLock:
    path: Path


def prepare_planning_workspace(
    project_state_dir: Path,
    slug: str,
    run_id: str,
) -> PlanningWorkspace:
    _require_safe_segment(slug, field="slug")
    _require_safe_segment(run_id, field="run_id")
    root = project_state_dir / "planning" / slug / run_id / "work" / slug
    if root.exists() and any(root.iterdir()):
        raise ContinuousRefactorError(f"Planning workspace is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    return PlanningWorkspace(root=root, slug=slug, run_id=run_id)


def capture_live_snapshot(
    repo_root: Path,
    live_migrations_dir: Path,
    slug: str,
) -> str:
    live_dir = _live_migration_dir(live_migrations_dir, slug)
    dirty_paths = _dirty_live_migration_paths(repo_root, live_dir)
    if dirty_paths:
        _raise_result(
                _blocked_result(
                    "dirty live migration directory; commit, discard, or inspect with migration doctor",
                    live_dir=live_dir,
                    dirty_paths=dirty_paths,
                )
        )
    return snapshot_tree_digest(live_dir)


def publish_lock_path(live_migrations_dir: Path) -> Path:
    return live_migrations_dir / _TRANSACTIONS_DIR_NAME / _LOCK_DIR_NAME


def snapshot_tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(_DIGEST_VERSION)
    if not path.exists():
        digest.update(_MISSING_TREE_DIGEST_INPUT)
        return digest.hexdigest()
    if path.is_symlink() or not path.is_dir():
        raise ContinuousRefactorError(f"Snapshot root must be a directory: {path}")

    root = path.resolve()
    for child in sorted(path.rglob("*"), key=lambda item: _relative_name(path, item)):
        if child.is_symlink():
            raise ContinuousRefactorError(f"Snapshot contains symlink: {child}")
        try:
            child_stat = child.stat()
        except OSError as error:
            raise ContinuousRefactorError(
                f"Could not stat snapshot path {child}: {error}"
            ) from error
        rel = child.resolve().relative_to(root).as_posix()
        mode = stat.S_IMODE(child_stat.st_mode)
        if child.is_dir():
            digest.update(f"D {rel} {mode:o}\0".encode("utf-8"))
            continue
        if child.is_file():
            digest.update(f"F {rel} {mode:o} {child_stat.st_size}\0".encode("utf-8"))
            try:
                digest.update(child.read_bytes())
            except OSError as error:
                raise ContinuousRefactorError(
                    f"Could not read snapshot path {child}: {error}"
                ) from error
            digest.update(b"\0")
            continue
        raise ContinuousRefactorError(f"Snapshot contains unsupported path: {child}")
    return digest.hexdigest()


def publish_planning_workspace(
    request: PlanningPublishRequest,
) -> PlanningPublishResult:
    _validate_request(request)
    live_migrations_dir = request.live_migrations_dir
    live_dir = _live_migration_dir(live_migrations_dir, request.slug)
    live_migrations_dir.mkdir(parents=True, exist_ok=True)

    lock = _acquire_publish_lock(
        live_migrations_dir,
        operation=request.operation,
        now=request.now,
        live_dir=live_dir,
    )
    try:
        result = _publish_planning_workspace_locked(request, live_dir)
    except PlanningPublishError as error:
        release_error = _release_publish_lock(lock.path)
        if release_error is not None:
            _raise_result(_with_cleanup_error(error.result, release_error))
        raise
    except Exception as error:
        release_error = _release_publish_lock(lock.path)
        if release_error is not None:
            raise ContinuousRefactorError(
                f"{error}\n{release_error}"
            ) from error
        raise

    release_error = _release_publish_lock(lock.path)
    if release_error is not None:
        return _with_cleanup_error(result, release_error)
    return result


def _publish_planning_workspace_locked(
    request: PlanningPublishRequest,
    live_dir: Path,
) -> PlanningPublishResult:
    live_migrations_dir = request.live_migrations_dir
    dirty_paths = _dirty_live_migration_paths(request.repo_root, live_dir)
    if dirty_paths:
        _raise_result(
            _blocked_result(
                "dirty live migration directory; commit, discard, or inspect with migration doctor",
                live_dir=live_dir,
                dirty_paths=dirty_paths,
            )
        )

    try:
        _validate_snapshot(request.workspace_dir, mode=request.validation_mode)
    except ContinuousRefactorError as error:
        _raise_result(
            _blocked_result(
                f"workspace validation failed: {error}",
                live_dir=live_dir,
            )
        )

    tx_paths = _prepare_transaction_paths(live_migrations_dir)
    try:
        _copy_tree(request.workspace_dir, tx_paths.staged_dir)
    except _FS_ERRORS as error:
        _raise_result(
            _failed_result(
                f"could not copy workspace to staged transaction path: {error}",
                live_dir=live_dir,
                tx_paths=tx_paths,
            )
        )

    try:
        _validate_snapshot(tx_paths.staged_dir, mode=request.validation_mode)
    except ContinuousRefactorError as error:
        _raise_result(
            _blocked_result(
                f"staged validation failed: {error}",
                live_dir=live_dir,
                tx_paths=tx_paths,
            )
        )

    if not _same_device(tx_paths.staged_dir, live_migrations_dir):
        _raise_result(
            _blocked_result(
                "staged publish source must be on the same filesystem as the live migrations dir",
                live_dir=live_dir,
                tx_paths=tx_paths,
            )
        )

    current_snapshot_id = snapshot_tree_digest(live_dir)
    if current_snapshot_id != request.base_snapshot_id:
        _raise_result(
            _blocked_result(
                "stale base snapshot: base_snapshot_id does not match current live snapshot "
                f"(base_snapshot_id={request.base_snapshot_id}, current_snapshot_id={current_snapshot_id})",
                live_dir=live_dir,
                tx_paths=tx_paths,
            )
        )

    return _publish_staged_snapshot(request, live_dir, tx_paths)


def _publish_staged_snapshot(
    request: PlanningPublishRequest,
    live_dir: Path,
    tx_paths: _TransactionPaths,
) -> PlanningPublishResult:
    rollback_exists = False
    try:
        if live_dir.exists():
            _move_path(live_dir, tx_paths.rollback_dir)
            rollback_exists = True
    except OSError as error:
        _raise_result(
            _failed_result(
                f"could not move live migration to rollback: {error}",
                live_dir=live_dir,
                tx_paths=tx_paths,
            )
        )

    try:
        _move_path(tx_paths.staged_dir, live_dir)
    except OSError as error:
        restore_error = _restore_rollback(
            live_dir,
            tx_paths,
            move_live_to_failed=live_dir.exists(),
        )
        _raise_result(
            _failed_result(
                _with_restore_context(
                    f"could not install staged migration: {error}",
                    restore_error,
                ),
                live_dir=live_dir,
                tx_paths=tx_paths,
            )
        )

    try:
        _validate_snapshot(live_dir, mode=request.validation_mode)
    except ContinuousRefactorError as error:
        restore_error = _restore_rollback(live_dir, tx_paths, move_live_to_failed=True)
        _raise_result(
            _failed_result(
                _with_restore_context(
                    f"live snapshot validation failed after publish: {error}",
                    restore_error,
                ),
                live_dir=live_dir,
                tx_paths=tx_paths,
            )
        )

    cleanup_error = _cleanup_rollback(tx_paths.rollback_dir) if rollback_exists else None
    if cleanup_error is None:
        _remove_empty_dir(tx_paths.transaction_dir)
    return PlanningPublishResult(
        status="published",
        reason="published",
        snapshot_id=snapshot_tree_digest(live_dir),
        live_dir=live_dir,
        transaction_dir=tx_paths.transaction_dir,
        staged_dir=tx_paths.staged_dir,
        rollback_dir=tx_paths.rollback_dir,
        failed_dir=tx_paths.failed_dir,
        cleanup_error=cleanup_error,
    )


def _validate_request(request: PlanningPublishRequest) -> None:
    _require_safe_segment(request.slug, field="slug")
    if request.workspace_dir.name != request.slug:
        raise ContinuousRefactorError(
            "Planning workspace snapshot directory must be named for the migration "
            f"slug {request.slug!r}: {request.workspace_dir}"
        )
    workspace = request.workspace_dir.resolve()
    live_root = request.live_migrations_dir.resolve()
    try:
        workspace.relative_to(live_root)
    except ValueError:
        pass
    else:
        raise ContinuousRefactorError(
            f"Planning workspace must be outside live migrations dir: {request.workspace_dir}"
        )
    if not request.base_snapshot_id:
        raise ContinuousRefactorError("base_snapshot_id is required")


def _require_safe_segment(value: str, *, field: str) -> None:
    if (
        not value
        or Path(value).name != value
        or value.startswith(".")
        or value.startswith("__")
    ):
        raise ContinuousRefactorError(
            f"Planning publish {field} is not a safe path segment: {value!r}"
        )


def _live_migration_dir(live_migrations_dir: Path, slug: str) -> Path:
    _require_safe_segment(slug, field="slug")
    return live_migrations_dir / slug


def _prepare_transaction_paths(live_migrations_dir: Path) -> _TransactionPaths:
    token = _new_transaction_token()
    transaction_dir = live_migrations_dir / _TRANSACTIONS_DIR_NAME / token
    staged_dir = transaction_dir / "staged"
    rollback_dir = transaction_dir / "rollback"
    failed_dir = transaction_dir / "failed"
    try:
        transaction_dir.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not create planning transaction directory {transaction_dir}: {error}"
        ) from error
    return _TransactionPaths(
        transaction_dir=transaction_dir,
        staged_dir=staged_dir,
        rollback_dir=rollback_dir,
        failed_dir=failed_dir,
    )


def _acquire_publish_lock(
    live_migrations_dir: Path,
    *,
    operation: str,
    now: str | None,
    live_dir: Path,
) -> _PublishLock:
    lock_path = publish_lock_path(live_migrations_dir)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.mkdir()
    except FileExistsError:
        _raise_result(_lock_conflict_result(lock_path, live_dir))
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not acquire planning publish lock {lock_path}: {error}"
        ) from error

    metadata = {
        "pid": os.getpid(),
        "operation": operation,
        "created_at": now or iso_timestamp(),
    }
    try:
        (lock_path / _LOCK_OWNER_FILE).write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        shutil.rmtree(lock_path, ignore_errors=True)
        raise ContinuousRefactorError(
            f"Could not write planning publish lock metadata {lock_path}: {error}"
        ) from error

    return _PublishLock(lock_path)


def _release_publish_lock(lock_path: Path) -> str | None:
    try:
        _remove_tree(lock_path)
    except _FS_ERRORS as error:
        return f"could not release planning publish lock {lock_path}: {error}"
    _remove_empty_dir(lock_path.parent)
    return None


def _lock_conflict_result(lock_path: Path, live_dir: Path) -> PlanningPublishResult:
    metadata = _read_lock_metadata(lock_path)
    detail = ", ".join(
        f"{key}={metadata[key]}"
        for key in ("pid", "operation", "created_at")
        if key in metadata
    )
    suffix = f" ({detail})" if detail else ""
    return PlanningPublishResult(
        status="blocked",
        reason=f"concurrent mutation lock is active at {lock_path}{suffix}",
        snapshot_id=None,
        live_dir=live_dir,
        transaction_dir=None,
        staged_dir=None,
        rollback_dir=None,
        failed_dir=None,
        lock_path=lock_path,
    )


def _read_lock_metadata(lock_path: Path) -> dict[str, object]:
    try:
        raw = json.loads((lock_path / _LOCK_OWNER_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(key, str)}


def _validate_snapshot(path: Path, mode: ConsistencyMode = "ready-publish") -> None:
    if not path.is_dir():
        raise ContinuousRefactorError(f"Migration snapshot is not a directory: {path}")
    snapshot_tree_digest(path)
    findings = _publish_validation_findings(path, mode)
    if not has_blocking_consistency_findings(findings):
        return
    details = "; ".join(
        f"{finding.code}: {finding.path}: {finding.message}"
        for finding in findings
        if finding.severity == "error"
    )
    raise ContinuousRefactorError(f"migration snapshot is inconsistent: {details}")


def _publish_validation_findings(
    path: Path,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    findings = check_migration_consistency(path, mode=mode)
    if not _is_transaction_staged_snapshot(path):
        return findings
    return [
        finding
        for finding in findings
        if finding.code != "manifest-slug-mismatch"
    ]


def _is_transaction_staged_snapshot(path: Path) -> bool:
    return path.name == "staged" and _TRANSACTIONS_DIR_NAME in path.parts


def _dirty_live_migration_paths(repo_root: Path, live_dir: Path) -> tuple[str, ...]:
    pathspec = _repo_relative(live_dir, repo_root)
    result = run_command(
        ["git", "status", "--porcelain", "--ignored=matching", "--", pathspec],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise ContinuousRefactorError(
            "Could not inspect live migration git status.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return tuple(
        line[3:] if len(line) > 3 else line
        for line in result.stdout.splitlines()
        if line.strip()
    )


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise ContinuousRefactorError(
            f"Live migration path must stay inside repository: {path}"
        ) from error


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def _move_path(source: Path, destination: Path) -> None:
    source.replace(destination)


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path)


def _same_device(source: Path, target_root: Path) -> bool:
    return source.stat().st_dev == target_root.stat().st_dev


def _new_transaction_token() -> str:
    return uuid.uuid4().hex


def _restore_rollback(
    live_dir: Path,
    tx_paths: _TransactionPaths,
    *,
    move_live_to_failed: bool = False,
) -> str | None:
    try:
        if move_live_to_failed and live_dir.exists():
            _move_path(live_dir, tx_paths.failed_dir)
        if tx_paths.rollback_dir.exists():
            _move_path(tx_paths.rollback_dir, live_dir)
            return None
        return "rollback snapshot is unavailable"
    except OSError as error:
        return f"rollback restore failed: {error}"


def _with_restore_context(message: str, restore_error: str | None) -> str:
    if restore_error is None:
        return f"{message}; previous live snapshot was restored"
    return f"{message}; {restore_error}"


def _cleanup_rollback(rollback_dir: Path) -> str | None:
    if not rollback_dir.exists():
        return None
    try:
        _remove_tree(rollback_dir)
    except _FS_ERRORS as error:
        return f"could not remove rollback transaction directory {rollback_dir}: {error}"
    return None


def _remove_empty_dir(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        return


def _blocked_result(
    reason: str,
    *,
    live_dir: Path,
    tx_paths: _TransactionPaths | None = None,
    dirty_paths: tuple[str, ...] = (),
) -> PlanningPublishResult:
    return PlanningPublishResult(
        status="blocked",
        reason=reason,
        snapshot_id=snapshot_tree_digest(live_dir),
        live_dir=live_dir,
        transaction_dir=tx_paths.transaction_dir if tx_paths is not None else None,
        staged_dir=tx_paths.staged_dir if tx_paths is not None else None,
        rollback_dir=tx_paths.rollback_dir if tx_paths is not None else None,
        failed_dir=tx_paths.failed_dir if tx_paths is not None else None,
        dirty_paths=dirty_paths,
    )


def _failed_result(
    reason: str,
    *,
    live_dir: Path,
    tx_paths: _TransactionPaths,
) -> PlanningPublishResult:
    return PlanningPublishResult(
        status="failed",
        reason=reason,
        snapshot_id=snapshot_tree_digest(live_dir),
        live_dir=live_dir,
        transaction_dir=tx_paths.transaction_dir,
        staged_dir=tx_paths.staged_dir,
        rollback_dir=tx_paths.rollback_dir,
        failed_dir=tx_paths.failed_dir,
        lock_path=publish_lock_path(live_dir.parent),
    )


def _with_cleanup_error(
    result: PlanningPublishResult,
    cleanup_error: str,
) -> PlanningPublishResult:
    combined = (
        cleanup_error
        if result.cleanup_error is None
        else f"{result.cleanup_error}; {cleanup_error}"
    )
    return replace(result, cleanup_error=combined)


def _raise_result(result: PlanningPublishResult) -> None:
    raise PlanningPublishError(result)


def _result_message(result: PlanningPublishResult) -> str:
    lines = [result.reason]
    if result.dirty_paths:
        lines.append("dirty paths:")
        lines.extend(f"- {path}" for path in result.dirty_paths)
    if result.lock_path is not None:
        lines.append(f"lock={result.lock_path}")
    if result.status == "failed":
        if result.live_dir is not None:
            lines.append(f"live={result.live_dir}")
        if result.rollback_dir is not None:
            lines.append(f"rollback={result.rollback_dir}")
        if result.staged_dir is not None:
            lines.append(f"staged={result.staged_dir}")
        if result.failed_dir is not None:
            lines.append(f"failed={result.failed_dir}")
    if result.cleanup_error is not None:
        lines.append(f"cleanup_error={result.cleanup_error}")
    return "\n".join(lines)


def _relative_name(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
