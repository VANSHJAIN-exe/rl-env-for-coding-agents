"""
OpenEnv Typed Models for PatchEditEnv.
Action, Observation, State — all Pydantic v2.
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


def _clamp(v: float) -> float:
    """Ensure value is strictly within (0, 1) — never 0.0 or 1.0."""
    if v <= 0.0:
        return 0.01
    if v >= 1.0:
        return 0.99
    return round(v, 4)


class PatchAction(BaseModel):
    """
    The action an agent takes: a unified diff patch against the numbered source.
    """
    patch: str = Field(
        ...,
        description=(
            "A unified diff patch string using line numbers injected into the source. "
            "Format: '--- a/code.py\\n+++ b/code.py\\n@@ -L,N +L,N @@\\n-old line\\n+new line'"
        ),
    )
    architect_plan: Optional[str] = Field(
        None,
        description="Plain-English reasoning about what to change and why (Architect step output).",
    )


class PatchObservation(BaseModel):
    """What the agent observes at each step."""
    numbered_source: str = Field(
        ...,
        description="Full source file with injected line numbers, e.g. '  1\\tdef foo():'.",
    )
    bug_description: str = Field(
        ...,
        description="Natural-language description of the bug the agent must fix.",
    )
    task_id: str = Field(..., description="Task identifier: easy_patch / medium_patch / hard_patch.")
    last_patch_result: Optional[str] = Field(
        None,
        description="Feedback from previous attempt: applied | failed_to_apply | wrong_output | None.",
    )
    last_reward: float = Field(0.01, description="Reward from the previous step.")  # FIX: default 0.0 → 0.01
    attempts_remaining: int = Field(..., description="Remaining patch attempts before episode ends.")
    message: str = Field("", description="Human-readable status message.")

    @field_validator("last_reward", mode="before")
    @classmethod
    def clamp_last_reward(cls, v: float) -> float:
        return _clamp(float(v))


class PatchState(BaseModel):
    """Internal episode state returned by /state."""
    episode_id: str
    task_id: str
    step_count: int
    done: bool
    total_reward: float
    best_score: float

    @field_validator("total_reward", "best_score", mode="before")
    @classmethod
    def clamp_scores(cls, v: float) -> float:
        return _clamp(float(v))
