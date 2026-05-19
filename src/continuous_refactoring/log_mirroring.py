from __future__ import annotations

from dataclasses import dataclass

__all__ = ["LogMirroring"]


@dataclass(frozen=True)
class LogMirroring:
    agent: bool = False
    command: bool = False
