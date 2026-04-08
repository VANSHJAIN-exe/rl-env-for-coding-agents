"""
PatchEditEnvironment — core OpenEnv environment.
Implements the full OpenEnv spec with rewards strictly in (0, 1).
"""

import re
import uuid
import textwrap
import subprocess
import sys
import tempfile
import os
from typing import Optional, Tuple

# Import TASKS from your local server module
try:
    from server.tasks import TASKS
except ImportError:
    # Minimal fallback for standalone testing
    TASKS = {
        "easy_patch": {
            "name": "Easy Patch",
            "difficulty": "easy",
            "num_bugs": 1,
            "max_attempts": 5,
            "buggy_source": "def add(a, b):\n    return a - b",
            "bug_description": "Function subtracts instead of adding.",
            "tests": [("add(1, 2)", 3)]
        }
    }

def _strict_unit(value: float) -> float:
    """Forces score to be strictly within (0, 1) range."""
    if value <= 0.0:
        return 0.01
    if value >= 1.0:
        return 0.99
    return round(value, 4)

def _strict_fraction(passed: float, total: int) -> float:
    """Clamps test fractions to strict (0, 1) bounds."""
    if total <= 0:
        return 0.99
    return _strict_unit(passed / total)

def _inject_line_numbers(source: str) -> str:
    """Prefix each line with its 1-based line number."""
    lines = source.splitlines()
    width = len(str(len(lines)))
    numbered = []
    for i, line in enumerate(lines, start=1):
        numbered.append(f"{i:>{width}}\t{line}")
    return "\n".join(numbered)

def _strip_line_number_prefixes(text: str) -> str:
    """Remove line-number echoes from agent output before patching."""
    cleaned = []
    for line in text.splitlines():
        if line.startswith(("---", "+++", "@@", "-", "+", " ", "\\")):
            cleaned.append(line)
        else:
            stripped = re.sub(r"^\s*\d+\t", "", line)
            cleaned.append(stripped)
    return "\n".join(cleaned)

def _apply_patch(original_source: str, patch_str: str) -> Tuple[bool, str]:
    """Applies patch via CLI patch utility."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path = os.path.join(tmpdir, "code.py")
        patch_path = os.path.join(tmpdir, "fix.patch")
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

def _run_tests_in_sandbox(patched_source: str, tests: list, task_id: str) -> float:
    """Executes code and checks test expressions."""
    if not tests:
        return 0.99

    passed = 0
    for expr, expected in tests:
        if task_id == "hard_patch":
            passed += _run_hard_tests(patched_source, expr, expected)
            continue

        test_code = textwrap.dedent(f"""\
            {patched_source}
            _result = {expr}
            _expected = {repr(expected)}
            assert _result == _expected
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
    """Specialized test logic for complex tasks."""
    harnesses = {
        "_lru_cache_key_test": "{src}\nc = LRUCache(4)\n@c.cached\ndef fn(x): return x*2\nprint('cache_hit' if fn(5)==fn(5)==10 else 'cache_miss')",
        "_retry_exc_type_test": "{src}\n@retry(max_attempts=2, exceptions=(ValueError,))\ndef f(): raise ValueError('oops')\ntry: f()\nexcept ValueError: print('ValueError')",
    }
    harness = harnesses.get(test_name, "print(False)")
    code = harness.format(src=patched_source)
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            fname = f.name
        proc = subprocess.run([sys.executable, fname], capture_output=True, text=True, timeout=5)
        os.unlink(fname)
        return 1.0 if str(expected) == proc.stdout.strip() else 0.0
    except:
        return 0.0

def _syntax_check(source: str) -> bool:
    try:
        compile(source, "<string>", "exec")
        return True
    except:
        return False

def _score_patch_format(patch_str: str, numbered_source: str) -> float:
    if not patch_str.strip(): return 0.01
    total_lines = numbered_source.count("\n") + 1
    hunk_lines = re.findall(r"@@\s*-(\d+)", patch_str)
    if not hunk_lines: return 0.05
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
        self.best_score = 0.01
        self.attempts_used = 0
        self.max_attempts = self.task["max_attempts"]
        self.numbered_source = _inject_line_numbers(self.task["buggy_source"])
        self.last_patch_result: Optional[str] = None
        self.last_reward: float = 0.01

class PatchEditEnvironment:
    def __init__(self):
        self._episode: Optional[EpisodeState] = None

    def reset(self, task_name: str = "easy_patch") -> dict:
        if task_name not in TASKS: task_name = "easy_patch"
        self._episode = EpisodeState(task_name)
        ep = self._episode
        res_reward = _strict_unit(0.0)
        return {
            "observation": {
                "numbered_source": ep.numbered_source,
                "bug_description": ep.task["bug_description"],
                "task_id": ep.task_id,
                "last_patch_result": None,
                "last_reward": res_reward,
                "attempts_remaining": ep.attempts_remaining(),
                "message": f"Task: {ep.task['name']}. {ep.max_attempts} attempts allowed.",
            },
            "reward": res_reward,
            "done": False,
            "info": {"episode_id": ep.episode_id, "task": ep.task["name"]},
        }

    def step(self, action: dict) -> dict:
        ep = self._episode
        if ep is None or ep.done: return self._terminal_result(ep)

        patch_str = action.get("patch", "")
        ep.step_count += 1
        ep.attempts_used += 1

        reward = 0.0
        patch_result = "failed_to_apply"
        message = ""

        # 1. Format
        reward += _score_patch_format(patch_str, ep.numbered_source)

        # 2. Apply
        ok, patched = _apply_patch(ep.task["buggy_source"], patch_str)
        if ok:
            reward += 0.20
            patch_result = "applied"
            # 3. Syntax
            if _syntax_check(patched):
                reward += 0.10
                # 4. Tests
                test_score = _run_tests_in_sandbox(patched, ep.task["tests"], ep.task_id)
                reward += (test_score * 0.40)
                if test_score >= 0.99:
                    message = "All tests passed!"
                    ep.done = True
                else:
                    message = f"Applied. {test_score*100:.0f}% pass."
            else:
                message = "Syntax error in patch."
        else:
            if ep.attempts_used > 1: reward -= 0.05
            message = f"Patch error: {patched[:50]}"

        final_reward = _strict_unit(reward)
        ep.total_reward += final_reward
        ep.best_score = _strict_unit(max(ep.best_score, final_reward))
        ep.last_patch_result = patch_result
        ep.last_reward = final_reward

        if ep.attempts_remaining() <= 0: ep.done = True

        return {
            "observation": {
                "numbered_source": ep.numbered_source,
                "bug_description": ep.task["bug_description"],
                "task_id": ep.task_id,
                "last_patch_result": patch_result,
                "last_reward": final_reward,
                "attempts_remaining": ep.attempts_remaining(),
                "message": message,
            },
            "reward": final_reward,
            "done": ep.done,
            "info": {"step": ep.step_count, "best_score": ep.best_score},
        }

    def state(self) -> dict:
        ep = self._episode
        if not ep: return {"total_reward": 0.01, "best_score": 0.01, "done": True}
        return {
            "episode_id": ep.episode_id,
            "step_count": ep.step_count,
            "done": ep.done,
            "total_reward": _strict_unit(ep.total_reward),
            "best_score": ep.best_score,
        }

    def _terminal_result(self, ep) -> dict:
        r = 0.01
        return {
            "observation": {"last_patch_result": "done", "last_reward": r, "message": "Finished."},
            "reward": r, "done": True, "info": {"score": r}
        }
