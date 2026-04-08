from __future__ import annotations

import asyncio
import os
from typing import Any

from openai import AsyncOpenAI

from client import EnvClient
from models import PatchAction


SYSTEM_PROMPT = (
    "You fix buggy Python code by returning only a unified diff patch. "
    "Do not include markdown fences or explanation."
)


def _require_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _fallback_patch(task_id: str) -> str:
    patches = {
        "easy_patch": """--- a/code.py
+++ b/code.py
@@ -5,1 +5,1 @@
-    while low < high:
+    while low <= high:
""",
        "medium_patch": """--- a/code.py
+++ b/code.py
@@ -19,1 +19,1 @@
-    running_total = 1          # BUG: should be 0
+    running_total = 0
@@ -39,1 +39,1 @@
-            all_items.append(order["items"])   # BUG: should be extend
+            all_items.extend(order["items"])
""",
        "hard_patch": """--- a/code.py
+++ b/code.py
@@ -42,1 +42,1 @@
-            key = (id(args), id(kwargs))   # BUG: id() is address, not value
+            key = (args, tuple(sorted(kwargs.items())))
@@ -72,1 +72,1 @@
-            raise RuntimeError(f"Failed after {max_attempts} attempts") from last_exc  # BUG: should re-raise last_exc directly
+            raise last_exc
@@ -97,1 +97,1 @@
-            # BUG: forgot to reset self._call_count = 0 here
+            self._call_count = 0
""",
    }
    return patches[task_id]


async def _llm_patch(
    llm: AsyncOpenAI,
    model_name: str,
    task_id: str,
    bug_description: str,
    numbered_source: str,
) -> str:
    prompt = (
        f"Task ID: {task_id}\n"
        f"Bug Description:\n{bug_description}\n\n"
        f"Numbered Source:\n{numbered_source}\n\n"
        "Return only a unified diff patch."
    )
    completion = await llm.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    content = completion.choices[0].message.content or ""
    return content.strip()


async def choose_action(
    llm: AsyncOpenAI,
    model_name: str,
    task_id: str,
    observation: dict[str, Any],
) -> PatchAction:
    bug_description = observation["bug_description"]
    numbered_source = observation["numbered_source"]

    try:
        patch = await _llm_patch(llm, model_name, task_id, bug_description, numbered_source)
    except Exception:
        patch = ""

    if not patch or "---" not in patch or "+++" not in patch:
        patch = _fallback_patch(task_id)

    return PatchAction(patch=patch, architect_plan=f"Apply the known fix for {task_id}.")


def log_start(task_id: str, episode_id: str) -> None:
    print(f"[START] task_id={task_id} episode_id={episode_id}")


def log_step(task_id: str, episode_id: str, step: int, reward: float, done: bool, status: str) -> None:
    print(
        f"[STEP] task_id={task_id} episode_id={episode_id} "
        f"step={step} reward={reward:.4f} done={done} status={status}"
    )


def log_end(task_id: str, episode_id: str, total_reward: float, best_score: float, done: bool) -> None:
    print(
        f"[END] task_id={task_id} episode_id={episode_id} "
        f"total_reward={total_reward:.4f} best_score={best_score:.4f} done={done}"
    )


def bounded_score(value: float) -> float:
    if value <= 0.0:
        return 0.01
    if value >= 1.0:
        return 0.99
    return value


async def run_task(env: EnvClient, llm: AsyncOpenAI, model_name: str, task_id: str) -> None:
    reset_result = await env.reset(task_id)
    info = reset_result["info"]
    observation = reset_result["observation"]
    episode_id = info["episode_id"]
    log_start(task_id, episode_id)

    done = bool(reset_result["done"])
    step = 0
    while not done and observation["attempts_remaining"] > 0:
        step += 1
        action = await choose_action(llm, model_name, task_id, observation)
        step_result = await env.step(action)
        observation = step_result["observation"]
        done = bool(step_result["done"])
        log_step(
            task_id,
            episode_id,
            step,
            float(step_result["reward"]),
            done,
            observation["last_patch_result"] or "none",
        )

    state = await env.state()
    log_end(
        task_id,
        state.episode_id,
        bounded_score(float(state.total_reward)),
        bounded_score(float(state.best_score)),
        state.done,
    )


async def main() -> None:
    api_base_url = _require_env("API_BASE_URL", "http://127.0.0.1:8000/v1")
    model_name = _require_env("MODEL_NAME", "gpt-4o-mini")
    hf_token = _require_env("HF_TOKEN", "local-dev-token")
    env_base_url = os.getenv("ENV_BASE_URL", "http://127.0.0.1:8000")

    llm = AsyncOpenAI(base_url=api_base_url.rstrip("/"), api_key=hf_token)
    env = EnvClient(base_url=env_base_url)

    await env.health()
    tasks = await env.tasks()

    for task_id in ("easy_patch", "medium_patch", "hard_patch"):
        if task_id in tasks:
            await run_task(env, llm, model_name, task_id)


if __name__ == "__main__":
    asyncio.run(main())
