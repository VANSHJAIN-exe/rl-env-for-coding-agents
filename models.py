"""
OpenEnv Typed Models for PatchEditEnv.
Action, Observation, State — all Pydantic v2.
"""
from typing import Optional
from pydantic import BaseModel, Field


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
    last_reward: float = Field(0.0, description="Reward from the previous step.")
    attempts_remaining: int = Field(..., description="Remaining patch attempts before episode ends.")
    message: str = Field("", description="Human-readable status message.")


class PatchState(BaseModel):
    """Internal episode state returned by /state."""
    episode_id: str
    task_id: str
    step_count: int
    done: bool
    total_reward: float
    best_score: float