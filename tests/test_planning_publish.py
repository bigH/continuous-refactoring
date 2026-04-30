from __future__ import annotations

from pathlib import Path

import pytest

import continuous_refactoring.planning_publish as planning_publish
from conftest import init_repo
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.git import run_command
from continuous_refactoring.migration_consistency import (
    check_migration_consistency,
    has_blocking_consistency_findings,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    save_manifest,
)


_NOW = "2026-04-29T12:00:00.000+00:00"
_PHASE = PhaseSpec(
    name="setup",
    file="phase-0-setup.md",
    done=False,
    precondition="always",
)


def _manifest(slug: str) -> MigrationManifest:
    return MigrationManifest(
        name=slug,
        created_at=_NOW,
        last_touch=_NOW,
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase=_PHASE.name,
        phases=(_PHASE,),
    )


def _write_snapshot(root: Path, slug: str, version: str, *, extra: bool = False) -> Path:
    migration_dir = root / slug
    migration_dir.mkdir(parents=True)
    (migration_dir / "plan.md").write_text(f"# Plan {version}\n", encoding="utf-8")
    (migration_dir / _PHASE.file).write_text(
        f"## Precondition\n\nalways\n\n## Definition of Done\n\n{version}\n",
        encoding="utf-8",
    )
    if extra:
        (migration_dir / "notes.md").write_text(f"{version}\n", encoding="utf-8")
    save_manifest(_manifest(slug), migration_dir / "manifest.json")
    return migration_dir


def _request(
    repo_root: Path,
    live_migrations_dir: Path,
    slug: str,
    workspace_dir: Path,
    *,
    base_snapshot_id: str | None = None,
) -> planning_publish.PlanningPublishRequest:
    return planning_publish.PlanningPublishRequest(
        repo_root=repo_root,
        live_migrations_dir=live_migrations_dir,
        slug=slug,
        workspace_dir=workspace_dir,
        base_snapshot_id=(
            base_snapshot_id
            if base_snapshot_id is not None
            else planning_publish.snapshot_tree_digest(live_migrations_dir / slug)
        ),
    )


