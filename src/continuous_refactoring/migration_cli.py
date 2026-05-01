from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from continuous_refactoring.artifacts import (
    ContinuousRefactorError,
    create_run_artifacts,
)
from continuous_refactoring.config import resolve_live_migrations_dir, resolve_project
from continuous_refactoring.migration_consistency import (
    MigrationConsistencyFinding,
    check_migration_consistency,
    has_blocking_consistency_findings,
    iter_visible_migration_dirs,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    load_manifest as load_migration_manifest,
    phase_file_reference,
    resolve_current_phase,
)
from continuous_refactoring.planning_publish import publish_lock_path
from continuous_refactoring.planning_state import (
    FeedbackSource,
    load_planning_state,
    planning_state_path,
)

__all__ = [
    "MigrationCliContext",
    "MigrationTarget",
    "handle_migration",
    "handle_migration_doctor",
    "handle_migration_list",
    "handle_migration_refine",
    "handle_migration_review",
    "resolve_migration_target",
]

_MIGRATION_USAGE = "Usage: continuous-refactoring migration {list,doctor,review,refine}"
_MISSING_TEXT = "(none)"


@dataclass(frozen=True)
class MigrationCliContext:
    repo_root: Path
    live_dir: Path
    project_state_dir: Path


@dataclass(frozen=True)
class MigrationTarget:
    slug: str
    path: Path


def handle_migration(args: argparse.Namespace) -> None:
    if args.migration_command == "list":
        return handle_migration_list(args)
    if args.migration_command == "doctor":
        return handle_migration_doctor(args)
    if args.migration_command == "review":
        return handle_migration_review(args)
    if args.migration_command == "refine":
        return handle_migration_refine(args)
    print(_MIGRATION_USAGE, file=sys.stderr)
    raise SystemExit(2)


def handle_migration_list(args: argparse.Namespace) -> None:
    context = _resolve_context(error_code=1)
    if not context.live_dir.is_dir():
        return

    for migration_dir in iter_visible_migration_dirs(context.live_dir):
        row = _list_row(context, migration_dir)
        if row is None:
            continue
        if args.status is not None and row.status != args.status:
            continue
        if args.awaiting_review and row.awaiting_review != "yes":
            continue
        print(row.format())


