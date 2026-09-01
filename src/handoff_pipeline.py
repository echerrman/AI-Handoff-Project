from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel

try:
    from .agents import DeveloperAgent, MaintainerAgent
    from .config import (
        CURATED_TASKS_PATH,
        CURATION_SEED,
        DATA_DIR,
        DEFAULT_EXPERIMENT_NAME,
        DEFAULT_EXPERIMENT_TYPE,
        DEVELOPER_MODEL,
        GEMINI_RATE_LIMIT_SECONDS,
        HF_DATASETS_CACHE,
        HF_HOME,
        MAINTAINER_MODEL,
        PIPELINE_RESULTS_PATH,
        RUN2_DEFAULT_TASK_LIMIT,
    )
    from .research_artifacts import (
        append_jsonl,
        build_manifest,
        initialize_log_file,
        load_json,
        prepare_run_artifacts,
        snapshot_curated_tasks,
        update_manifest,
        utc_now_iso,
        write_json,
    )
except ImportError:
    from agents import DeveloperAgent, MaintainerAgent
    from config import (
        CURATED_TASKS_PATH,
        CURATION_SEED,
        DATA_DIR,
        DEFAULT_EXPERIMENT_NAME,
        DEFAULT_EXPERIMENT_TYPE,
        DEVELOPER_MODEL,
        GEMINI_RATE_LIMIT_SECONDS,
        HF_DATASETS_CACHE,
        HF_HOME,
        MAINTAINER_MODEL,
        PIPELINE_RESULTS_PATH,
        RUN2_DEFAULT_TASK_LIMIT,
    )
    from research_artifacts import (
        append_jsonl,
        build_manifest,
        initialize_log_file,
        load_json,
        prepare_run_artifacts,
        snapshot_curated_tasks,
        update_manifest,
        utc_now_iso,
        write_json,
    )


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_dump_json(model: BaseModel, *, indent: int = 2) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json(indent=indent)
    return json.dumps(model.dict(), indent=indent)


class GenerationState(BaseModel):
    original_prompt: str
    explicit_constraints: str


class HandoffReceipt(BaseModel):
    task_id: str
    generation_state: GenerationState
    code_artifact: str


class PromptOnlyContext(BaseModel):
    task_id: str
    original_prompt: str
    code_artifact: str


def load_curated_tasks(path: str = CURATED_TASKS_PATH) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Curated task file not found at {path}. Run src/dataset_prep.py first."
        )

    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        raise ValueError("Curated task file must contain a JSON list of task objects.")
    return payload


def load_existing_results(path: str) -> dict[str, dict[str, Any]]:
    payload = load_json(path, default=[])
    if not payload:
        return {}
    if not isinstance(payload, list):
        raise ValueError("Existing pipeline results must be a JSON list.")

    return {
        result["task_id"]: result
        for result in payload
        if isinstance(result, dict) and "task_id" in result
    }


