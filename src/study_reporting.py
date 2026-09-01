from __future__ import annotations

import os
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from .config import PROJECT_ROOT, RESULTS_DIR
    from .research_artifacts import RunArtifacts, load_json, write_csv, write_json, write_markdown_table
except ImportError:
    from config import PROJECT_ROOT, RESULTS_DIR
    from research_artifacts import RunArtifacts, load_json, write_csv, write_json, write_markdown_table


STUDY_OVERVIEW_DIR = os.path.join(RESULTS_DIR, "study_overview")
STUDY_OVERVIEW_TABLES_DIR = os.path.join(STUDY_OVERVIEW_DIR, "tables")
STUDY_OVERVIEW_FIGURES_DIR = os.path.join(STUDY_OVERVIEW_DIR, "figures")


def _ensure_directories() -> None:
    os.makedirs(STUDY_OVERVIEW_DIR, exist_ok=True)
    os.makedirs(STUDY_OVERVIEW_TABLES_DIR, exist_ok=True)
    os.makedirs(STUDY_OVERVIEW_FIGURES_DIR, exist_ok=True)


def _load_run_bundle(run_id: str) -> dict[str, Any]:
    artifacts = RunArtifacts.for_run(run_id)
    return {
        "run_id": run_id,
        "artifacts": artifacts,
        "manifest": load_json(artifacts.manifest_path, default={}) or {},
        "summary": load_json(artifacts.final_metrics_path, default={}) or {},
    }


def _condition_label(experiment_type: str, condition: str) -> str:
    if experiment_type == "run1_core":
        return {"baseline": "Baseline", "experimental": "Context-Aware", "developer": "Developer"}.get(
            condition,
            condition,
        )
    if experiment_type == "run2_multihop":
        return {"baseline": "Baseline Final", "experimental": "Context-Aware Final", "developer": "Developer"}.get(
            condition,
            condition,
        )
    if experiment_type == "run3_ablation":
        return {"baseline": "Baseline", "experimental": "Prompt-Only Ablation", "developer": "Developer"}.get(
            condition,
            condition,
        )
    return condition