def _tree(path: Path) -> dict[str, str]:
    return {
        child.relative_to(path).as_posix(): child.read_text(encoding="utf-8")
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


def _commit_all(repo_root: Path, message: str = "commit") -> None:
    run_command(["git", "add", "-A"], cwd=repo_root)
    run_command(["git", "commit", "-m", message], cwd=repo_root)


def _tx(live_migrations_dir: Path, token: str) -> Path:
    return live_migrations_dir / "__transactions__" / token


def _stable_token(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setattr(planning_publish, "_new_transaction_token", lambda: token)


def test_publish_creates_new_live_migration_from_staged_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    _stable_token(monkeypatch, "tx-create")

    result = planning_publish.publish_planning_workspace(
        _request(repo, live_dir, "auth-cleanup", workspace)
    )

    assert result.status == "published"
    assert result.live_dir == live_dir / "auth-cleanup"
    assert _tree(live_dir / "auth-cleanup") == _tree(workspace)
    findings = check_migration_consistency(
        live_dir / "auth-cleanup", mode="execution-gate"
    )
    assert not has_blocking_consistency_findings(findings)
    assert result.cleanup_error is None
    assert not _tx(live_dir, "tx-create").exists()


def test_publish_replaces_existing_non_empty_live_dir_with_backup_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old", extra=True)
    _commit_all(repo, "old migration")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    _stable_token(monkeypatch, "tx-replace")

    result = planning_publish.publish_planning_workspace(
        _request(repo, live_dir, "auth-cleanup", workspace)
    )

    assert result.status == "published"
    assert _tree(old_live) == _tree(workspace)
    assert not (old_live / "notes.md").exists()
    assert not (_tx(live_dir, "tx-replace") / "rollback").exists()
    assert not (_tx(live_dir, "tx-replace") / "failed").exists()


def test_publish_requires_same_device_final_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    old_tree = _tree(old_live)
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    seen: list[tuple[Path, Path]] = []
    _stable_token(monkeypatch, "tx-device")

    def different_device(source: Path, target_root: Path) -> bool:
        seen.append((source, target_root))
        return False

    def fail_move(_source: Path, _destination: Path) -> None:
        raise AssertionError("publish must not move live state across devices")

    monkeypatch.setattr(planning_publish, "_same_device", different_device)
    monkeypatch.setattr(planning_publish, "_move_path", fail_move)

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    assert exc.value.result.status == "blocked"
    assert "same filesystem" in str(exc.value)
    assert seen == [(_tx(live_dir, "tx-device") / "staged", live_dir)]
    assert _tree(old_live) == old_tree
    assert (_tx(live_dir, "tx-device") / "staged").is_dir()
    assert not (_tx(live_dir, "tx-device") / "rollback").exists()


def test_staged_validation_failure_leaves_live_snapshot_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    old_tree = _tree(old_live)
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    validated: list[Path] = []
    _stable_token(monkeypatch, "tx-stage-invalid")

    def validate(path: Path, mode: str = "ready-publish") -> None:
        validated.append(path)
        if path.name == "staged":
            raise ContinuousRefactorError("staged invalid")

    def fail_live_move(source: Path, _destination: Path) -> None:
        if source == old_live:
            raise AssertionError("live dir must not move after staged validation fails")

    monkeypatch.setattr(planning_publish, "_validate_snapshot", validate)
    monkeypatch.setattr(planning_publish, "_move_path", fail_live_move)

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    assert exc.value.result.status == "blocked"
    assert "staged invalid" in str(exc.value)
    assert validated == [workspace, _tx(live_dir, "tx-stage-invalid") / "staged"]
    assert _tree(old_live) == old_tree
    assert (_tx(live_dir, "tx-stage-invalid") / "staged").is_dir()
    assert not (_tx(live_dir, "tx-stage-invalid") / "rollback").exists()


def test_publish_rejects_stale_base_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    stale_base = planning_publish.snapshot_tree_digest(old_live)
    (old_live / "plan.md").write_text("# human edit\n", encoding="utf-8")
    _commit_all(repo, "human migration edit")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    _stable_token(monkeypatch, "tx-stale")

    def fail_live_move(source: Path, _destination: Path) -> None:
        if source == old_live:
            raise AssertionError("stale publish must not move live state")

    monkeypatch.setattr(planning_publish, "_move_path", fail_live_move)

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(
                repo,
                live_dir,
                "auth-cleanup",
                workspace,
                base_snapshot_id=stale_base,
            )
        )

    assert exc.value.result.status == "blocked"
    assert "stale base snapshot" in str(exc.value)
    assert "base_snapshot_id" in str(exc.value)
    assert (old_live / "plan.md").read_text(encoding="utf-8") == "# human edit\n"
    assert (_tx(live_dir, "tx-stale") / "staged").is_dir()
    assert not (_tx(live_dir, "tx-stale") / "rollback").exists()


def test_nested_transaction_named_dir_changes_snapshot_digest_and_blocks_stale_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    stale_base = planning_publish.snapshot_tree_digest(old_live)
    nested = old_live / "__transactions__"
    nested.mkdir()
    (nested / "user-note.md").write_text("do not drop\n", encoding="utf-8")
    _commit_all(repo, "nested transaction-named user dir")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    _stable_token(monkeypatch, "tx-nested-stale")

    def fail_live_move(source: Path, _destination: Path) -> None:
        if source == old_live:
            raise AssertionError("stale publish must not move live state")

    monkeypatch.setattr(planning_publish, "_move_path", fail_live_move)

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(
                repo,
                live_dir,
                "auth-cleanup",
                workspace,
                base_snapshot_id=stale_base,
            )
        )

    assert exc.value.result.status == "blocked"
    assert "stale base snapshot" in str(exc.value)
    assert (nested / "user-note.md").read_text(encoding="utf-8") == "do not drop\n"
    assert not (_tx(live_dir, "tx-nested-stale") / "rollback").exists()


