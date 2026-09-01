from __future__ import annotations

import argparse
import os
import time
from collections import Counter
from typing import Any

try:
    from .config import CURATED_TASKS_PATH
    from .dataset_prep import prepare_curated_dataset
    from .evaluator import evaluate_pipeline_results
    from .handoff_pipeline import run_pipeline
    from .study_reporting import generate_study_overview
except ImportError:
    from config import CURATED_TASKS_PATH
    from dataset_prep import prepare_curated_dataset
    from evaluator import evaluate_pipeline_results
    from handoff_pipeline import run_pipeline
    from research_artifacts import RunArtifacts, load_json
    from study_reporting import generate_study_overview
else:
    from .research_artifacts import RunArtifacts, load_json


RUN_SPECS = [
    {
        "run_id": "run1_core_full",
        "experiment_name": "Run 1 Core Two-Agent Handoff",
        "experiment_type": "run1_core",
        "limit": None,
    },
    {
        "run_id": "run2_multihop_subset15",
        "experiment_name": "Run 2 Multi-Hop Extension",
        "experiment_type": "run2_multihop",
        "limit": 15,
    },
    {
        "run_id": "run3_ablation_full",
        "experiment_name": "Run 3 Prompt-Only Ablation",
        "experiment_type": "run3_ablation",
        "limit": None,
    },
]


def _status_print(message: str) -> None:
    print(message, flush=True)


def _pipeline_status_counts(run_id: str) -> Counter[str]:
    artifacts = RunArtifacts.for_run(run_id)
    payload = load_json(artifacts.pipeline_results_path, default=[]) or []
    if not isinstance(payload, list):
        raise ValueError(f"Pipeline results for run {run_id} were not a JSON list.")
    return Counter(str(item.get("status")) for item in payload if isinstance(item, dict))


def _run_pipeline_until_clean(
    *,
    run_id: str,
    experiment_name: str,
    experiment_type: str,
    limit: int | None,
    overwrite: bool,
    retry_delay_seconds: float,
    max_pipeline_cycles: int,
) -> str:
    for cycle in range(1, max_pipeline_cycles + 1):
        _status_print(
            f"Starting pipeline cycle {cycle}/{max_pipeline_cycles} for {run_id} ({experiment_type})."
        )
        resolved_run_id, _ = run_pipeline(
            run_id=run_id,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
            limit=limit,
            overwrite=overwrite if cycle == 1 else False,
            resume=not overwrite or cycle > 1,
        )
        status_counts = _pipeline_status_counts(resolved_run_id)
        incomplete_count = sum(
            count for status, count in status_counts.items() if status != "completed"
        )
        _status_print(
            f"Pipeline cycle {cycle} finished for {resolved_run_id} with status counts: "
            + ", ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
        )
        if incomplete_count == 0:
            _status_print(f"{resolved_run_id} is now fully complete and ready for evaluation.")
            return resolved_run_id
        if cycle < max_pipeline_cycles:
            _status_print(
                f"{resolved_run_id} still has {incomplete_count} incomplete or failed task records. "
                f"Sleeping {retry_delay_seconds:.0f}s before the next resume cycle."
            )
            time.sleep(retry_delay_seconds)

    raise RuntimeError(
        f"Run {run_id} still had incomplete or failed task records after {max_pipeline_cycles} pipeline cycles."
    )


def _run_evaluation_until_complete(
    *,
    run_id: str,
    retry_delay_seconds: float,
    max_evaluation_cycles: int,
) -> None:
    for cycle in range(1, max_evaluation_cycles + 1):
        _status_print(f"Starting evaluation cycle {cycle}/{max_evaluation_cycles} for {run_id}.")
        try:
            evaluate_pipeline_results(run_id=run_id)
            _status_print(f"Evaluation cycle {cycle} completed successfully for {run_id}.")
            return
        except Exception as exc:
            _status_print(f"Evaluation cycle {cycle} failed for {run_id}: {exc}")
            if cycle < max_evaluation_cycles:
                _status_print(
                    f"Sleeping {retry_delay_seconds:.0f}s before retrying evaluation for {run_id}."
                )
                time.sleep(retry_delay_seconds)

    raise RuntimeError(
        f"Run {run_id} still failed evaluation after {max_evaluation_cycles} evaluation cycles."
    )


def run_full_study(
    *,
    overwrite: bool = False,
    refresh_dataset: bool = False,
    retry_delay_seconds: float = 120.0,
    max_pipeline_cycles: int = 24,
    max_evaluation_cycles: int = 24,
) -> dict[str, Any]:
    if refresh_dataset or not os.path.exists(CURATED_TASKS_PATH):
        prepare_curated_dataset()

    completed_run_ids: list[str] = []
    for spec in RUN_SPECS:
        run_id = _run_pipeline_until_clean(
            run_id=spec["run_id"],
            experiment_name=spec["experiment_name"],
            experiment_type=spec["experiment_type"],
            limit=spec["limit"],
            overwrite=overwrite,
            retry_delay_seconds=retry_delay_seconds,
            max_pipeline_cycles=max_pipeline_cycles,
        )
        _status_print(f"Evaluating clean run {run_id}.")
        _run_evaluation_until_complete(
            run_id=run_id,
            retry_delay_seconds=retry_delay_seconds,
            max_evaluation_cycles=max_evaluation_cycles,
        )
        completed_run_ids.append(run_id)

    _status_print("Generating cross-run study overview artifacts.")
    overview = generate_study_overview(completed_run_ids)
    return {
        "run_ids": completed_run_ids,
        "overview": overview,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all study experiments and generate aggregate reports.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute all run outputs from scratch for the stable run ids.",
    )
    parser.add_argument(
        "--refresh-dataset",
        action="store_true",
        help="Regenerate the curated dataset before running the study.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=120.0,
        help="Delay between resume cycles when a run still has incomplete or failed task records.",
    )
    parser.add_argument(
        "--max-pipeline-cycles",
        type=int,
        default=24,
        help="Maximum number of resume cycles to attempt per run before aborting.",
    )
    parser.add_argument(
        "--max-evaluation-cycles",
        type=int,
        default=24,
        help="Maximum number of resume cycles to attempt for evaluation before aborting.",
    )
    args = parser.parse_args()

    result = run_full_study(
        overwrite=args.overwrite,
        refresh_dataset=args.refresh_dataset,
        retry_delay_seconds=args.retry_delay_seconds,
        max_pipeline_cycles=args.max_pipeline_cycles,
        max_evaluation_cycles=args.max_evaluation_cycles,
    )
    print("Completed study runs: " + ", ".join(result["run_ids"]), flush=True)


if __name__ == "__main__":
    main()
