from __future__ import annotations

from typing import Literal, TypeAlias

MultihostArtifactsType: TypeAlias = Literal["test"]
MultihostArtifactsMode: TypeAlias = Literal["never", "on-failure", "always"]
MultihostOutcome: TypeAlias = Literal["passed", "failed", "skipped", "error", "unknown"]
