from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from typing import Any

try:
    from .config import CORRECTNESS_TIMEOUT_SECONDS
except ImportError:
    from config import CORRECTNESS_TIMEOUT_SECONDS


CORRECTNESS_CHILD_SCRIPT = textwrap.dedent(
    """
    import json
    import traceback
    import sys

    payload = json.load(sys.stdin)
    code = payload["code"]
    test_code = payload["test_code"]
    entry_point = payload["entry_point"]

    result = {
        "passed": False,
        "status": "unknown",
        "error_type": None,
        "error_message": None,
        "traceback": None,
    }

    namespace = {}

    try:
        compile(code, "<candidate>", "exec")
    except SyntaxError as exc:
        result.update(
            {
                "status": "syntax_error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        print(json.dumps(result))
        raise SystemExit(0)

    try:
        exec(code, namespace)
        exec(test_code, namespace)
        candidate = namespace.get(entry_point)
        if candidate is None:
            raise NameError(f"Entry point '{entry_point}' was not defined by candidate code.")

        check = namespace.get("check")
        if check is None:
            test_check = namespace.get("test_check")
            if callable(test_check):
                test_check()
            else:
                raise NameError("HumanEval test harness did not define check(candidate).")
        else:
            check(candidate)

        result.update(
            {
                "passed": True,
                "status": "passed",
            }
        )
    except BaseException as exc:
        result.update(
            {
                "status": "runtime_error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )

    print(json.dumps(result))
    """
).strip()


def evaluate_code_correctness(
    *,
    code: str,
    test_code: str,
    entry_point: str,
    timeout_seconds: float = CORRECTNESS_TIMEOUT_SECONDS,
    python_executable: str | None = None,
) -> dict[str, Any]:
    if not code.strip():
        return {
            "passed": False,
            "status": "missing_code",
            "error_type": None,
            "error_message": "No candidate code was available for evaluation.",
            "traceback": None,
            "duration_seconds": 0.0,
        }

    payload = json.dumps(
        {
            "code": code,
            "test_code": test_code,
            "entry_point": entry_point,
        }
    )
    started_at = time.perf_counter()

    try:
        completed = subprocess.run(
            [python_executable or sys.executable, "-c", CORRECTNESS_CHILD_SCRIPT],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "status": "timeout",
            "error_type": "TimeoutExpired",
            "error_message": f"Candidate exceeded {timeout_seconds:.2f}s correctness timeout.",
            "traceback": None,
            "duration_seconds": round(time.perf_counter() - started_at, 4),
        }

    duration_seconds = round(time.perf_counter() - started_at, 4)
    stdout = completed.stdout.strip()

    if not stdout:
        return {
            "passed": False,
            "status": "harness_error",
            "error_type": "EmptyHarnessOutput",
            "error_message": completed.stderr.strip() or "Correctness harness produced no stdout.",
            "traceback": None,
            "duration_seconds": duration_seconds,
        }

    try:
        result = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {
            "passed": False,
            "status": "harness_error",
            "error_type": type(exc).__name__,
            "error_message": f"Could not parse correctness harness output: {exc}",
            "traceback": stdout,
            "duration_seconds": duration_seconds,
        }

    result["duration_seconds"] = duration_seconds
    return result
