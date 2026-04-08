"""
Task definitions for PatchEditEnv.

Each task has:
  - id, name, description, difficulty
  - buggy_source: the broken Python code
  - bug_description: what to tell the agent
  - fixed_source: ground-truth fix (used internally by grader)
  - test_cases: list of (args, expected_output) tuples
  - max_attempts: how many patch tries per episode
"""

from typing import List, Tuple, Any, Dict

# ---------------------------------------------------------------------------
# TASK 1 — EASY
# Single off-by-one bug in a small 28-line file.
# Agent must change `<` to `<=` on one line.
# ---------------------------------------------------------------------------

EASY_BUGGY = '''\
def binary_search(arr, target):
    """Return index of target in sorted arr, or -1 if not found."""
    low = 0
    high = len(arr) - 1
    while low < high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1


def find_items(inventory, query_items):
    """Return dict mapping each query item to its index in inventory."""
    results = {}
    for item in query_items:
        idx = binary_search(inventory, item)
        results[item] = idx
    return results


if __name__ == "__main__":
    inv = [1, 3, 5, 7, 9, 11]
    print(find_items(inv, [1, 5, 11, 4]))
'''

EASY_FIXED = '''\
def binary_search(arr, target):
    """Return index of target in sorted arr, or -1 if not found."""
    low = 0
    high = len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1


def find_items(inventory, query_items):
    """Return dict mapping each query item to its index in inventory."""
    results = {}
    for item in query_items:
        idx = binary_search(inventory, item)
        results[item] = idx
    return results


if __name__ == "__main__":
    inv = [1, 3, 5, 7, 9, 11]
    print(find_items(inv, [1, 5, 11, 4]))
'''

EASY_BUG_DESC = (
    "The function `binary_search` never finds elements at the last position of the search window. "
    "When `low == high`, the loop exits prematurely before checking that position. "
    "Fix the loop condition so elements at the boundary are not missed."
)

EASY_TESTS: List[Tuple] = [
    # (function_call_string, expected_result)
    ("binary_search([1,3,5,7,9,11], 11)", 5),
    ("binary_search([1,3,5,7,9,11], 1)", 0),
    ("binary_search([1,3,5,7,9,11], 5)", 2),
    ("binary_search([1,3,5,7,9,11], 4)", -1),
    ("binary_search([2], 2)", 0),
]

# ---------------------------------------------------------------------------
# TASK 2 — MEDIUM
# Logic bug in a data-processing pipeline (~70 lines).
# Agent must fix a wrong aggregation: using `append` instead of `extend`
# AND a wrong initial value for running_total (starts at 1 instead of 0).
# Two hunks in the patch.
# ---------------------------------------------------------------------------

MEDIUM_BUGGY = '''\
"""Order processing pipeline for a fulfilment centre."""
from typing import List, Dict, Any


def parse_order(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalise an incoming order dict."""
    if "items" not in raw or not isinstance(raw["items"], list):
        raise ValueError("Order must have an 'items' list")
    if "order_id" not in raw:
        raise ValueError("Order must have an 'order_id'")
    return {
        "order_id": str(raw["order_id"]),
        "items": raw["items"],
        "priority": raw.get("priority", "normal"),
    }


def compute_total(items: List[Dict[str, Any]]) -> float:
    """Sum price * quantity for all line items."""
    running_total = 1          # BUG: should be 0
    for item in items:
        price = float(item.get("price", 0))
        qty = int(item.get("qty", 1))
        running_total += price * qty
    return running_total


def batch_process(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process a batch of raw orders. Return summary."""
    processed = []
    failed = []
    all_items = []

    for raw in orders:
        try:
            order = parse_order(raw)
            total = compute_total(order["items"])
            order["total"] = total
            processed.append(order)
            all_items.append(order["items"])   # BUG: should be extend
        except ValueError as e:
            failed.append({"raw": raw, "error": str(e)})

    return {
        "processed": processed,
        "failed": failed,
        "all_items": all_items,
        "batch_total": sum(o["total"] for o in processed),
    }


def top_items_by_value(orders: List[Dict[str, Any]], top_n: int = 3) -> List[str]:
    """Return top_n item names ranked by total value (price * qty)."""
    scores: Dict[str, float] = {}
    for order in orders:
        for item in order.get("items", []):
            name = item.get("name", "unknown")
            val = float(item.get("price", 0)) * int(item.get("qty", 1))
            scores[name] = scores.get(name, 0) + val
    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    return ranked[:top_n]


if __name__ == "__main__":
    sample = [
        {"order_id": 1, "items": [{"name": "bolt", "price": 0.5, "qty": 100}]},
        {"order_id": 2, "items": [{"name": "nut", "price": 0.3, "qty": 200}]},
    ]
    result = batch_process(sample)
    print("Batch total:", result["batch_total"])
    print("All items count:", len(result["all_items"]))
'''

