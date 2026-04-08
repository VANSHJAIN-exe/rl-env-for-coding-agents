"""
FastAPI server for PatchEditEnv.
Exposes the OpenEnv HTTP API: /reset, /step, /state, /health, /tasks
"""
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.environment import PatchEditEnvironment

app = FastAPI(
    title="PatchEditEnv",
    description=(
        "An OpenEnv environment that trains AI agents to perform efficient, "
        "targeted code edits via two-step Architect→Implementer patch generation."
    ),
    version="1.0.0",
)

# One environment instance per server process
_env = PatchEditEnvironment()


# -------------------------------------------------------------------------
# Request schemas
# -------------------------------------------------------------------------

class ResetRequest(BaseModel):
    task_name: Optional[str] = "easy_patch"


class StepRequest(BaseModel):
    patch: str
    architect_plan: Optional[str] = None


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------

@app.get("/health")
def health():
    """Liveness probe — validators ping this first."""
    return {"status": "ok", "env": "PatchEditEnv", "version": "1.0.0"}


@app.get("/tasks")
def list_tasks():
    """Return all available task IDs and metadata."""
    from server.tasks import TASKS
    return {
        tid: {
            "name": t["name"],
            "description": t["description"],
            "difficulty": t["difficulty"],
            "num_bugs": t["num_bugs"],
            "max_attempts": t["max_attempts"],
        }
        for tid, t in TASKS.items()
    }


@app.post("/reset")
def reset(req: Optional[ResetRequest] = None):
    """Start a new episode for the given task."""
    task_name = "easy_patch" if req is None else (req.task_name or "easy_patch")
    result = _env.reset(task_name=task_name)
    return JSONResponse(content=result)


@app.post("/step")
def step(req: StepRequest):
    """Submit a patch. Returns observation, reward, done, info."""
    action = {"patch": req.patch, "architect_plan": req.architect_plan}
    result = _env.step(action)
    return JSONResponse(content=result)


@app.get("/state")
def state():
    """Return current episode state metadata."""
    return JSONResponse(content=_env.state())


@app.get("/")
def root():
    """Root — returns environment info for OpenEnv validators."""
    return {
        "name": "PatchEditEnv",
        "version": "1.0.0",
        "spec_version": "1.0",
        "description": (
            "Trains agents to edit code efficiently using line-numbered source "
            "and two-step Architect→Implementer patch generation."
        ),
        "endpoints": ["/reset", "/step", "/state", "/health", "/tasks"],
    }
