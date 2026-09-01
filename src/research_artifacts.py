from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from .config import CURATED_TASKS_PATH, CURATION_SEED, PROJECT_ROOT, RESULTS_DIR, RUNS_DIR
except ImportError:
    from config import CURATED_TASKS_PATH, CURATION_SEED, PROJECT_ROOT, RESULTS_DIR, RUNS_DIR


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_run_id(experiment_type: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{slugify(experiment_type)}"


def slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "run"


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def load_json(path: str, default: Any | None = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def append_jsonl(path: str, payload: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_csv(path: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_markdown_table(path: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    header = "| " + " | ".join(fieldnames) + " |"
    divider = "| " + " | ".join(["---"] * len(fieldnames)) + " |"
    lines = [header, divider]

    for row in rows:
        values = [str(row.get(field, "")) for field in fieldnames]
        lines.append("| " + " | ".join(values) + " |")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def get_package_versions(package_names: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for package_name in package_names:
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = "not-installed"
    return versions


@dataclass
class RunArtifacts:
    run_id: str
    run_dir: str
    inputs_dir: str
    outputs_dir: str
    logs_dir: str
    tables_dir: str
    figures_dir: str
    examples_dir: str
    manifest_path: str
    experiment_config_path: str
    curated_snapshot_path: str
    pipeline_results_path: str
    evaluation_results_path: str
    final_metrics_path: str
    pipeline_llm_log_path: str
    evaluation_llm_log_path: str
    figure_metadata_path: str
    study_summary_path: str
    manual_screenshot_checklist_path: str

    @classmethod
    def for_run(cls, run_id: str) -> "RunArtifacts":
        run_dir = os.path.join(RUNS_DIR, run_id)
        return cls(
            run_id=run_id,
            run_dir=run_dir,
            inputs_dir=os.path.join(run_dir, "inputs"),
            outputs_dir=os.path.join(run_dir, "outputs"),
            logs_dir=os.path.join(run_dir, "logs"),
            tables_dir=os.path.join(run_dir, "tables"),
            figures_dir=os.path.join(run_dir, "figures"),
            examples_dir=os.path.join(run_dir, "examples"),
            manifest_path=os.path.join(run_dir, "manifest.json"),
            experiment_config_path=os.path.join(run_dir, "inputs", "experiment_config.json"),
            curated_snapshot_path=os.path.join(run_dir, "inputs", "curated_tasks_snapshot.json"),
            pipeline_results_path=os.path.join(run_dir, "outputs", "pipeline_results.json"),
            evaluation_results_path=os.path.join(run_dir, "outputs", "evaluation_results.json"),
            final_metrics_path=os.path.join(run_dir, "outputs", "final_metrics.json"),
            pipeline_llm_log_path=os.path.join(run_dir, "logs", "pipeline_llm_calls.jsonl"),
            evaluation_llm_log_path=os.path.join(run_dir, "logs", "evaluation_llm_calls.jsonl"),
            figure_metadata_path=os.path.join(run_dir, "figures", "figure_metadata.json"),
            study_summary_path=os.path.join(run_dir, "study_summary.md"),
            manual_screenshot_checklist_path=os.path.join(run_dir, "manual_screenshot_checklist.md"),
        )

    def ensure_directories(self) -> None:
        os.makedirs(self.run_dir, exist_ok=True)
        os.makedirs(self.inputs_dir, exist_ok=True)
        os.makedirs(self.outputs_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.tables_dir, exist_ok=True)
        os.makedirs(self.figures_dir, exist_ok=True)
        os.makedirs(self.examples_dir, exist_ok=True)

    def artifact_paths(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "inputs": {
                "experiment_config": self.experiment_config_path,
                "curated_tasks_snapshot": self.curated_snapshot_path,
            },
            "outputs": {
                "pipeline_results": self.pipeline_results_path,
                "evaluation_results": self.evaluation_results_path,
                "final_metrics": self.final_metrics_path,
            },
            "logs": {
                "pipeline_llm_calls": self.pipeline_llm_log_path,
                "evaluation_llm_calls": self.evaluation_llm_log_path,
            },
            "tables_dir": self.tables_dir,
            "figures": {
                "directory": self.figures_dir,
                "metadata": self.figure_metadata_path,
            },
            "examples_dir": self.examples_dir,
            "study_summary": self.study_summary_path,
            "manual_screenshot_checklist": self.manual_screenshot_checklist_path,
        }


def prepare_run_artifacts(
    *,
    run_id: str | None,
    experiment_type: str,
    resume: bool,
    overwrite: bool,
) -> tuple[RunArtifacts, bool]:
    resolved_run_id = run_id or generate_run_id(experiment_type)
    artifacts = RunArtifacts.for_run(resolved_run_id)
    run_exists = os.path.isdir(artifacts.run_dir)

    if run_exists and not resume and not overwrite:
        raise FileExistsError(
            f"Run directory already exists for run_id='{resolved_run_id}'. "
            "Use --resume to continue or --overwrite to regenerate outputs."
        )

    artifacts.ensure_directories()
    return artifacts, not run_exists


def find_latest_run_id() -> str:
    if not os.path.isdir(RUNS_DIR):
        raise FileNotFoundError(f"No run directory exists at {RUNS_DIR}.")

    candidate_names = [
        name for name in os.listdir(RUNS_DIR) if os.path.isdir(os.path.join(RUNS_DIR, name))
    ]
    if not candidate_names:
        raise FileNotFoundError(f"No experiment runs were found in {RUNS_DIR}.")

    candidate_names.sort(
        key=lambda name: os.path.getmtime(os.path.join(RUNS_DIR, name)),
        reverse=True,
    )
    return candidate_names[0]


def initialize_log_file(path: str, overwrite: bool) -> None:
    if overwrite or not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")


def snapshot_curated_tasks(source_path: str, destination_path: str) -> None:
    shutil.copyfile(source_path, destination_path)


def build_manifest(
    *,
    artifacts: RunArtifacts,
    experiment_name: str,
    experiment_type: str,
    cli_args: dict[str, Any],
    model_config: dict[str, Any],
    settings: dict[str, Any],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": artifacts.run_id,
        "experiment_name": experiment_name,
        "experiment_type": experiment_type,
        "created_at_utc": created_at_utc or utc_now_iso(),
        "project_root": PROJECT_ROOT,
        "results_root": RESULTS_DIR,
        "curated_tasks_source_path": CURATED_TASKS_PATH,
        "random_seed": CURATION_SEED,
        "cli_args": cli_args,
        "model_config": model_config,
        "settings": settings,
        "environment": {
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "package_versions": get_package_versions(
                [
                    "datasets",
                    "google-genai",
                    "matplotlib",
                    "pydantic",
                    "python-dotenv",
                    "pytest",
                ]
            ),
        },
        "experiment_metadata": {
            "agent_count": 2,
            "handoff_mode": "developer_to_maintainer",
            "ablation_flags": {},
        },
        "status": {
            "pipeline": "not_started",
            "evaluation": "not_started",
        },
        "artifacts": artifacts.artifact_paths(),
    }


def update_manifest(manifest_path: str, updates: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(manifest_path, default={}) or {}

    def _merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                target[key] = _merge(target[key], value)
            else:
                target[key] = value
        return target

    manifest = _merge(manifest, updates)
    write_json(manifest_path, manifest)
    return manifest