def test_publish_cleans_backup_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    _stable_token(monkeypatch, "tx-clean")

    result = planning_publish.publish_planning_workspace(
        _request(repo, live_dir, "auth-cleanup", workspace)
    )

    assert result.status == "published"
    assert result.cleanup_error is None
    assert _tree(old_live) == _tree(workspace)
    assert not (_tx(live_dir, "tx-clean") / "rollback").exists()
    assert not _tx(live_dir, "tx-clean").exists()


def test_publish_restores_rollback_when_live_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    old_tree = _tree(old_live)
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    original_move = planning_publish._move_path
    _stable_token(monkeypatch, "tx-restore")

    def fail_install(source: Path, destination: Path) -> None:
        if source == _tx(live_dir, "tx-restore") / "staged" and destination == old_live:
            raise OSError("cannot install staged")
        original_move(source, destination)

    monkeypatch.setattr(planning_publish, "_move_path", fail_install)

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    assert exc.value.result.status == "failed"
    assert "cannot install staged" in str(exc.value)
    assert _tree(old_live) == old_tree
    assert (_tx(live_dir, "tx-restore") / "staged").is_dir()
    assert not (_tx(live_dir, "tx-restore") / "rollback").exists()


def test_publish_reports_live_rollback_staged_and_failed_paths_when_rollback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    original_move = planning_publish._move_path
    _stable_token(monkeypatch, "tx-rollback-fails")

    def validate(path: Path, mode: str = "ready-publish") -> None:
        if path == old_live:
            raise ContinuousRefactorError("live validation failed")

    def fail_restore(source: Path, destination: Path) -> None:
        if source == _tx(live_dir, "tx-rollback-fails") / "rollback" and destination == old_live:
            raise OSError("rollback restore failed")
        original_move(source, destination)

    monkeypatch.setattr(planning_publish, "_validate_snapshot", validate)
    monkeypatch.setattr(planning_publish, "_move_path", fail_restore)

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    message = str(exc.value)
    assert exc.value.result.status == "failed"
    assert "rollback restore failed" in message
    assert "live=" in message
    assert "rollback=" in message
    assert "staged=" in message
    assert "failed=" in message
    assert (_tx(live_dir, "tx-rollback-fails") / "rollback").is_dir()
    assert (_tx(live_dir, "tx-rollback-fails") / "failed").is_dir()


def test_publish_refuses_dirty_live_migration_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    (old_live / "plan.md").write_text("# dirty tracked\n", encoding="utf-8")
    (old_live / "local.md").write_text("local\n", encoding="utf-8")
    tx_noise = live_dir / "__transactions__" / "old" / "staged"
    tx_noise.mkdir(parents=True)
    (tx_noise / "ignored.md").write_text("ignored\n", encoding="utf-8")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    _stable_token(monkeypatch, "tx-dirty")

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    message = str(exc.value)
    assert exc.value.result.status == "blocked"
    assert "dirty live migration" in message
    assert "migrations/auth-cleanup/plan.md" in message
    assert "migrations/auth-cleanup/local.md" in message
    assert "__transactions__" not in message
    assert not _tx(live_dir, "tx-dirty").exists()


def test_publish_refuses_ignored_live_migration_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    _write_snapshot(live_dir, "auth-cleanup", "old")
    (repo / ".gitignore").write_text(
        "migrations/auth-cleanup/*.cache\n",
        encoding="utf-8",
    )
    _commit_all(repo, "old migration with ignore rule")
    ignored = live_dir / "auth-cleanup" / "local.cache"
    ignored.write_text("operator scratch\n", encoding="utf-8")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    _stable_token(monkeypatch, "tx-ignored-dirty")

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    message = str(exc.value)
    assert exc.value.result.status == "blocked"
    assert "dirty live migration" in message
    assert "migrations/auth-cleanup/local.cache" in message
    assert ignored.read_text(encoding="utf-8") == "operator scratch\n"
    assert not _tx(live_dir, "tx-ignored-dirty").exists()