def should_reuse_existing_result(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    return record.get("status") == "completed"


def save_results(results: list[dict[str, Any]], run_results_path: str) -> None:
    write_json(run_results_path, results)
    write_json(PIPELINE_RESULTS_PATH, results)


def _default_limit_for_experiment(experiment_type: str, limit: int | None) -> int | None:
    if limit is not None:
        return limit
    if experiment_type == "run2_multihop":
        return RUN2_DEFAULT_TASK_LIMIT
    return None


def _experiment_metadata(experiment_type: str) -> dict[str, Any]:
    if experiment_type == "run2_multihop":
        return {
            "agent_count": 3,
            "handoff_mode": "developer_to_maintainer_to_maintainer",
            "ablation_flags": {},
        }
    if experiment_type == "run3_ablation":
        return {
            "agent_count": 2,
            "handoff_mode": "developer_to_maintainer",
            "ablation_flags": {"prompt_only_without_explicit_constraint_field": True},
        }
    return {
        "agent_count": 2,
        "handoff_mode": "developer_to_maintainer",
        "ablation_flags": {},
    }


def _build_run_configuration(
    *,
    run_id: str,
    experiment_name: str,
    experiment_type: str,
    limit: int | None,
    overwrite: bool,
    resume: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "experiment_name": experiment_name,
        "experiment_type": experiment_type,
        "random_seed": CURATION_SEED,
        "task_limit": limit,
        "resume": resume,
        "overwrite": overwrite,
        "source_curated_tasks_path": CURATED_TASKS_PATH,
        "project_data_dir": DATA_DIR,
        "models": {
            "developer": DEVELOPER_MODEL,
            "maintainer": MAINTAINER_MODEL,
        },
        "settings": {
            "gemini_rate_limit_seconds": GEMINI_RATE_LIMIT_SECONDS,
            "hf_home": os.environ.get("HF_HOME", HF_HOME),
            "hf_datasets_cache": os.environ.get("HF_DATASETS_CACHE", HF_DATASETS_CACHE),
        },
        "experiment_metadata": _experiment_metadata(experiment_type),
    }


def _log_writer(log_path: str) -> Callable[[dict[str, Any]], None]:
    def _writer(record: dict[str, Any]) -> None:
        append_jsonl(log_path, record)

    return _writer


def _status_print(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _error_payload(message: str, *, phase: str) -> dict[str, Any]:
    return {
        "phase": phase,
        "message": message,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _ordered_results(tasks: list[dict[str, Any]], by_task_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [by_task_id[item["task_id"]] for item in tasks if item["task_id"] in by_task_id]


def _variant_template() -> dict[str, Any]:
    return {
        "prompt": None,
        "handoff_input_json": None,
        "raw_response_text": None,
        "final_code": None,
        "usage": None,
        "error": None,
    }


def _developer_template(prompt: str) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "raw_response_text": None,
        "initial_code": None,
        "usage": None,
        "error": None,
    }


def _hop_template(hop_number: int, condition: str) -> dict[str, Any]:
    return {
        "hop_number": hop_number,
        "condition": condition,
        "prompt": None,
        "handoff_input_json": None,
        "raw_response_text": None,
        "final_code": None,
        "usage": None,
        "error": None,
    }


def _task_record(
    *,
    task: dict[str, Any],
    task_index: int,
    task_count: int,
    run_id: str,
    experiment_name: str,
    experiment_type: str,
) -> dict[str, Any]:
    developer_prompt = DeveloperAgent.build_prompt(task["prompt"], task["poison_constraint"])
    return {
        "task_id": task["task_id"],
        "constraint_type": task.get("constraint_type", task["poison_constraint"].split(":", 1)[0]),
        "poison_constraint": task["poison_constraint"],
        "selection_score": task.get("selection_score"),
        "entry_point": task.get("entry_point"),
        "test": task.get("test"),
        "task_prompt": task["prompt"],
        "status": "running",
        "errors": [],
        "handoff_receipt": None,
        "handoff_receipt_json": None,
        "developer": _developer_template(developer_prompt),
        "baseline": _variant_template(),
        "experimental": _variant_template(),
        "baseline_hops": [],
        "experimental_hops": [],
        "run_metadata": {
            "run_id": run_id,
            "experiment_name": experiment_name,
            "experiment_type": experiment_type,
            "processed_at_utc": None,
            "task_index": task_index,
            "task_count": task_count,
            "reused_existing_result": False,
            "phase_timings_seconds": {},
            "task_duration_seconds": None,
        },
    }


def _make_handoff_receipt(
    *,
    task_id: str,
    original_prompt: str,
    poison_constraint: str,
    code_artifact: str,
) -> tuple[dict[str, Any], str]:
    receipt = HandoffReceipt(
        task_id=task_id,
        generation_state=GenerationState(
            original_prompt=original_prompt,
            explicit_constraints=poison_constraint,
        ),
        code_artifact=code_artifact,
    )
    return _model_dump(receipt), _model_dump_json(receipt, indent=2)


def _make_prompt_only_context(
    *,
    task_id: str,
    original_prompt: str,
    code_artifact: str,
) -> tuple[dict[str, Any], str]:
    context = PromptOnlyContext(
        task_id=task_id,
        original_prompt=original_prompt,
        code_artifact=code_artifact,
    )
    return _model_dump(context), _model_dump_json(context, indent=2)


def _store_variant_invocation(
    target: dict[str, Any],
    *,
    invocation: Any,
    code_key: str,
    handoff_input_json: str | None = None,
) -> None:
    target["prompt"] = invocation.prompt
    target["raw_response_text"] = invocation.raw_text
    target[code_key] = invocation.text
    target["usage"] = invocation.usage_dict()
    if handoff_input_json is not None:
        target["handoff_input_json"] = handoff_input_json


def _run_developer_stage(
    *,
    developer: DeveloperAgent,
    task: dict[str, Any],
    record: dict[str, Any],
    run_id: str,
    experiment_name: str,
    experiment_type: str,
) -> bool:
    task_id = task["task_id"]
    _status_print(f"{task_id}: developer stage started.")
    try:
        developer_result = developer.generate_code(
            task["prompt"],
            task["poison_constraint"],
            context={
                "run_id": run_id,
                "experiment_name": experiment_name,
                "experiment_type": experiment_type,
                "task_id": task_id,
                "phase": "developer_generation",
                "condition": "developer",
                "stage": "pipeline",
            },
        )
        _store_variant_invocation(record["developer"], invocation=developer_result, code_key="initial_code")
        record["run_metadata"]["phase_timings_seconds"]["developer_generation"] = round(
            developer_result.latency_seconds,
            4,
        )
        _status_print(
            f"{task_id}: developer stage finished using {developer_result.model} "
            f"in {developer_result.latency_seconds:.1f}s."
        )
        return True
    except Exception as exc:
        error_message = str(exc)
        record["status"] = "developer_failed"
        record["developer"]["error"] = error_message
        record["errors"].append(_error_payload(error_message, phase="developer_generation"))
        _status_print(f"{task_id}: developer stage failed.")
        return False


def _run_baseline_call(
    *,
    maintainer: MaintainerAgent,
    code_artifact: str,
    record_target: dict[str, Any],
    record: dict[str, Any],
    run_id: str,
    experiment_name: str,
    experiment_type: str,
    task_id: str,
    phase: str,
) -> bool:
    _status_print(f"{task_id}: {phase} started.")
    try:
        result = maintainer.refactor_baseline(
            code_artifact,
            context={
                "run_id": run_id,
                "experiment_name": experiment_name,
                "experiment_type": experiment_type,
                "task_id": task_id,
                "phase": phase,
                "condition": "baseline",
                "stage": "pipeline",
            },
        )
        _store_variant_invocation(record_target, invocation=result, code_key="final_code")
        record["run_metadata"]["phase_timings_seconds"][phase] = round(result.latency_seconds, 4)
        _status_print(
            f"{task_id}: {phase} finished using {result.model} "
            f"in {result.latency_seconds:.1f}s."
        )
        return True
    except Exception as exc:
        error_message = str(exc)
        record_target["error"] = error_message
        record["errors"].append(_error_payload(error_message, phase=phase))
        _status_print(f"{task_id}: {phase} failed.")
        return False


def _run_experimental_call(
    *,
    maintainer: MaintainerAgent,
    handoff_receipt_json: str,
    record_target: dict[str, Any],
    record: dict[str, Any],
    run_id: str,
    experiment_name: str,
    experiment_type: str,
    task_id: str,
    phase: str,
) -> bool:
    _status_print(f"{task_id}: {phase} started.")
    try:
        result = maintainer.refactor_experimental(
            handoff_receipt_json,
            context={
                "run_id": run_id,
                "experiment_name": experiment_name,
                "experiment_type": experiment_type,
                "task_id": task_id,
                "phase": phase,
                "condition": "experimental",
                "stage": "pipeline",
            },
        )
        _store_variant_invocation(
            record_target,
            invocation=result,
            code_key="final_code",
            handoff_input_json=handoff_receipt_json,
        )
        record["run_metadata"]["phase_timings_seconds"][phase] = round(result.latency_seconds, 4)
        _status_print(
            f"{task_id}: {phase} finished using {result.model} "
            f"in {result.latency_seconds:.1f}s."
        )
        return True
    except Exception as exc:
        error_message = str(exc)
        record_target["handoff_input_json"] = handoff_receipt_json
        record_target["error"] = error_message
        record["errors"].append(_error_payload(error_message, phase=phase))
        _status_print(f"{task_id}: {phase} failed.")
        return False


def _run_prompt_only_call(
    *,
    maintainer: MaintainerAgent,
    original_task_prompt: str,
    code_artifact: str,
    handoff_context_json: str,
    record_target: dict[str, Any],
    record: dict[str, Any],
    run_id: str,
    experiment_name: str,
    experiment_type: str,
    task_id: str,
    phase: str,
) -> bool:
    _status_print(f"{task_id}: {phase} started.")
    try:
        result = maintainer.refactor_prompt_only(
            original_task_prompt,
            code_artifact,
            context={
                "run_id": run_id,
                "experiment_name": experiment_name,
                "experiment_type": experiment_type,
                "task_id": task_id,
                "phase": phase,
                "condition": "experimental",
                "stage": "pipeline",
                "ablation_mode": "prompt_only_without_explicit_constraints",
            },
        )
        _store_variant_invocation(
            record_target,
            invocation=result,
            code_key="final_code",
            handoff_input_json=handoff_context_json,
        )
        record["run_metadata"]["phase_timings_seconds"][phase] = round(result.latency_seconds, 4)
        _status_print(
            f"{task_id}: {phase} finished using {result.model} "
            f"in {result.latency_seconds:.1f}s."
        )
        return True
    except Exception as exc:
        error_message = str(exc)
        record_target["handoff_input_json"] = handoff_context_json
        record_target["error"] = error_message
        record["errors"].append(_error_payload(error_message, phase=phase))
        _status_print(f"{task_id}: {phase} failed.")
        return False


def _copy_final_variant(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["prompt"] = source.get("prompt")
    target["handoff_input_json"] = source.get("handoff_input_json")
    target["raw_response_text"] = source.get("raw_response_text")
    target["final_code"] = source.get("final_code")
    target["usage"] = source.get("usage")
    target["error"] = source.get("error")


def _execute_run1_or_run3(
    *,
    maintainer: MaintainerAgent,
    task: dict[str, Any],
    record: dict[str, Any],
    run_id: str,
    experiment_name: str,
    experiment_type: str,
) -> None:
    developer_code = record["developer"]["initial_code"]
    receipt_dict, receipt_json = _make_handoff_receipt(
        task_id=task["task_id"],
        original_prompt=task["prompt"],
        poison_constraint=task["poison_constraint"],
        code_artifact=developer_code,
    )
    record["handoff_receipt"] = receipt_dict
    record["handoff_receipt_json"] = receipt_json

    _run_baseline_call(
        maintainer=maintainer,
        code_artifact=developer_code,
        record_target=record["baseline"],
        record=record,
        run_id=run_id,
        experiment_name=experiment_name,
        experiment_type=experiment_type,
        task_id=task["task_id"],
        phase="baseline_refactor",
    )

    if experiment_type == "run3_ablation":
        prompt_only_context_dict, prompt_only_context_json = _make_prompt_only_context(
            task_id=task["task_id"],
            original_prompt=task["prompt"],
            code_artifact=developer_code,
        )
        record["experimental"]["input_context"] = prompt_only_context_dict
        _run_prompt_only_call(
            maintainer=maintainer,
            original_task_prompt=task["prompt"],
            code_artifact=developer_code,
            handoff_context_json=prompt_only_context_json,
            record_target=record["experimental"],
            record=record,
            run_id=run_id,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
            task_id=task["task_id"],
            phase="experimental_prompt_only_refactor",
        )
    else:
        _run_experimental_call(
            maintainer=maintainer,
            handoff_receipt_json=receipt_json,
            record_target=record["experimental"],
            record=record,
            run_id=run_id,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
            task_id=task["task_id"],
            phase="experimental_refactor",
        )


def _execute_run2_multihop(
    *,
    maintainer: MaintainerAgent,
    task: dict[str, Any],
    record: dict[str, Any],
    run_id: str,
    experiment_name: str,
    experiment_type: str,
) -> None:
    developer_code = record["developer"]["initial_code"]
    receipt_dict, receipt_json = _make_handoff_receipt(
        task_id=task["task_id"],
        original_prompt=task["prompt"],
        poison_constraint=task["poison_constraint"],
        code_artifact=developer_code,
    )
    record["handoff_receipt"] = receipt_dict
    record["handoff_receipt_json"] = receipt_json

    baseline_hop1 = _hop_template(1, "baseline")
    record["baseline_hops"].append(baseline_hop1)
    baseline_hop1_ok = _run_baseline_call(
        maintainer=maintainer,
        code_artifact=developer_code,
        record_target=baseline_hop1,
        record=record,
        run_id=run_id,
        experiment_name=experiment_name,
        experiment_type=experiment_type,
        task_id=task["task_id"],
        phase="baseline_hop_1_refactor",
    )

    baseline_hop2 = _hop_template(2, "baseline")
    record["baseline_hops"].append(baseline_hop2)
    if baseline_hop1_ok and baseline_hop1.get("final_code"):
        _run_baseline_call(
            maintainer=maintainer,
            code_artifact=baseline_hop1["final_code"],
            record_target=baseline_hop2,
            record=record,
            run_id=run_id,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
            task_id=task["task_id"],
            phase="baseline_hop_2_refactor",
        )
    else:
        baseline_hop2["error"] = "Skipped because baseline hop 1 did not produce code."

    if baseline_hop2.get("final_code"):
        _copy_final_variant(record["baseline"], baseline_hop2)

    experimental_hop1 = _hop_template(1, "experimental")
    record["experimental_hops"].append(experimental_hop1)
    experimental_hop1_ok = _run_experimental_call(
        maintainer=maintainer,
        handoff_receipt_json=receipt_json,
        record_target=experimental_hop1,
        record=record,
        run_id=run_id,
        experiment_name=experiment_name,
        experiment_type=experiment_type,
        task_id=task["task_id"],
        phase="experimental_hop_1_refactor",
    )

    experimental_hop2 = _hop_template(2, "experimental")
    record["experimental_hops"].append(experimental_hop2)
    if experimental_hop1_ok and experimental_hop1.get("final_code"):
        hop2_receipt_dict, hop2_receipt_json = _make_handoff_receipt(
            task_id=task["task_id"],
            original_prompt=task["prompt"],
            poison_constraint=task["poison_constraint"],
            code_artifact=experimental_hop1["final_code"],
        )
        record["experimental_handoff_chain"] = {
            "developer_to_hop_1": receipt_dict,
            "hop_1_to_hop_2": hop2_receipt_dict,
        }
        _run_experimental_call(
            maintainer=maintainer,
            handoff_receipt_json=hop2_receipt_json,
            record_target=experimental_hop2,
            record=record,
            run_id=run_id,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
            task_id=task["task_id"],
            phase="experimental_hop_2_refactor",
        )
    else:
        experimental_hop2["error"] = "Skipped because experimental hop 1 did not produce code."

    if experimental_hop2.get("final_code"):
        _copy_final_variant(record["experimental"], experimental_hop2)


def _finalize_status(record: dict[str, Any]) -> bool:
    baseline_ok = bool(record["baseline"].get("final_code"))
    experimental_ok = bool(record["experimental"].get("final_code"))

    if baseline_ok and experimental_ok:
        record["status"] = "completed"
        return False
    if baseline_ok or experimental_ok:
        record["status"] = "completed_with_errors"
        return True
    record["status"] = "maintainer_failed"
    return True


def run_pipeline(
    *,
    run_id: str | None = None,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
    experiment_type: str = DEFAULT_EXPERIMENT_TYPE,
    limit: int | None = None,
    overwrite: bool = False,
    resume: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    resolved_limit = _default_limit_for_experiment(experiment_type, limit)
    artifacts, _ = prepare_run_artifacts(
        run_id=run_id,
        experiment_type=experiment_type,
        resume=resume,
        overwrite=overwrite,
    )
    initialize_log_file(artifacts.pipeline_llm_log_path, overwrite=overwrite)

    if overwrite or not os.path.exists(artifacts.curated_snapshot_path):
        snapshot_curated_tasks(CURATED_TASKS_PATH, artifacts.curated_snapshot_path)

    configuration_payload = _build_run_configuration(
        run_id=artifacts.run_id,
        experiment_name=experiment_name,
        experiment_type=experiment_type,
        limit=resolved_limit,
        overwrite=overwrite,
        resume=resume,
    )
    write_json(artifacts.experiment_config_path, configuration_payload)

    existing_manifest = load_json(artifacts.manifest_path, default=None)
    manifest = existing_manifest or build_manifest(
        artifacts=artifacts,
        experiment_name=experiment_name,
        experiment_type=experiment_type,
        cli_args={
            "run_id": artifacts.run_id,
            "experiment_name": experiment_name,
            "experiment_type": experiment_type,
            "limit": resolved_limit,
            "overwrite": overwrite,
            "resume": resume,
        },
        model_config={
            "developer": DEVELOPER_MODEL,
            "maintainer": MAINTAINER_MODEL,
        },
        settings={
            "gemini_rate_limit_seconds": GEMINI_RATE_LIMIT_SECONDS,
            "random_seed": CURATION_SEED,
            "hf_home": os.environ.get("HF_HOME", HF_HOME),
            "hf_datasets_cache": os.environ.get("HF_DATASETS_CACHE", HF_DATASETS_CACHE),
        },
    )
    write_json(artifacts.manifest_path, manifest)
    update_manifest(
        artifacts.manifest_path,
        {
            "status": {"pipeline": "running"},
            "pipeline_started_at_utc": utc_now_iso(),
            "experiment_metadata": _experiment_metadata(experiment_type),
        },
    )

    tasks = load_curated_tasks()
    if resolved_limit is not None:
        tasks = tasks[:resolved_limit]

    _status_print(
        f"Pipeline run {artifacts.run_id} started for experiment {experiment_type} with {len(tasks)} tasks."
    )

    existing_by_task = {} if overwrite else load_existing_results(artifacts.pipeline_results_path)
    pipeline_logger = _log_writer(artifacts.pipeline_llm_log_path)
    developer = DeveloperAgent(llm_logger=pipeline_logger)
    maintainer = MaintainerAgent(llm_logger=pipeline_logger)

    reused_tasks = 0
    failed_tasks = 0

    for index, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        existing_record = existing_by_task.get(task_id)
        if existing_record and should_reuse_existing_result(existing_record):
            reused_tasks += 1
            existing_record.setdefault("run_metadata", {})
            existing_record["run_metadata"]["reused_existing_result"] = True
            _status_print(f"[{index}/{len(tasks)}] Reusing completed result for {task_id}.")
            continue
        if existing_record:
            _status_print(f"[{index}/{len(tasks)}] Retrying incomplete or failed result for {task_id}.")
        else:
            _status_print(f"[{index}/{len(tasks)}] Starting new task {task_id}.")

        task_started = time.perf_counter()
        record = _task_record(
            task=task,
            task_index=index,
            task_count=len(tasks),
            run_id=artifacts.run_id,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
        )

        developer_ok = _run_developer_stage(
            developer=developer,
            task=task,
            record=record,
            run_id=artifacts.run_id,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
        )

        if developer_ok:
            if experiment_type == "run2_multihop":
                _execute_run2_multihop(
                    maintainer=maintainer,
                    task=task,
                    record=record,
                    run_id=artifacts.run_id,
                    experiment_name=experiment_name,
                    experiment_type=experiment_type,
                )
            else:
                _execute_run1_or_run3(
                    maintainer=maintainer,
                    task=task,
                    record=record,
                    run_id=artifacts.run_id,
                    experiment_name=experiment_name,
                    experiment_type=experiment_type,
                )

            if _finalize_status(record):
                failed_tasks += 1
        else:
            failed_tasks += 1

        record["run_metadata"]["processed_at_utc"] = utc_now_iso()
        record["run_metadata"]["task_duration_seconds"] = round(time.perf_counter() - task_started, 4)
        existing_by_task[task_id] = record
        save_results(_ordered_results(tasks, existing_by_task), artifacts.pipeline_results_path)
        _status_print(
            f"[{index}/{len(tasks)}] Saved {task_id} with status {record['status']} "
            f"after {record['run_metadata']['task_duration_seconds']:.1f}s."
        )

    ordered_results = _ordered_results(tasks, existing_by_task)
    save_results(ordered_results, artifacts.pipeline_results_path)

    pipeline_status = "completed_with_errors" if failed_tasks else "completed"
    update_manifest(
        artifacts.manifest_path,
        {
            "status": {"pipeline": pipeline_status},
            "pipeline_completed_at_utc": utc_now_iso(),
            "pipeline_summary": {
                "task_count": len(tasks),
                "completed_records": len(ordered_results),
                "reused_records": reused_tasks,
                "failed_records": failed_tasks,
                "pipeline_results_path": artifacts.pipeline_results_path,
                "legacy_pipeline_results_path": PIPELINE_RESULTS_PATH,
            },
        },
    )
    return artifacts.run_id, ordered_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the context-aware handoff pipeline.")
    parser.add_argument("--run-id", type=str, default=None, help="Optional run identifier.")
    parser.add_argument(
        "--experiment-name",
        type=str,
        default=DEFAULT_EXPERIMENT_NAME,
        help="Human-readable name for this experiment run.",
    )
    parser.add_argument(
        "--experiment-type",
        type=str,
        default=DEFAULT_EXPERIMENT_TYPE,
        help="Stable experiment type label such as run1_core or run2_multihop.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optionally limit the number of curated tasks processed.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute pipeline outputs for an existing run_id.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an existing run_id and reuse completed task records.",
    )
    args = parser.parse_args()

    resolved_run_id, results = run_pipeline(
        run_id=args.run_id,
        experiment_name=args.experiment_name,
        experiment_type=args.experiment_type,
        limit=args.limit,
        overwrite=args.overwrite,
        resume=args.resume,
    )
    _status_print(f"Saved {len(results)} pipeline results for run {resolved_run_id}.")


if __name__ == "__main__":
    main()