def _build_condition_rows(run_bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in run_bundles:
        summary = bundle["summary"]
        experiment_type = summary["experiment_type"]
        for condition in ("developer", "baseline", "experimental"):
            condition_payload = summary.get(condition, {})
            correctness_payload = condition_payload.get("correctness", {})
            adherence_payload = condition_payload.get("adherence", {})
            tokens_payload = condition_payload.get("tokens", {})
            rows.append(
                {
                    "run_id": bundle["run_id"],
                    "experiment_name": summary["experiment_name"],
                    "experiment_type": experiment_type,
                    "condition": condition,
                    "condition_label": _condition_label(experiment_type, condition),
                    "task_count": correctness_payload.get("task_count", 0),
                    "correctness_percent": correctness_payload.get("correctness_percent", ""),
                    "adherence_percent": adherence_payload.get("constraint_adherence_percent", ""),
                    "average_total_tokens": tokens_payload.get("average_total_tokens", ""),
                }
            )
    return rows


def _build_ablation_rows(run_bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_type = {bundle["summary"]["experiment_type"]: bundle for bundle in run_bundles}
    rows: list[dict[str, Any]] = []
    for experiment_type, label in (
        ("run1_core", "Context-Aware Explicit Constraints"),
        ("run3_ablation", "Prompt-Only Ablation"),
    ):
        bundle = by_type.get(experiment_type)
        if not bundle:
            continue
        experimental = bundle["summary"]["experimental"]
        rows.append(
            {
                "variant": label,
                "run_id": bundle["run_id"],
                "task_count": experimental["correctness"]["task_count"],
                "correctness_percent": experimental["correctness"]["correctness_percent"],
                "adherence_percent": experimental["adherence"]["constraint_adherence_percent"],
                "average_total_tokens": experimental["tokens"]["average_total_tokens"],
            }
        )
    return rows


def _build_run_rows(run_bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in run_bundles:
        summary = bundle["summary"]
        rows.append(
            {
                "run_id": bundle["run_id"],
                "experiment_name": summary["experiment_name"],
                "experiment_type": summary["experiment_type"],
                "task_count": summary["task_count"],
                "baseline_correctness_percent": summary["baseline"]["correctness"]["correctness_percent"],
                "baseline_adherence_percent": summary["baseline"]["adherence"]["constraint_adherence_percent"],
                "experimental_correctness_percent": summary["experimental"]["correctness"]["correctness_percent"],
                "experimental_adherence_percent": summary["experimental"]["adherence"]["constraint_adherence_percent"],
                "correctness_delta": summary["baseline_vs_experimental"]["correctness_percent_delta"],
                "adherence_delta": summary["baseline_vs_experimental"]["adherence_percent_delta"],
                "token_delta": summary["baseline_vs_experimental"]["average_total_tokens_delta"],
            }
        )
    return rows


def _generate_figures(run_bundles: list[dict[str, Any]], condition_rows: list[dict[str, Any]], ablation_rows: list[dict[str, Any]]) -> dict[str, Any]:
    figure_metadata: dict[str, Any] = {}

    final_condition_rows = [row for row in condition_rows if row["condition"] in {"baseline", "experimental"}]
    grouped_by_run: dict[str, list[dict[str, Any]]] = {}
    for row in final_condition_rows:
        grouped_by_run.setdefault(row["run_id"], []).append(row)

    run_ids = [bundle["run_id"] for bundle in run_bundles]
    x_positions = range(len(run_ids))
    width = 0.35

    adherence_path = os.path.join(STUDY_OVERVIEW_FIGURES_DIR, "cross_run_adherence.png")
    fig, ax = plt.subplots(figsize=(10, 5))
    baseline_vals = []
    experimental_vals = []
    for run_id in run_ids:
        rows = {row["condition"]: row for row in grouped_by_run.get(run_id, [])}
        baseline_vals.append(float(rows.get("baseline", {}).get("adherence_percent") or 0.0))
        experimental_vals.append(float(rows.get("experimental", {}).get("adherence_percent") or 0.0))
    ax.bar([value - width / 2 for value in x_positions], baseline_vals, width=width, label="Baseline")
    ax.bar([value + width / 2 for value in x_positions], experimental_vals, width=width, label="Experimental")
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(run_ids)
    ax.set_ylabel("Adherence (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Cross-Run Constraint Adherence Comparison")
    ax.legend()
    fig.tight_layout()
    fig.savefig(adherence_path, dpi=200)
    plt.close(fig)
    figure_metadata["cross_run_adherence.png"] = {
        "title": "Cross-Run Constraint Adherence Comparison",
        "caption": "Grouped bar chart comparing final baseline and experimental adherence percentages across Run 1, Run 2, and Run 3.",
    }

    correctness_path = os.path.join(STUDY_OVERVIEW_FIGURES_DIR, "cross_run_correctness.png")
    fig, ax = plt.subplots(figsize=(10, 5))
    baseline_vals = []
    experimental_vals = []
    for run_id in run_ids:
        rows = {row["condition"]: row for row in grouped_by_run.get(run_id, [])}
        baseline_vals.append(float(rows.get("baseline", {}).get("correctness_percent") or 0.0))
        experimental_vals.append(float(rows.get("experimental", {}).get("correctness_percent") or 0.0))
    ax.bar([value - width / 2 for value in x_positions], baseline_vals, width=width, label="Baseline")
    ax.bar([value + width / 2 for value in x_positions], experimental_vals, width=width, label="Experimental")
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(run_ids)
    ax.set_ylabel("Correctness (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Cross-Run Correctness Comparison")
    ax.legend()
    fig.tight_layout()
    fig.savefig(correctness_path, dpi=200)
    plt.close(fig)
    figure_metadata["cross_run_correctness.png"] = {
        "title": "Cross-Run Correctness Comparison",
        "caption": "Grouped bar chart comparing final baseline and experimental correctness percentages across Run 1, Run 2, and Run 3.",
    }

    if ablation_rows:
        ablation_path = os.path.join(STUDY_OVERVIEW_FIGURES_DIR, "ablation_comparison.png")
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        labels = [row["variant"] for row in ablation_rows]
        adherence_vals = [float(row["adherence_percent"] or 0.0) for row in ablation_rows]
        token_vals = [float(row["average_total_tokens"] or 0.0) for row in ablation_rows]
        axes[0].bar(labels, adherence_vals)
        axes[0].set_ylim(0, 100)
        axes[0].set_ylabel("Adherence (%)")
        axes[0].set_title("Ablation Adherence")
        axes[1].bar(labels, token_vals)
        axes[1].set_ylabel("Average Total Tokens")
        axes[1].set_title("Ablation Token Usage")
        for axis in axes:
            axis.tick_params(axis="x", rotation=20)
        fig.tight_layout()
        fig.savefig(ablation_path, dpi=200)
        plt.close(fig)
        figure_metadata["ablation_comparison.png"] = {
            "title": "Ablation Comparison",
            "caption": "Side-by-side charts comparing the Run 1 context-aware experimental condition to the Run 3 prompt-only ablation on adherence and token usage.",
        }

    write_json(os.path.join(STUDY_OVERVIEW_FIGURES_DIR, "figure_metadata.json"), figure_metadata)
    return figure_metadata


def _write_overview_markdown(run_bundles: list[dict[str, Any]], figure_metadata: dict[str, Any]) -> None:
    lines = [
        "# Study Overview",
        "",
        "This directory aggregates the results from all three planned experiments.",
        "",
        "## Runs",
        "",
    ]
    for bundle in run_bundles:
        summary = bundle["summary"]
        lines.append(
            f"- `{bundle['run_id']}`: {summary['experiment_name']} "
            f"({summary['experiment_type']}, {summary['task_count']} tasks)"
        )

    lines.extend(["", "## Figures", ""])
    for filename, metadata in figure_metadata.items():
        lines.append(f"- [${metadata['title']}]({os.path.join('figures', filename).replace(os.sep, '/')})")
        lines.append(f"  {metadata['caption']}")

    lines.extend(
        [
            "",
            "## Tables",
            "",
            "- [Run Comparison](tables/run_comparison.md)",
            "- [Condition Comparison](tables/condition_comparison.md)",
            "- [Ablation Comparison](tables/ablation_comparison.md)",
            "",
        ]
    )

    with open(os.path.join(STUDY_OVERVIEW_DIR, "study_overview.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_root_readme(run_bundles: list[dict[str, Any]]) -> None:
    by_type = {bundle["summary"]["experiment_type"]: bundle for bundle in run_bundles}
    run1 = by_type.get("run1_core")
    run2 = by_type.get("run2_multihop")
    run3 = by_type.get("run3_ablation")

    def _metric(bundle: dict[str, Any] | None, condition: str, category: str, key: str) -> str:
        if not bundle:
            return "n/a"
        return str(bundle["summary"][condition][category][key])

    lines = [
        "# Context-Aware Handoffs Research Study",
        "",
        "This repository contains a role-specialized LLM-agent study on context-aware handoffs in code maintenance pipelines.",
        "",
        "## Research Setup",
        "",
        "- Model family: Gemini, instantiated as role-specialized agents over a shared backbone.",
        "- Agent roles: `DeveloperAgent`, `MaintainerAgent`, and `JudgeAgent` in `src/agents.py`.",
        "- Dataset: curated 50-task subset of HumanEval with assigned poison constraints.",
        "- Constraint types: Negative, Structural, and Efficiency.",
        "- Core artifact root: `results/runs/`.",
        "",
        "## Experiments",
        "",
        "- Run 1 (`run1_core`): 2-agent baseline vs context-aware handoff on the 50-task curated dataset.",
        "- Run 2 (`run2_multihop`): 3-agent multi-hop extension on a 15-task subset to test context degradation across hops.",
        "- Run 3 (`run3_ablation`): prompt-only ablation that removes the explicit constraint field from the experimental handoff.",
        "",
        "## How the Pipeline Works",
        "",
        "1. `src/dataset_prep.py` downloads HumanEval into the project-local `.cache/` directory and writes `data/curated_tasks.json`.",
        "2. `src/handoff_pipeline.py` runs the role-specialized LLM pipeline and writes a run-scoped artifact folder.",
        "3. `src/evaluator.py` executes correctness checks, constraint adherence checks, and paper-facing report generation.",
        "4. `src/study_runner.py` orchestrates all planned runs and then generates cross-run reports and this README.",
        "",
        "## Evaluation and Reporting",
        "",
        "- Correctness is evaluated deterministically by executing the HumanEval tests against candidate code in a subprocess sandbox with a timeout.",
        "- Structural and Efficiency constraints are judged deterministically from AST/static heuristics.",
        "- Negative constraints are judged with the Gemini-based `JudgeAgent`.",
        "- Each run stores prompts, raw model outputs, token usage, timings, retries, figures, tables, example cases, and a narrative study summary.",
        "",
        "## Current Results Snapshot",
        "",
        f"- Run 1 Baseline adherence: {_metric(run1, 'baseline', 'adherence', 'constraint_adherence_percent')}%",
        f"- Run 1 Experimental adherence: {_metric(run1, 'experimental', 'adherence', 'constraint_adherence_percent')}%",
        f"- Run 2 Baseline adherence: {_metric(run2, 'baseline', 'adherence', 'constraint_adherence_percent')}%",
        f"- Run 2 Experimental adherence: {_metric(run2, 'experimental', 'adherence', 'constraint_adherence_percent')}%",
        f"- Run 3 Prompt-only adherence: {_metric(run3, 'experimental', 'adherence', 'constraint_adherence_percent')}%",
        "",
        "## Where to Find Things",
        "",
        "- Curated dataset: `data/curated_tasks.json`",
        "- Latest top-level metrics mirror: `results/final_metrics.json`",
        "- Per-run artifacts: `results/runs/<run_id>/`",
        "- Cross-run comparison package: `results/study_overview/`",
        "- Cross-run overview: `results/study_overview/study_overview.md`",
        "",
        "## Per-Run Artifact Layout",
        "",
        "- `inputs/`: exact inputs and experiment configuration",
        "- `outputs/`: pipeline results, evaluation results, and final metrics",
        "- `logs/`: raw LLM prompt/response JSONL logs",
        "- `tables/`: CSV and Markdown tables for the paper",
        "- `figures/`: PNG figures plus figure metadata",
        "- `examples/`: qualitative example packs",
        "- `study_summary.md`: run-level narrative summary",
        "",
        "## Models and Agent Definitions",
        "",
        "- Developer default model: loaded from `GEMINI_DEVELOPER_MODEL`, currently defaulting to `gemini-2.5-flash-lite`.",
        "- Maintainer default model: loaded from `GEMINI_MAINTAINER_MODEL`, currently defaulting to `gemini-2.5-flash-lite`.",
        "- Judge default model: loaded from `GEMINI_JUDGE_MODEL`, currently defaulting to `gemini-2.5-flash-lite`.",
        "- The code includes fallback handling for transient quota/unavailability issues across compatible Gemini flash variants.",
        "",
        "## Reproduction",
        "",
        "Run the full study with:",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe src\\study_runner.py --overwrite",
        "```",
        "",
        "## Citation-Relevant Components",
        "",
        "- HumanEval benchmark and associated paper",
        "- Hugging Face `datasets` library",
        "- Google Gemini API / `google-genai` SDK",
        "- Pydantic for structured schemas",
        "",
        "## Notes",
        "",
        "- In this project, an `agent` means a role-conditioned LLM instance with its own prompt policy, interface, and task in the handoff pipeline.",
        "- The same Gemini model family can back multiple agents while still supporting a valid multi-agent experimental design.",
        "",
    ]

    with open(os.path.join(PROJECT_ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def generate_study_overview(run_ids: list[str]) -> dict[str, Any]:
    _ensure_directories()
    run_bundles = [_load_run_bundle(run_id) for run_id in run_ids]

    run_rows = _build_run_rows(run_bundles)
    condition_rows = _build_condition_rows(run_bundles)
    ablation_rows = _build_ablation_rows(run_bundles)

    write_json(os.path.join(STUDY_OVERVIEW_DIR, "run_comparison.json"), run_rows)
    write_json(os.path.join(STUDY_OVERVIEW_DIR, "condition_comparison.json"), condition_rows)
    write_json(os.path.join(STUDY_OVERVIEW_DIR, "ablation_comparison.json"), ablation_rows)

    run_fields = list(run_rows[0].keys()) if run_rows else [
        "run_id",
        "experiment_name",
        "experiment_type",
        "task_count",
        "baseline_correctness_percent",
        "baseline_adherence_percent",
        "experimental_correctness_percent",
        "experimental_adherence_percent",
        "correctness_delta",
        "adherence_delta",
        "token_delta",
    ]
    condition_fields = list(condition_rows[0].keys()) if condition_rows else [
        "run_id",
        "experiment_name",
        "experiment_type",
        "condition",
        "condition_label",
        "task_count",
        "correctness_percent",
        "adherence_percent",
        "average_total_tokens",
    ]
    ablation_fields = list(ablation_rows[0].keys()) if ablation_rows else [
        "variant",
        "run_id",
        "task_count",
        "correctness_percent",
        "adherence_percent",
        "average_total_tokens",
    ]

    write_csv(os.path.join(STUDY_OVERVIEW_TABLES_DIR, "run_comparison.csv"), run_fields, run_rows)
    write_markdown_table(os.path.join(STUDY_OVERVIEW_TABLES_DIR, "run_comparison.md"), run_fields, run_rows)
    write_csv(
        os.path.join(STUDY_OVERVIEW_TABLES_DIR, "condition_comparison.csv"),
        condition_fields,
        condition_rows,
    )
    write_markdown_table(
        os.path.join(STUDY_OVERVIEW_TABLES_DIR, "condition_comparison.md"),
        condition_fields,
        condition_rows,
    )
    write_csv(
        os.path.join(STUDY_OVERVIEW_TABLES_DIR, "ablation_comparison.csv"),
        ablation_fields,
        ablation_rows,
    )
    write_markdown_table(
        os.path.join(STUDY_OVERVIEW_TABLES_DIR, "ablation_comparison.md"),
        ablation_fields,
        ablation_rows,
    )

    figure_metadata = _generate_figures(run_bundles, condition_rows, ablation_rows)
    _write_overview_markdown(run_bundles, figure_metadata)
    _write_root_readme(run_bundles)

    return {
        "study_overview_dir": STUDY_OVERVIEW_DIR,
        "run_ids": run_ids,
        "figure_metadata": figure_metadata,
    }
