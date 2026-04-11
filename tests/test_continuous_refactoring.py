from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    continuous_refactoring.run_command(["git", "init"], cwd=path)
    continuous_refactoring.run_command(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
    )
    continuous_refactoring.run_command(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "README.md"], cwd=path)
    continuous_refactoring.run_command(["git", "commit", "-m", "init"], cwd=path)


def _write_fake_codex(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "codex"
    script.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    output_path = None
    repo_root = None
    for index, arg in enumerate(args):
        if arg == "--output-last-message":
            output_path = Path(args[index + 1])
        if arg == "--cd":
            repo_root = Path(args[index + 1])

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            os.environ.get("FAKE_CODEX_LAST_MESSAGE", ""),
            encoding="utf-8",
        )

    stdout_text = os.environ.get("FAKE_CODEX_STDOUT", "")
    if stdout_text:
        sys.stdout.write(stdout_text)
        sys.stdout.flush()

    stderr_text = os.environ.get("FAKE_CODEX_STDERR", "")
    if stderr_text:
        sys.stderr.write(stderr_text)
        sys.stderr.flush()

    relative_path = os.environ.get("FAKE_CODEX_TOUCH_FILE")
    if relative_path and repo_root is not None:
        destination = repo_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            os.environ.get("FAKE_CODEX_TOUCH_CONTENT", ""),
            encoding="utf-8",
        )

    return int(os.environ.get("FAKE_CODEX_EXIT_CODE", "0"))


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_run_observed_command_writes_timestamped_logs(tmp_path: Path) -> None:
    stdout_path = tmp_path / "observed.stdout.log"
    stderr_path = tmp_path / "observed.stderr.log"

    result = continuous_refactoring.run_observed_command(
        [sys.executable, "-c", "print('hello from stdout')"],
        cwd=tmp_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        mirror_to_terminal=False,
    )

    assert result.returncode == 0
    assert result.stdout == "hello from stdout\n"
    assert result.stderr == ""
    assert re.search(r"^\[\d{4}-\d{2}-\d{2}T", stdout_path.read_text(encoding="utf-8"))
    assert "hello from stdout" in stdout_path.read_text(encoding="utf-8")
    assert "<no output>" in stderr_path.read_text(encoding="utf-8")


def test_extract_chosen_target_accepts_chosen_scope() -> None:
    text = """
    chosen_scope:
    - compiler cleanup batch
    """

    assert (
        continuous_refactoring.extract_chosen_target(text)
        == "compiler cleanup batch"
    )


def test_main_fails_at_startup_when_worktree_is_dirty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    (repo_root / "notes.txt").write_text("dirty\n", encoding="utf-8")

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    refactor_prompt = prompts_dir / "refactor.md"
    refactor_prompt.write_text("chosen_target: drop the foobizzy\n", encoding="utf-8")
    fix_prompt = prompts_dir / "fix.md"
    fix_prompt.write_text("chosen_target: recover the foobizzy\n", encoding="utf-8")

    test_script = tmp_path / "check_tests.py"
    test_script.write_text("print('tests ok')\n", encoding="utf-8")

    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setattr(
        continuous_refactoring.loop,
        "parse_args",
        lambda: argparse.Namespace(
            agent="codex",
            model="fake-model",
            effort="xhigh",
            refactoring_prompt=refactor_prompt,
            fix_prompt=fix_prompt,
            repo_root=repo_root,
            validation_command=f"{sys.executable} {test_script}",
            max_attempts=1,
            commit_message_prefix="continuous refactor",
            push_remote="origin",
            no_push=True,
        ),
    )

    with pytest.raises(
        continuous_refactoring.ContinuousRefactorError,
    ) as error:
        continuous_refactoring.main()
    assert "working copy has local changes" in str(error.value)
    assert "?? notes.txt" in str(error.value)

    run_root = tmpdir_root / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["final_status"] == "dirty_worktree"
    assert summary["counts"]["attempts_started"] == 0
    assert summary["error_message"]