def handle_migration_doctor(args: argparse.Namespace) -> None:
    context = _resolve_context(error_code=2)
    target: str | None = getattr(args, "target", None)
    all_targets = bool(getattr(args, "all", False))
    if all_targets == bool(target):
        print(
            "Error: migration doctor requires exactly one of --all or <slug-or-path>.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if all_targets:
        findings = _doctor_all(context)
    else:
        assert target is not None
        try:
            migration_target = resolve_migration_target(
                live_dir=context.live_dir,
                repo_root=context.repo_root,
                value=target,
            )
        except ContinuousRefactorError as error:
            print(f"Error: {error}", file=sys.stderr)
            raise SystemExit(2) from error
        findings = _doctor_migration(context, migration_target)

    for slug, finding in findings:
        print(_format_doctor_finding(slug, finding))
    if has_blocking_consistency_findings(finding for _, finding in findings):
        raise SystemExit(1)


def handle_migration_review(args: argparse.Namespace) -> None:
    context = _resolve_context(error_code=2)
    try:
        target = resolve_migration_target(
            live_dir=context.live_dir,
            repo_root=context.repo_root,
            value=args.target,
        )
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    from continuous_refactoring.config import load_taste
    from continuous_refactoring.review_cli import (
        StagedReviewRequest,
        handle_staged_migration_review,
    )

    try:
        taste = load_taste(resolve_project(context.repo_root))
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    handle_staged_migration_review(
        StagedReviewRequest(
            repo_root=context.repo_root,
            live_dir=context.live_dir,
            target=target,
            project_state_dir=context.project_state_dir,
            agent=args.agent,
            model=args.model,
            effort=args.effort,
            taste=taste,
        )
    )


def handle_migration_refine(args: argparse.Namespace) -> None:
    context = _resolve_context(error_code=2)
    feedback_text, feedback_source = _read_refine_feedback(args)
    try:
        target = resolve_migration_target(
            live_dir=context.live_dir,
            repo_root=context.repo_root,
            value=args.target,
        )
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    from continuous_refactoring.config import load_taste
    from continuous_refactoring.planning import (
        PlanningRefineRequest,
        run_refine_planning_step,
    )

    try:
        taste = load_taste(resolve_project(context.repo_root))
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    artifacts = create_run_artifacts(
        context.repo_root,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        test_command="migration refine",
    )
    try:
        result = run_refine_planning_step(
            PlanningRefineRequest(
                migration_name=target.slug,
                feedback_text=feedback_text,
                feedback_source=feedback_source,
                taste=taste,
                repo_root=context.repo_root,
                live_dir=context.live_dir,
                artifacts=artifacts,
                agent=args.agent,
                model=args.model,
                effort=args.effort,
            )
        )
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(_refine_error_code(str(error))) from error

    if result.status != "published":
        print(
            f"Error: {_refine_publish_error_message(result.reason, target.slug)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"Refined {target.slug}: {result.reason}")


def resolve_migration_target(
    *,
    live_dir: Path,
    repo_root: Path,
    value: str,
) -> MigrationTarget:
    live_root = live_dir.resolve()
    slug_target = _slug_target(live_root, value)
    path_target = _path_target(
        live_root,
        repo_root.resolve(),
        value,
        reject_symlink=slug_target is None,
    )

    if (
        slug_target is not None
        and path_target is not None
        and slug_target.path.resolve() != path_target.path.resolve()
    ):
        raise ContinuousRefactorError(
            f"Migration target {value!r} is ambiguous between "
            f"{slug_target.path} and {path_target.path}."
        )
    if slug_target is not None:
        return slug_target
    if path_target is not None:
        return path_target
    if _looks_like_path(value):
        _raise_invalid_path_target(live_root, repo_root.resolve(), value)
    raise ContinuousRefactorError(f"Migration {value!r} does not exist.")


def _read_refine_feedback(args: argparse.Namespace) -> tuple[str, FeedbackSource]:
    if args.message is not None:
        text = str(args.message)
        source: FeedbackSource = "message"
    else:
        try:
            path = args.file
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            print(
                f"Error: could not read refinement feedback file: {error}",
                file=sys.stderr,
            )
            raise SystemExit(2) from error
        source = "file"
    if not text.strip():
        print("Error: refinement feedback must not be empty.", file=sys.stderr)
        raise SystemExit(2)
    return text, source


def _refine_publish_error_message(reason: str, slug: str) -> str:
    if "stale base snapshot" not in reason:
        return reason
    return (
        f"{reason}\n"
        "Live migration changed while refine was running. "
        f"Run `continuous-refactoring migration doctor {slug}` if unsure, then "
        f"rerun `continuous-refactoring migration refine {slug} ...`."
    )


def _refine_error_code(message: str) -> int:
    usage_fragments = (
        "cannot be refined",
        "only planning or unexecuted ready migrations",
        "already advanced",
        "missing .planning/state.json",
        "Cannot reopen planning state",
        "Planning state is terminal",
    )
    return 2 if any(fragment in message for fragment in usage_fragments) else 1


@dataclass(frozen=True)
class _ListRow:
    slug: str
    status: str
    cursor: str
    awaiting_review: str
    last_touch: str
    cooldown: str
    reason: str

    def format(self) -> str:
        return "\t".join(
            (
                self.slug,
                self.status,
                self.cursor,
                self.awaiting_review,
                self.last_touch,
                self.cooldown,
                self.reason,
            )
        )


def _resolve_context(*, error_code: int) -> MigrationCliContext:
    try:
        project = resolve_project(Path.cwd().resolve())
    except ContinuousRefactorError:
        print(
            "Error: project not initialized; no live-migrations-dir available.",
            file=sys.stderr,
        )
        raise SystemExit(error_code)
    try:
        live_dir = resolve_live_migrations_dir(project)
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(error_code)
    if live_dir is None:
        print(
            "Error: no live-migrations-dir configured for this project.",
            file=sys.stderr,
        )
        raise SystemExit(error_code)
    return MigrationCliContext(
        repo_root=Path(project.entry.path).resolve(),
        live_dir=live_dir,
        project_state_dir=project.project_dir,
    )


def _list_row(
    context: MigrationCliContext,
    migration_dir: Path,
) -> _ListRow | None:
    manifest_path = migration_dir / "manifest.json"
    if not manifest_path.exists():
        return _ListRow(
            slug=migration_dir.name,
            status="invalid-manifest",
            cursor="blocked",
            awaiting_review="no",
            last_touch=_MISSING_TEXT,
            cooldown=_MISSING_TEXT,
            reason="missing-manifest",
        )
    try:
        manifest = load_migration_manifest(manifest_path)
    except ContinuousRefactorError as error:
        return _ListRow(
            slug=migration_dir.name,
            status="invalid-manifest",
            cursor="blocked",
            awaiting_review="no",
            last_touch=_MISSING_TEXT,
            cooldown=_MISSING_TEXT,
            reason=f"invalid-manifest: {_single_line(str(error))}",
        )

    cursor, cursor_reason = _cursor_text(context, migration_dir, manifest)
    return _ListRow(
        slug=migration_dir.name,
        status=manifest.status,
        cursor=cursor,
        awaiting_review="yes" if manifest.awaiting_human_review else "no",
        last_touch=manifest.last_touch,
        cooldown=manifest.cooldown_until or _MISSING_TEXT,
        reason=_reason_text(manifest, cursor_reason),
    )


def _cursor_text(
    context: MigrationCliContext,
    migration_dir: Path,
    manifest: MigrationManifest,
) -> tuple[str, str | None]:
    if manifest.status == "planning":
        return _planning_cursor(context, migration_dir)
    if manifest.status in ("ready", "in-progress"):
        if not manifest.current_phase:
            return _MISSING_TEXT, None
        try:
            phase = resolve_current_phase(manifest)
        except ContinuousRefactorError:
            return "blocked", "invalid-current-phase"
        return phase_file_reference(phase), None
    return _MISSING_TEXT, None


def _planning_cursor(
    context: MigrationCliContext,
    migration_dir: Path,
) -> tuple[str, str | None]:
    state_path = planning_state_path(migration_dir)
    if not state_path.exists():
        return "planning:blocked", "planning-state-missing"
    try:
        state = load_planning_state(
            context.repo_root,
            state_path,
            published_migration_root=migration_dir,
        )
    except ContinuousRefactorError:
        return "planning:blocked", "planning-state-invalid"
    return f"planning:{state.next_step}", None


def _reason_text(manifest: MigrationManifest, cursor_reason: str | None) -> str:
    if cursor_reason is not None:
        return cursor_reason
    if manifest.human_review_reason:
        return manifest.human_review_reason
    return _MISSING_TEXT


def _doctor_all(
    context: MigrationCliContext,
) -> list[tuple[str, MigrationConsistencyFinding]]:
    findings: list[tuple[str, MigrationConsistencyFinding]] = []
    for migration_dir in iter_visible_migration_dirs(context.live_dir):
        findings.extend(
            _doctor_migration(
                context,
                MigrationTarget(slug=migration_dir.name, path=migration_dir),
            )
        )
    findings.extend(_transaction_findings(context.live_dir))
    return findings


def _doctor_migration(
    context: MigrationCliContext,
    target: MigrationTarget,
) -> list[tuple[str, MigrationConsistencyFinding]]:
    findings = check_migration_consistency(target.path, mode="doctor")
    findings.extend(_planning_state_findings(context, target.path))
    return [(target.slug, finding) for finding in findings]


def _planning_state_findings(
    context: MigrationCliContext,
    migration_dir: Path,
) -> list[MigrationConsistencyFinding]:
    manifest_path = migration_dir / "manifest.json"
    try:
        manifest = load_migration_manifest(manifest_path)
    except ContinuousRefactorError:
        return []
    if manifest.status != "planning":
        return []

    state_path = planning_state_path(migration_dir)
    if not state_path.exists():
        return [
            MigrationConsistencyFinding(
                severity="error",
                mode="doctor",
                code="planning-state-missing",
                path=state_path,
                message="Planning migration is missing .planning/state.json.",
            )
        ]
    try:
        load_planning_state(
            context.repo_root,
            state_path,
            published_migration_root=migration_dir,
        )
    except ContinuousRefactorError as error:
        return [
            MigrationConsistencyFinding(
                severity="error",
                mode="doctor",
                code="planning-state-invalid",
                path=state_path,
                message=_single_line(str(error)),
            )
        ]
    return []


def _transaction_findings(
    live_dir: Path,
) -> list[tuple[str, MigrationConsistencyFinding]]:
    transaction_root = publish_lock_path(live_dir).parent
    if not transaction_root.exists():
        return []
    if not transaction_root.is_dir():
        return [
            (
                "__transactions__",
                MigrationConsistencyFinding(
                    severity="error",
                    mode="doctor",
                    code="transaction-root-invalid",
                    path=transaction_root,
                    message="Planning transaction root is not a directory.",
                ),
            )
        ]

    findings: list[tuple[str, MigrationConsistencyFinding]] = []
    lock_path = publish_lock_path(live_dir)
    if lock_path.exists():
        findings.append(
            (
                "__transactions__",
                MigrationConsistencyFinding(
                    severity="error",
                    mode="doctor",
                    code="publish-lock-present",
                    path=lock_path,
                    message=_lock_message(lock_path),
                ),
            )
        )

    for child in sorted(transaction_root.iterdir()):
        if child == lock_path:
            continue
        if child.is_dir():
            findings.append(
                (
                    "__transactions__",
                    MigrationConsistencyFinding(
                        severity="error",
                        mode="doctor",
                        code="transaction-leftover",
                        path=child,
                        message="Planning transaction directory is still present.",
                    ),
                )
            )
    return findings


def _format_doctor_finding(
    slug: str,
    finding: MigrationConsistencyFinding,
) -> str:
    return "\t".join(
        (
            slug,
            finding.severity,
            finding.code,
            str(finding.path),
            finding.message,
        )
    )


def _slug_target(live_root: Path, value: str) -> MigrationTarget | None:
    if not _safe_slug(value):
        return None
    path = live_root / value
    if not path.is_dir() or path.is_symlink():
        return None
    return MigrationTarget(slug=value, path=path)


def _path_target(
    live_root: Path,
    repo_root: Path,
    value: str,
    *,
    reject_symlink: bool,
) -> MigrationTarget | None:
    if not _should_consider_path(repo_root, value):
        return None
    _require_no_parent_traversal(value)
    path = _raw_path(repo_root, value)
    if reject_symlink and path.is_symlink():
        raise ContinuousRefactorError(
            f"Migration path must not be a symlink: {path}"
        )
    resolved = path.resolve()
    if not resolved.exists():
        return None
    _require_contained_visible_child(live_root, resolved, original=path)
    return MigrationTarget(slug=resolved.name, path=resolved)


def _raise_invalid_path_target(live_root: Path, repo_root: Path, value: str) -> None:
    _require_no_parent_traversal(value)
    path = _raw_path(repo_root, value)
    if path.is_symlink():
        raise ContinuousRefactorError(
            f"Migration path must not be a symlink: {path}"
        )
    resolved = path.resolve()
    _require_contained_visible_child(live_root, resolved, original=path)
    if not resolved.is_dir():
        raise ContinuousRefactorError(f"Migration path is not a directory: {path}")


def _require_contained_visible_child(
    live_root: Path,
    resolved: Path,
    *,
    original: Path,
) -> None:
    try:
        relative = resolved.relative_to(live_root)
    except ValueError as error:
        raise ContinuousRefactorError(
            f"Migration path must stay inside live migrations dir: {original}"
        ) from error
    if len(relative.parts) != 1:
        raise ContinuousRefactorError(
            f"Migration path must identify a direct migration directory: {original}"
        )
    if not _safe_slug(relative.parts[0]):
        raise ContinuousRefactorError(
            f"Migration path targets a hidden or internal directory: {original}"
        )
    if not resolved.is_dir():
        raise ContinuousRefactorError(f"Migration path is not a directory: {original}")


def _safe_slug(value: str) -> bool:
    return (
        value != ""
        and Path(value).name == value
        and not value.startswith(".")
        and not value.startswith("__")
    )


def _should_consider_path(repo_root: Path, value: str) -> bool:
    return _looks_like_path(value) or _raw_path(repo_root, value).exists()


def _looks_like_path(value: str) -> bool:
    path = Path(value)
    return path.is_absolute() or len(path.parts) > 1 or value.startswith(".")


def _require_no_parent_traversal(value: str) -> None:
    if ".." in Path(value).parts:
        raise ContinuousRefactorError(
            f"Migration path must not contain parent traversal: {value}"
        )


def _raw_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def _lock_message(lock_path: Path) -> str:
    details = _lock_metadata(lock_path)
    try:
        mtime = datetime.fromtimestamp(lock_path.stat().st_mtime).astimezone()
    except OSError:
        mtime_text = "unknown"
    else:
        mtime_text = mtime.isoformat(timespec="seconds")
    suffix = f"; {details}" if details else ""
    return f"Planning publish lock is present; mtime={mtime_text}{suffix}."


def _lock_metadata(lock_path: Path) -> str:
    owner_path = lock_path / "owner.json"
    try:
        raw = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(raw, dict):
        return ""
    parts = [
        f"{key}={raw[key]}"
        for key in ("pid", "operation", "created_at")
        if key in raw
    ]
    return ", ".join(parts)


def _single_line(value: str) -> str:
    return " ".join(value.split())
