from __future__ import annotations

import re
from pathlib import Path

from continuous_refactoring.artifacts import CommandCapture


CHOSEN_SCOPE_PATTERN = r"(?:chosen_target|chosen_scope)"
REQUIRED_PREAMBLE = (
    "All changes must keep the project in a state where all tests pass. "
    "Do not finish unless the repository is green after your refactor."
)

TARGET_LINE_PATTERN = re.compile(
    rf"^\s*(?:[-*]\s*)?(?:`|\*\*)?{CHOSEN_SCOPE_PATTERN}"
    rf"(?:`|\*\*)?\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
TARGET_HEADER_PATTERN = re.compile(
    rf"^\s*(?:#+\s*)?(?:`|\*\*)?{CHOSEN_SCOPE_PATTERN}(?:`|\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
SUMMARY_UNKNOWN = "scope unavailable"


def prompt_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compose_refactor_prompt(
    base_prompt: str,
    attempt: int,
    previous_failure: str | None = None,
) -> str:
    sections = [
        f"Attempt {attempt}",
        base_prompt,
        REQUIRED_PREAMBLE,
    ]
    if previous_failure:
        sections.append("Previous attempt failed tests with this output:\n")
        sections.append(previous_failure)
        sections.append(
            "Use this as context only if it helps; do not copy test output into code."
        )
        sections.append(
            "Only fix failures introduced by this refactoring pass. "
            "If a failure is not a direct consequence of your edits, "
            "do not rewrite unrelated code."
        )
    return "\n\n".join(sections)


def normalize_target(text: str) -> str:
    return " ".join(text.strip().strip("`*").split())


def extract_chosen_target(text: str) -> str | None:
    lines = text.splitlines()
    for line in lines:
        match = TARGET_LINE_PATTERN.match(line)
        if match:
            return normalize_target(match.group(1))

    for index, line in enumerate(lines):
        if not TARGET_HEADER_PATTERN.match(line):
            continue
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if stripped.startswith(("-", "*")):
                stripped = stripped[1:].strip()
            return normalize_target(stripped)
    return None


def resolve_phase_target(
    agent_result: CommandCapture,
    last_message_path: Path | None,
) -> str | None:
    if last_message_path is not None and last_message_path.exists():
        target = extract_chosen_target(last_message_path.read_text(encoding="utf-8"))
        if target:
            return target
    return extract_chosen_target(agent_result.stdout) or extract_chosen_target(
        agent_result.stderr
    )


def describe_target(target: str | None) -> str:
    return target or SUMMARY_UNKNOWN