def test_lock_rejects_concurrent_mutation_and_reports_lock_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    lock_path = planning_publish.publish_lock_path(live_dir)
    lock_path.mkdir(parents=True)
    (lock_path / "owner.json").write_text(
        '{"pid": 123, "operation": "review", '
        '"created_at": "2026-04-29T12:00:00.000+00:00"}\n',
        encoding="utf-8",
    )
    _stable_token(monkeypatch, "tx-locked")

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    message = str(exc.value)
    assert exc.value.result.status == "blocked"
    assert "concurrent mutation" in message
    assert str(lock_path) in message
    assert "123" in message
    assert "review" in message
    assert "2026-04-29T12:00:00.000+00:00" in message
    assert _tree(old_live) != _tree(workspace)
    assert not _tx(live_dir, "tx-locked").exists()


def test_publish_reports_lock_cleanup_failure_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    original_remove = planning_publish._remove_tree
    _stable_token(monkeypatch, "tx-lock-cleanup-fails")

    def fail_lock_cleanup(path: Path) -> None:
        if path == planning_publish.publish_lock_path(live_dir):
            raise OSError("lock cleanup denied")
        original_remove(path)

    monkeypatch.setattr(planning_publish, "_remove_tree", fail_lock_cleanup)

    result = planning_publish.publish_planning_workspace(
        _request(repo, live_dir, "auth-cleanup", workspace)
    )

    assert result.status == "published"
    assert result.cleanup_error is not None
    assert "lock cleanup denied" in result.cleanup_error
    assert _tree(old_live) == _tree(workspace)
    assert planning_publish.publish_lock_path(live_dir).is_dir()


def test_publish_moves_partial_live_to_failed_before_restoring_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    old_tree = _tree(old_live)
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    original_move = planning_publish._move_path
    _stable_token(monkeypatch, "tx-partial-live")

    def fail_install_with_partial_live(source: Path, destination: Path) -> None:
        if source == _tx(live_dir, "tx-partial-live") / "staged" and destination == old_live:
            destination.mkdir()
            (destination / "partial.md").write_text("bad partial\n", encoding="utf-8")
            raise OSError("cannot install staged")
        original_move(source, destination)

    monkeypatch.setattr(planning_publish, "_move_path", fail_install_with_partial_live)

    with pytest.raises(planning_publish.PlanningPublishError) as exc:
        planning_publish.publish_planning_workspace(
            _request(repo, live_dir, "auth-cleanup", workspace)
        )

    assert exc.value.result.status == "failed"
    assert _tree(old_live) == old_tree
    assert (
        _tx(live_dir, "tx-partial-live") / "failed" / "partial.md"
    ).read_text(encoding="utf-8") == "bad partial\n"


def test_transaction_dirs_are_left_for_doctor_when_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    live_dir = repo / "migrations"
    old_live = _write_snapshot(live_dir, "auth-cleanup", "old")
    _commit_all(repo, "old migration")
    old_tree = _tree(old_live)
    workspace = _write_snapshot(tmp_path / "workspace", "auth-cleanup", "new")
    original_remove = planning_publish._remove_tree
    _stable_token(monkeypatch, "tx-cleanup-fails")

    def fail_cleanup(path: Path) -> None:
        if path == _tx(live_dir, "tx-cleanup-fails") / "rollback":
            raise OSError("cleanup denied")
        original_remove(path)

    monkeypatch.setattr(planning_publish, "_remove_tree", fail_cleanup)

    result = planning_publish.publish_planning_workspace(
        _request(repo, live_dir, "auth-cleanup", workspace)
    )

    assert result.status == "published"
    assert result.cleanup_error is not None
    assert "cleanup denied" in result.cleanup_error
    assert _tree(old_live) == _tree(workspace)
    assert _tree(_tx(live_dir, "tx-cleanup-fails") / "rollback") == old_tree
    assert not (_tx(live_dir, "tx-cleanup-fails") / "failed").exists()