MEDIUM_FIXED = '''\
"""Order processing pipeline for a fulfilment centre."""
from typing import List, Dict, Any


def parse_order(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalise an incoming order dict."""
    if "items" not in raw or not isinstance(raw["items"], list):
        raise ValueError("Order must have an 'items' list")
    if "order_id" not in raw:
        raise ValueError("Order must have an 'order_id'")
    return {
        "order_id": str(raw["order_id"]),
        "items": raw["items"],
        "priority": raw.get("priority", "normal"),
    }


def compute_total(items: List[Dict[str, Any]]) -> float:
    """Sum price * quantity for all line items."""
    running_total = 0
    for item in items:
        price = float(item.get("price", 0))
        qty = int(item.get("qty", 1))
        running_total += price * qty
    return running_total


def batch_process(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process a batch of raw orders. Return summary."""
    processed = []
    failed = []
    all_items = []

    for raw in orders:
        try:
            order = parse_order(raw)
            total = compute_total(order["items"])
            order["total"] = total
            processed.append(order)
            all_items.extend(order["items"])
        except ValueError as e:
            failed.append({"raw": raw, "error": str(e)})

    return {
        "processed": processed,
        "failed": failed,
        "all_items": all_items,
        "batch_total": sum(o["total"] for o in processed),
    }


def top_items_by_value(orders: List[Dict[str, Any]], top_n: int = 3) -> List[str]:
    """Return top_n item names ranked by total value (price * qty)."""
    scores: Dict[str, float] = {}
    for order in orders:
        for item in order.get("items", []):
            name = item.get("name", "unknown")
            val = float(item.get("price", 0)) * int(item.get("qty", 1))
            scores[name] = scores.get(name, 0) + val
    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    return ranked[:top_n]


if __name__ == "__main__":
    sample = [
        {"order_id": 1, "items": [{"name": "bolt", "price": 0.5, "qty": 100}]},
        {"order_id": 2, "items": [{"name": "nut", "price": 0.3, "qty": 200}]},
    ]
    result = batch_process(sample)
    print("Batch total:", result["batch_total"])
    print("All items count:", len(result["all_items"]))
'''

MEDIUM_BUG_DESC = (
    "This order-processing pipeline has two bugs. "
    "First, `compute_total` initialises `running_total` to 1 instead of 0, "
    "causing every order total to be inflated by 1. "
    "Second, `batch_process` uses `all_items.append(order['items'])` instead of "
    "`all_items.extend(order['items'])`, so `all_items` becomes a list-of-lists "
    "instead of a flat list of individual items. Fix both bugs."
)

MEDIUM_TESTS: List[Tuple] = [
    # compute_total tests
    ("compute_total([{'price': 10, 'qty': 2}, {'price': 5, 'qty': 1}])", 25.0),
    ("compute_total([])", 0.0),
    ("compute_total([{'price': 1, 'qty': 1}])", 1.0),
    # batch_process all_items flat list test
    ("len(batch_process([{'order_id':1,'items':[{'name':'x','price':1,'qty':1},{'name':'y','price':2,'qty':1}]},{'order_id':2,'items':[{'name':'z','price':3,'qty':1}]}])['all_items'])", 3),
    # batch total
    ("batch_process([{'order_id':1,'items':[{'name':'a','price':5,'qty':2}]}])['batch_total']", 10.0),
]

# ---------------------------------------------------------------------------
# TASK 3 — HARD
# Multi-hunk bug in a caching + retry utility (~120 lines).
# Bugs: (1) LRU cache key uses id() instead of value — breaks across calls.
#       (2) Retry decorator swallows the original exception type.
#       (3) rate_limit counter never resets — always blocks after first window.
# Three separate hunks required.
# ---------------------------------------------------------------------------