def test_main_keeps_running_after_no_change_refactor_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    refactor_prompt = prompts_dir / "refactor.md"
    refactor_prompt.write_text("chosen_target: drop the foobizzy\n", encoding="utf-8")
    fix_prompt = prompts_dir / "fix.md"
    fix_prompt.write_text("chosen_target: recover the foobizzy\n", encoding="utf-8")

    test_script = tmp_path / "check_tests.py"
    test_script.write_text("print('tests ok')\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    _write_fake_codex(bin_dir)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("FAKE_CODEX_STDOUT", "- chosen_target: drop the foobizzy\n")
    monkeypatch.setenv("FAKE_CODEX_LAST_MESSAGE", "chosen_target: drop the foobizzy\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        continuous_refactoring.loop,
        "parse_args",
        lambda: argparse.Namespace(
            agent="codex",
            model="fake-model",
            effort="xhigh",
            refactoring_prompt=refactor_prompt,
            fix_prompt=fix_prompt,
            repo_root=repo_root,
            validation_command=f"{sys.executable} {test_script}",
            max_attempts=2,
            commit_message_prefix="continuous refactor",
            push_remote="origin",
            no_push=True,
        ),
    )

    exit_code = continuous_refactoring.main()

    assert exit_code == 0
    run_root = tmpdir_root / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["final_status"] == "max_attempts_reached"
    assert summary["counts"]["attempts_started"] == 2
    assert summary["counts"]["refactor_passed_no_changes"] == 2
    assert summary["attempts"][0]["refactor_target"] == "drop the foobizzy"
    assert summary["attempts"][0]["refactor_change_count"] == 0
    assert summary["attempts"][0]["commit_sha"] is None
    assert summary["attempts"][1]["refactor_target"] == "drop the foobizzy"
    assert summary["attempts"][1]["refactor_change_count"] == 0
    assert summary["attempts"][1]["commit_sha"] is None

    run_log = (run_dir / "run.log").read_text(encoding="utf-8")
    assert (
        "[WARN] completed attempted refactor with 0 changes: drop the foobizzy"
        in run_log
    )
    assert "[WARN] Reached max attempts." in run_log

    agent_stdout_log = run_dir / "attempt-001" / "refactor" / "agent.stdout.log"
    baseline_stdout_log = run_dir / "baseline" / "initial" / "tests.stdout.log"
    assert "drop the foobizzy" in agent_stdout_log.read_text(encoding="utf-8")
    assert "tests ok" in baseline_stdout_log.read_text(encoding="utf-8")

    output = capsys.readouterr().out
    assert "[INFO] run artifacts:" in output
    assert (
        "[WARN] completed attempted refactor with 0 changes: drop the foobizzy"
        in output
    )
    assert "Attempt 2/2: refactoring" in output


def test_main_runs_until_interrupted_by_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    refactor_prompt = prompts_dir / "refactor.md"
    refactor_prompt.write_text("chosen_target: drop the foobizzy\n", encoding="utf-8")
    fix_prompt = prompts_dir / "fix.md"
    fix_prompt.write_text("chosen_target: recover the foobizzy\n", encoding="utf-8")

    test_script = tmp_path / "check_tests.py"
    test_script.write_text("print('tests ok')\n", encoding="utf-8")

    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setattr(
        continuous_refactoring.loop,
        "parse_args",
        lambda: argparse.Namespace(
            agent="codex",
            model="fake-model",
            effort="xhigh",
            refactoring_prompt=refactor_prompt,
            fix_prompt=fix_prompt,
            repo_root=repo_root,
            validation_command=f"{sys.executable} {test_script}",
            max_attempts=None,
            commit_message_prefix="continuous refactor",
            push_remote="origin",
            no_push=True,
        ),
    )

    calls = 0

    def fake_run_refactoring_attempt(
        **_: object,
    ) -> continuous_refactoring.PhaseAttemptResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return continuous_refactoring.PhaseAttemptResult(
                passed=True,
                failure_context="",
                target="drop the foobizzy",
                agent_returncode=0,
                test_returncode=0,
            )
        raise KeyboardInterrupt

    monkeypatch.setattr(
        continuous_refactoring.loop,
        "run_refactoring_attempt",
        fake_run_refactoring_attempt,
    )

    exit_code = continuous_refactoring.main()

    assert exit_code == 130
    run_root = tmpdir_root / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["final_status"] == "interrupted"
    assert summary["counts"]["attempts_started"] == 2
    assert summary["counts"]["refactor_passed_no_changes"] == 1
    assert summary["counts"]["commits_created"] == 0

    run_log = (run_dir / "run.log").read_text(encoding="utf-8")
    assert "[WARN] Interrupted by user. Stopping continuous refactor loop." in run_log

    output = capsys.readouterr().out
    assert "Attempt 1: refactoring" in output
    assert "Attempt 2: refactoring" in output
    assert "[WARN] Interrupted by user. Stopping continuous refactor loop." in output


def test_main_records_committed_refactor_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    refactor_prompt = prompts_dir / "refactor.md"
    refactor_prompt.write_text(
        "chosen_scope: converge the splines\n",
        encoding="utf-8",
    )
    fix_prompt = prompts_dir / "fix.md"
    fix_prompt.write_text("chosen_target: fix the splines\n", encoding="utf-8")

    test_script = tmp_path / "check_tests.py"
    test_script.write_text("print('tests ok')\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    _write_fake_codex(bin_dir)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("FAKE_CODEX_STDOUT", "- chosen_scope: converge the splines\n")
    monkeypatch.setenv(
        "FAKE_CODEX_LAST_MESSAGE",
        "chosen_scope: converge the splines\n",
    )
    monkeypatch.setenv("FAKE_CODEX_TOUCH_FILE", "README.md")
    monkeypatch.setenv("FAKE_CODEX_TOUCH_CONTENT", "seed\nrefactor\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(
        continuous_refactoring.loop,
        "parse_args",
        lambda: argparse.Namespace(
            agent="codex",
            model="fake-model",
            effort="xhigh",
            refactoring_prompt=refactor_prompt,
            fix_prompt=fix_prompt,
            repo_root=repo_root,
            validation_command=f"{sys.executable} {test_script}",
            max_attempts=1,
            commit_message_prefix="continuous refactor",
            push_remote="origin",
            no_push=True,
        ),
    )

    exit_code = continuous_refactoring.main()

    assert exit_code == 0
    run_root = tmpdir_root / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["attempts_started"] == 1
    assert summary["counts"]["refactor_passed_with_changes"] == 1
    assert summary["counts"]["commits_created"] == 1
    assert summary["attempts"][0]["refactor_target"] == "converge the splines"
    assert summary["attempts"][0]["refactor_change_count"] == 1
    assert summary["attempts"][0]["commit_phase"] == "refactor"
    commit_sha = summary["attempts"][0]["commit_sha"]
    assert commit_sha

    run_log = (run_dir / "run.log").read_text(encoding="utf-8")
    assert "[INFO] completed refactor: converge the splines" in run_log
    assert f"[INFO] created commit {commit_sha}" in run_log

    output = capsys.readouterr().out
    assert "[INFO] completed refactor: converge the splines" in output
    assert f"Tests passed. Commit: {commit_sha}" in output

    commit_subject = continuous_refactoring.run_command(
        ["git", "log", "-1", "--format=%s"],
        cwd=repo_root,
    ).stdout.strip()
    assert commit_subject == "continuous refactor: attempt 1"
    assert (repo_root / "README.md").read_text(encoding="utf-8") == "seed\nrefactor\n"
