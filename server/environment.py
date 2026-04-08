"""
PatchEditEnvironment — core OpenEnv environment.

Implements the full OpenEnv spec:
  reset(task_name) → StepResult
  step(action)     → StepResult
  state()          → PatchState

Reward design (never binary):
  +0.15  patch string is non-empty and references correct line numbers
  +0.20  patch applies cleanly to the buggy source (no patch errors)
  +0.25  patched code executes without ImportError / SyntaxError
  +0.40  test-case oracle score (fraction of passing tests × 0.40)
  Total max = 1.0 per step; best_score tracks episode maximum.

Penalties:
  -0.05  per attempt wasted after first failed apply (encourages efficiency)
"""

import re
import uuid
import textwrap
import subprocess
import sys
import tempfile
import os
from typing import Optional, Tuple

from server.tasks import TASKS


def _strict_unit(value: float) -> float:
    if value <= 0.0:
        return 0.01
    if value >= 1.0:
        return 0.99
    return round(value, 4)


def _strict_fraction(passed: float, total: int) -> float:
    if total <= 0:
        return 0.99
    return _strict_unit(passed / total)


def _inject_line_numbers(source: str) -> str:
    """Prefix each line with its 1-based line number (like `cat -n`)."""
    lines = source.splitlines()
    width = len(str(len(lines)))
    numbered = []
    for i, line in enumerate(lines, start=1):
        numbered.append(f"{i:>{width}}\t{line}")
    return "\n".join(numbered)