HARD_BUGGY = '''\
"""
Resilience utilities: LRU cache, retry decorator, and rate limiter.
Used in production API gateway to protect downstream services.
"""
import time
import functools
from typing import Any, Callable, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Minimal LRU Cache
# ---------------------------------------------------------------------------

class LRUCache:
    """Fixed-capacity LRU cache backed by a dict + doubly-linked list (via OrderedDict trick)."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache: Dict[Any, Any] = {}
        self._order: list = []

    def get(self, key: Any) -> Optional[Any]:
        if key not in self._cache:
            return None
        self._order.remove(key)
        self._order.append(key)
        return self._cache[key]

    def put(self, key: Any, value: Any) -> None:
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self.capacity:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = value
        self._order.append(key)

    def cached(self, fn: Callable) -> Callable:
        """Decorator: cache fn results in this LRU instance."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (id(args), id(kwargs))   # BUG: id() is address, not value
            result = self.get(key)
            if result is not None:
                return result
            result = fn(*args, **kwargs)
            self.put(key, result)
            return result
        return wrapper


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def retry(max_attempts: int = 3, delay: float = 0.1, exceptions: Tuple = (Exception,)):
    """
    Retry a function up to max_attempts times on specified exceptions.
    Re-raises the last exception if all attempts fail.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
            raise RuntimeError(f"Failed after {max_attempts} attempts") from last_exc  # BUG: should re-raise last_exc directly
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Simple fixed-window rate limiter.
    Allows up to `max_calls` calls per `period` seconds.
    """

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self._window_start: float = time.time()
        self._call_count: int = 0

    def is_allowed(self) -> bool:
        now = time.time()
        if now - self._window_start >= self.period:
            self._window_start = now
            # BUG: forgot to reset self._call_count = 0 here
        if self._call_count < self.max_calls:
            self._call_count += 1
            return True
        return False

    def throttle(self, fn: Callable) -> Callable:
        """Decorator: raise RuntimeError if rate limit exceeded."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not self.is_allowed():
                raise RuntimeError("Rate limit exceeded")
            return fn(*args, **kwargs)
        return wrapper


# ---------------------------------------------------------------------------
# Combined usage example
# ---------------------------------------------------------------------------

_cache = LRUCache(capacity=128)
_limiter = RateLimiter(max_calls=10, period=1.0)


@_limiter.throttle
@_cache.cached
@retry(max_attempts=3, delay=0.05)
def fetch_exchange_rate(base: str, quote: str) -> float:
    """Simulate fetching an exchange rate (replace with real API call)."""
    # Deterministic stub: just return len ratio for testing
    return len(base) / max(len(quote), 1)


if __name__ == "__main__":
    print(fetch_exchange_rate("USD", "EUR"))
    print(fetch_exchange_rate("USD", "EUR"))  # should hit cache
'''

