from __future__ import annotations

import json
import random
from typing import Any

try:
    from .config import CURATED_TASKS_PATH, CURATION_SEED, CURATION_SIZE, HUMANEVAL_DATASET
except ImportError:
    from config import CURATED_TASKS_PATH, CURATION_SEED, CURATION_SIZE, HUMANEVAL_DATASET

from datasets import load_dataset


POISON_CONSTRAINTS = [
    "Negative: Do not use any built-in Python standard library functions for this specific logic.",
    "Structural: You must implement this solution using recursion; do not use iterative loops.",
    "Efficiency: You must ensure this algorithm operates in O(n) time complexity or better.",
]


def _score_task_for_constraints(task: dict[str, Any]) -> float:
    prompt = task.get("prompt", "")
    test = task.get("test", "")
    entry_point = task.get("entry_point", "")

    prompt_lower = prompt.lower()
    score = 0.0
    score += min(len(prompt) / 120.0, 12.0)
    score += prompt.count(">>>") * 2.0
    score += prompt.count("\n") * 0.15
    score += 1.5 if entry_point else 0.0
    score += min(len(test) / 400.0, 5.0)

    for keyword in ("list", "string", "array", "number", "integer", "sorted", "palindrome"):
        if keyword in prompt_lower:
            score += 0.75

    for token in ("List[", "Dict[", "Tuple[", "str", "int", "float"):
        if token in prompt:
            score += 0.5

    return round(score, 3)


def _load_humaneval_test_split() -> Any:
    candidate_names = [HUMANEVAL_DATASET, "openai/openai_humaneval"]
    last_error: Exception | None = None

    for dataset_name in dict.fromkeys(candidate_names):
        try:
            return load_dataset(dataset_name, split="test")
        except Exception as exc:  # pragma: no cover - network and HF availability dependent
            last_error = exc

    raise RuntimeError(
        "Unable to download the HumanEval test split. "
        "Tried dataset names: "
        f"{candidate_names}."
    ) from last_error


def _build_balanced_constraint_pool(sample_size: int, seed: int) -> list[str]:
    repeats = (sample_size // len(POISON_CONSTRAINTS)) + 1
    pool = (POISON_CONSTRAINTS * repeats)[:sample_size]
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool


def prepare_curated_dataset(sample_size: int = CURATION_SIZE, seed: int = CURATION_SEED) -> list[dict[str, Any]]:
    dataset = _load_humaneval_test_split()
    scored_tasks = []
    for record in dataset:
        task = dict(record)
        task["selection_score"] = _score_task_for_constraints(task)
        scored_tasks.append(task)

    scored_tasks.sort(key=lambda item: (-item["selection_score"], item["task_id"]))
    curated_records = scored_tasks[: min(sample_size, len(scored_tasks))]

    constraint_pool = _build_balanced_constraint_pool(len(curated_records), seed)
    for task, poison_constraint in zip(curated_records, constraint_pool):
        task["poison_constraint"] = poison_constraint
        task["constraint_type"] = poison_constraint.split(":", 1)[0]

    with open(CURATED_TASKS_PATH, "w", encoding="utf-8") as handle:
        json.dump(curated_records, handle, indent=2, ensure_ascii=False)

    return curated_records


def main() -> None:
    curated_records = prepare_curated_dataset()
    print(f"Saved {len(curated_records)} curated tasks to {CURATED_TASKS_PATH}")


if __name__ == "__main__":
    main()