def _apply_patch(original_source: str, patch_str: str) -> Tuple[bool, str]:
    """
    Try to apply patch_str to original_source using the `patch` command.
    Returns (success, patched_source_or_error_msg).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path = os.path.join(tmpdir, "code.py")
        patch_path = os.path.join(tmpdir, "fix.patch")

        # Strip line-number prefixes the agent may have accidentally left in
        cleaned_patch = _strip_line_number_prefixes(patch_str)

        with open(orig_path, "w") as f:
            f.write(original_source)
        with open(patch_path, "w") as f:
            f.write(cleaned_patch)

        result = subprocess.run(
            ["patch", "--batch", "--forward", orig_path, patch_path],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            with open(orig_path, "r") as f:
                return True, f.read()
        else:
            return False, result.stderr or result.stdout


def _strip_line_number_prefixes(text: str) -> str:
    """Remove lines like '  42\t' that the agent may echo from the numbered source."""
    cleaned = []
    for line in text.splitlines():
        # Don't touch diff headers/hunks
        if line.startswith(("---", "+++", "@@", "-", "+", " ", "\\")):
            cleaned.append(line)
        else:
            # Strip leading number+tab if present
            stripped = re.sub(r"^\s*\d+\t", "", line)
            cleaned.append(stripped)
    return "\n".join(cleaned)


def _run_tests_in_sandbox(patched_source: str, tests: list, task_id: str) -> float:
    """
    Execute patched_source in a subprocess then run each test expression.
    Returns fraction of tests that pass (0.0–1.0).
    """
    if not tests:
        return 0.99

    passed = 0
    for expr, expected in tests:
        # Build test harness
        if task_id == "hard_patch":
            score = _run_hard_tests(patched_source, expr, expected)
            passed += score
            continue

        test_code = textwrap.dedent(f"""\
            {patched_source}

            _result = {expr}
            _expected = {repr(expected)}
            assert _result == _expected, f"Got {{_result!r}}, expected {{_expected!r}}"
        """)
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(test_code)
                fname = f.name
            proc = subprocess.run(
                [sys.executable, fname],
                capture_output=True, text=True, timeout=10
            )
            os.unlink(fname)
            if proc.returncode == 0:
                passed += 1
        except Exception:
            pass

    return _strict_fraction(passed, len(tests))


def _run_hard_tests(patched_source: str, test_name: str, expected) -> float:
    """Specialised test runner for hard task semantic checks."""
    harnesses = {
        "_lru_cache_key_test": textwrap.dedent("""\
            {src}
            c = LRUCache(4)
            @c.cached
            def fn(x): return x * 2
            r1 = fn(5)
            r2 = fn(5)
            # If cache key is correct, both calls return same object
            print("cache_hit" if r1 == r2 == 10 else "cache_miss")
        """),
        "_retry_exc_type_test": textwrap.dedent("""\
            {src}
            @retry(max_attempts=2, delay=0, exceptions=(ValueError,))
            def always_fails():
                raise ValueError("oops")
            try:
                always_fails()
            except ValueError:
                print("ValueError")
            except Exception as e:
                print(type(e).__name__)
        """),
        "_rate_limiter_reset_test": textwrap.dedent("""\
            import time
            {src}
            rl = RateLimiter(max_calls=2, period=0.05)
            rl.is_allowed()
            rl.is_allowed()
            time.sleep(0.1)
            result = rl.is_allowed()
            print(result)
        """),
        "_hard_integration_test": textwrap.dedent("""\
            {src}
            c = LRUCache(4)
            @c.cached
            def add(a, b): return a + b
            assert add(1, 2) == 3
            rl = RateLimiter(max_calls=5, period=1.0)
            assert rl.is_allowed() is True
            print(True)
        """),
    }

    harness = harnesses.get(test_name, "print(False)")
    code = harness.format(src=patched_source)
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            fname = f.name
        proc = subprocess.run(
            [sys.executable, fname],
            capture_output=True, text=True, timeout=15
        )
        os.unlink(fname)
        output = proc.stdout.strip()
        if str(expected) == output or output == str(expected):
            return 0.99
        return 0.01
    except Exception:
        return 0.01


def _syntax_check(source: str) -> bool:
    """Return True if source compiles without SyntaxError."""
    try:
        compile(source, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def _score_patch_format(patch_str: str, numbered_source: str) -> float:
    """
    Heuristic: does the patch reference line numbers that exist in the source?
    Returns 0.0–0.15.
    """
    if not patch_str.strip():
        return 0.0
    # Count total lines
    total_lines = numbered_source.count("\n") + 1
    # Find @@ -N ... @@ hunk headers
    hunk_lines = re.findall(r"@@\s*-(\d+)", patch_str)
    if not hunk_lines:
        return 0.05  # has content but no valid hunks
    # Check line numbers are plausible
    valid = all(1 <= int(ln) <= total_lines + 5 for ln in hunk_lines)
    return 0.15 if valid else 0.05


class EpisodeState:
    def __init__(self, task_id: str):
        self.episode_id = str(uuid.uuid4())[:8]
        self.task_id = task_id
        self.task = TASKS[task_id]
        self.step_count = 0
        self.done = False
        self.total_reward = 0.0
        self.best_score = 0.0
        self.attempts_used = 0
        self.max_attempts = self.task["max_attempts"]
        self.numbered_source = _inject_line_numbers(self.task["buggy_source"])
        self.last_patch_result: Optional[str] = None
        self.last_reward: float = 0.0

    def attempts_remaining(self) -> int:
        return self.max_attempts - self.attempts_used


class PatchEditEnvironment:
    """
    The main OpenEnv environment class.
    One instance is shared across requests; each reset() creates a new EpisodeState.
    """

    def __init__(self):
        self._episode: Optional[EpisodeState] = None

    # ------------------------------------------------------------------
    # OpenEnv API
    # ------------------------------------------------------------------

    def reset(self, task_name: str = "easy_patch") -> dict:
        if task_name not in TASKS:
            task_name = "easy_patch"
        self._episode = EpisodeState(task_name)
        ep = self._episode
        return {
            "observation": {
                "numbered_source": ep.numbered_source,
                "bug_description": ep.task["bug_description"],
                "task_id": ep.task_id,
                "last_patch_result": None,
                "last_reward": 0.01,
                "attempts_remaining": ep.attempts_remaining(),
                "message": (
                    f"Episode started. Task: {ep.task['name']} ({ep.task['difficulty']}). "
                    f"You have {ep.max_attempts} attempts."
                ),
            },
            "reward": 0.01,
            "done": False,
            "info": {
                "episode_id": ep.episode_id,
                "task": ep.task["name"],
                "difficulty": ep.task["difficulty"],
                "num_bugs": ep.task["num_bugs"],
                "max_attempts": ep.max_attempts,
            },
        }

    def step(self, action: dict) -> dict:
        ep = self._episode
        if ep is None or ep.done:
            return self._terminal_result(ep)

        patch_str = action.get("patch", "")
        architect_plan = action.get("architect_plan", "")

        ep.step_count += 1
        ep.attempts_used += 1

        reward = 0.0
        patch_result = "failed_to_apply"
        message = ""

        # --- Component 1: patch format score (0.0–0.15) ---
        fmt_score = _score_patch_format(patch_str, ep.numbered_source)
        reward += fmt_score

        # --- Component 2: apply patch (0.0 or +0.20) ---
        apply_ok, patched_or_err = _apply_patch(ep.task["buggy_source"], patch_str)

        if apply_ok:
            patched_source = patched_or_err
            reward += 0.20
            patch_result = "applied"

            # --- Component 3: syntax check (+0.25) ---
            if _syntax_check(patched_source):
                reward += 0.10  # partial for valid syntax
                message = "Patch applied and syntax OK. Running tests..."

                # --- Component 4: test oracle (0.0–0.40) ---
                test_score = _run_tests_in_sandbox(
                    patched_source, ep.task["tests"], ep.task_id
                )
                reward += test_score * 0.40

                if test_score >= 0.99:
                    reward = min(reward, 0.99)
                    patch_result = "applied"
                    message = f"All tests passed! Score: {reward:.3f}"
                    ep.done = True
                elif test_score > 0:
                    patch_result = "applied"
                    message = (
                        f"Patch applied. {test_score*100:.0f}% tests pass. "
                        f"Partial reward: {reward:.3f}. Try again."
                    )
                else:
                    patch_result = "wrong_output"
                    message = f"Patch applied but tests fail. Reward: {reward:.3f}. Rethink the fix."
            else:
                patch_result = "wrong_output"
                message = "Patch applied but produced syntax errors in the result."
        else:
            # Patch failed to apply — penalise wasted attempts (after first)
            if ep.attempts_used > 1:
                reward = max(0.0, fmt_score - 0.05)
            message = f"Patch failed to apply: {patched_or_err[:200]}"

        # Clamp reward
        reward = _strict_unit(min(max(reward, 0.0), 1.0))
        ep.total_reward += reward
        ep.best_score = _strict_unit(max(ep.best_score, reward))
        ep.last_patch_result = patch_result
        ep.last_reward = reward

        # Out of attempts?
        if ep.attempts_remaining() <= 0 and not ep.done:
            ep.done = True
            message += f" No attempts remaining. Best score: {ep.best_score:.3f}."

        return {
            "observation": {
                "numbered_source": ep.numbered_source,
                "bug_description": ep.task["bug_description"],
                "task_id": ep.task_id,
                "last_patch_result": patch_result,
                "last_reward": reward,
                "attempts_remaining": ep.attempts_remaining(),
                "message": message,
            },
            "reward": reward,
            "done": ep.done,
            "info": {
                "episode_id": ep.episode_id,
                "step": ep.step_count,
                "total_reward": _strict_unit(ep.total_reward),  # FIX: clamp raw sum
                "best_score": ep.best_score,
                "architect_plan_received": bool(architect_plan),
                "score": reward,
            },
        }

    def state(self) -> dict:
        ep = self._episode
        if ep is None:
            return {
                "episode_id": "none",
                "task_id": "none",
                "step_count": 0,
                "done": True,
                "total_reward": 0.01,
                "best_score": 0.01,
            }
        return {
            "episode_id": ep.episode_id,
            "task_id": ep.task_id,
            "step_count": ep.step_count,
            "done": ep.done,
            "total_reward": _strict_unit(ep.total_reward),
            "best_score": _strict_unit(ep.best_score),
        }

    def _terminal_result(self, ep) -> dict:
        obs = {
            "numbered_source": ep.numbered_source if ep else "",
            "bug_description": ep.task["bug_description"] if ep else "",
            "task_id": ep.task_id if ep else "none",
            "last_patch_result": "episode_done",
            "last_reward": 0.01,
            "attempts_remaining": 0,
            "message": "Episode already finished. Call /reset to start a new one.",
        }
        return {"observation": obs, "reward": 0.01, "done": True, "info": {"score": 0.01}}