HARD_FIXED = '''\
"""
Resilience utilities: LRU cache, retry decorator, and rate limiter.
Used in production API gateway to protect downstream services.
"""
import time
import functools
from typing import Any, Callable, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Minimal LRU Cache
# ---------------------------------------------------------------------------

class LRUCache:
    """Fixed-capacity LRU cache backed by a dict + doubly-linked list (via OrderedDict trick)."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache: Dict[Any, Any] = {}
        self._order: list = []

    def get(self, key: Any) -> Optional[Any]:
        if key not in self._cache:
            return None
        self._order.remove(key)
        self._order.append(key)
        return self._cache[key]

    def put(self, key: Any, value: Any) -> None:
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self.capacity:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = value
        self._order.append(key)

    def cached(self, fn: Callable) -> Callable:
        """Decorator: cache fn results in this LRU instance."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            result = self.get(key)
            if result is not None:
                return result
            result = fn(*args, **kwargs)
            self.put(key, result)
            return result
        return wrapper


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def retry(max_attempts: int = 3, delay: float = 0.1, exceptions: Tuple = (Exception,)):
    """
    Retry a function up to max_attempts times on specified exceptions.
    Re-raises the last exception if all attempts fail.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Simple fixed-window rate limiter.
    Allows up to `max_calls` calls per `period` seconds.
    """

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self._window_start: float = time.time()
        self._call_count: int = 0

    def is_allowed(self) -> bool:
        now = time.time()
        if now - self._window_start >= self.period:
            self._window_start = now
            self._call_count = 0
        if self._call_count < self.max_calls:
            self._call_count += 1
            return True
        return False

    def throttle(self, fn: Callable) -> Callable:
        """Decorator: raise RuntimeError if rate limit exceeded."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not self.is_allowed():
                raise RuntimeError("Rate limit exceeded")
            return fn(*args, **kwargs)
        return wrapper


# ---------------------------------------------------------------------------
# Combined usage example
# ---------------------------------------------------------------------------

_cache = LRUCache(capacity=128)
_limiter = RateLimiter(max_calls=10, period=1.0)


@_limiter.throttle
@_cache.cached
@retry(max_attempts=3, delay=0.05)
def fetch_exchange_rate(base: str, quote: str) -> float:
    """Simulate fetching an exchange rate (replace with real API call)."""
    return len(base) / max(len(quote), 1)


if __name__ == "__main__":
    print(fetch_exchange_rate("USD", "EUR"))
    print(fetch_exchange_rate("USD", "EUR"))  # should hit cache
'''

HARD_BUG_DESC = (
    "This resilience utility module has three separate bugs across three classes. "
    "\n\n"
    "Bug 1 — LRUCache.cached: The cache key is built using `(id(args), id(kwargs))`. "
    "Python's `id()` returns memory addresses, which are reused across calls. "
    "Two different argument tuples can share the same id, causing cache misses or wrong hits. "
    "Fix: use `(args, tuple(sorted(kwargs.items())))` as the key.\n\n"
    "Bug 2 — retry decorator: On exhaustion it raises `RuntimeError(...)` instead of "
    "re-raising the original exception. This destroys the original exception type, "
    "breaking `except SpecificError` handlers upstream. "
    "Fix: change the final raise to `raise last_exc`.\n\n"
    "Bug 3 — RateLimiter.is_allowed: When a new time window starts, `self._call_count` "
    "is never reset to 0. After the first full window, the limiter blocks all future calls forever. "
    "Fix: add `self._call_count = 0` immediately after `self._window_start = now`."
)

HARD_TESTS: List[Tuple] = [
    # Cache key correctness — same args must hit cache
    ("_lru_cache_key_test", "cache_hit"),
    # Retry preserves exception type
    ("_retry_exc_type_test", "ValueError"),
    # RateLimiter resets after window
    ("_rate_limiter_reset_test", True),
    # compute_total sanity (reuse medium helper for grader variety)
    ("_hard_integration_test", True),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TASKS: Dict[str, Dict] = {
    "easy_patch": {
        "id": "easy_patch",
        "name": "Binary Search Off-By-One",
        "description": "Fix a single off-by-one error in a binary search function.",
        "difficulty": "easy",
        "buggy_source": EASY_BUGGY,
        "fixed_source": EASY_FIXED,
        "bug_description": EASY_BUG_DESC,
        "tests": EASY_TESTS,
        "max_attempts": 5,
        "num_bugs": 1,
    },
    "medium_patch": {
        "id": "medium_patch",
        "name": "Order Pipeline Dual Bug",
        "description": "Fix two bugs in an order-processing pipeline (wrong initial value + wrong list method).",
        "difficulty": "medium",
        "buggy_source": MEDIUM_BUGGY,
        "fixed_source": MEDIUM_FIXED,
        "bug_description": MEDIUM_BUG_DESC,
        "tests": MEDIUM_TESTS,
        "max_attempts": 5,
        "num_bugs": 2,
    },
    "hard_patch": {
        "id": "hard_patch",
        "name": "Resilience Utils Triple Bug",
        "description": "Fix three bugs across LRU cache, retry decorator, and rate limiter.",
        "difficulty": "hard",
        "buggy_source": HARD_BUGGY,
        "fixed_source": HARD_FIXED,
        "bug_description": HARD_BUG_DESC,
        "tests": HARD_TESTS,
        "max_attempts": 7,
        "num_bugs": 3,
    },
}