from __future__ import annotations

import argparse
import ast
import copy
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from .agents import JudgeAgent
    from .config import FINAL_METRICS_PATH
    from .correctness import evaluate_code_correctness
    from .research_artifacts import (
        append_jsonl,
        find_latest_run_id,
        initialize_log_file,
        load_json,
        update_manifest,
        utc_now_iso,
        write_csv,
        write_json,
        write_markdown_table,
        RunArtifacts,
    )
except ImportError:
    from agents import JudgeAgent
    from config import FINAL_METRICS_PATH
    from correctness import evaluate_code_correctness
    from research_artifacts import (
        append_jsonl,
        find_latest_run_id,
        initialize_log_file,
        load_json,
        update_manifest,
        utc_now_iso,
        write_csv,
        write_json,
        write_markdown_table,
        RunArtifacts,
    )


JOINT_OUTCOME_LABELS = [
    "correct_and_adherent",
    "correct_not_adherent",
    "incorrect_adherent",
    "incorrect_not_adherent",
]


def _status_print(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def load_pipeline_results(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Pipeline results file not found at {path}. Run src/handoff_pipeline.py first."
        )

    payload = load_json(path, default=[])
    if not isinstance(payload, list):
        raise ValueError("Pipeline results must be a JSON list.")
    return payload


def load_existing_evaluation_results(path: str) -> dict[str, dict[str, Any]]:
    payload = load_json(path, default=[])
    if not payload:
        return {}
    if not isinstance(payload, list):
        raise ValueError("Existing evaluation results must be a JSON list.")

    return {
        result["task_id"]: result
        for result in payload
        if isinstance(result, dict) and "task_id" in result
    }


def _evaluation_record_complete(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False

    developer = record.get("developer") or {}
    baseline = record.get("baseline") or {}
    experimental = record.get("experimental") or {}
    if "correctness" not in developer:
        return False
    if not {"correctness", "adherence", "joint_outcome"}.issubset(baseline):
        return False
    if not {"correctness", "adherence", "joint_outcome"}.issubset(experimental):
        return False

    for hop_key in ("baseline_hops", "experimental_hops"):
        for hop in record.get(hop_key) or []:
            if not {"correctness", "adherence", "joint_outcome"}.issubset(hop):
                return False

    return True


def _ordered_evaluation_results(
    pipeline_results: list[dict[str, Any]],
    by_task_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [by_task_id[item["task_id"]] for item in pipeline_results if item["task_id"] in by_task_id]


def _safe_average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _constraint_type(poison_constraint: str) -> str:
    if ":" not in poison_constraint:
        return poison_constraint.strip()
    return poison_constraint.split(":", 1)[0].strip()


def _iterative_constructs_present(tree: ast.AST) -> bool:
    iterative_nodes = (
        ast.For,
        ast.While,
        ast.AsyncFor,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
    )
    return any(isinstance(node, iterative_nodes) for node in ast.walk(tree))


def _recursive_function_names(tree: ast.AST) -> set[str]:
    recursive_names: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            called_names = {
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            if node.name in called_names:
                recursive_names.add(node.name)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            called_names = {
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            if node.name in called_names:
                recursive_names.add(node.name)
            self.generic_visit(node)

    Visitor().visit(tree)
    return recursive_names


def _has_nested_loops(tree: ast.AST) -> bool:
    loop_nodes = (ast.For, ast.While, ast.AsyncFor)

    def visit(node: ast.AST, depth: int = 0) -> bool:
        next_depth = depth + 1 if isinstance(node, loop_nodes) else depth
        if next_depth >= 2:
            return True
        return any(visit(child, next_depth) for child in ast.iter_child_nodes(node))

    return visit(tree)


def _sort_operations_present(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"sorted"}:
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"sort"}:
                return True
    return False


def _expensive_loop_calls_present(tree: ast.AST) -> bool:
    expensive_methods = {"count", "index"}
    loop_nodes = (ast.For, ast.While, ast.AsyncFor)

    def visit(node: ast.AST, inside_loop: bool = False) -> bool:
        current_inside_loop = inside_loop or isinstance(node, loop_nodes)
        if current_inside_loop and isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in expensive_methods:
                return True
        return any(visit(child, current_inside_loop) for child in ast.iter_child_nodes(node))

    return visit(tree)


def _branching_recursion_present(tree: ast.AST) -> bool:
    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            calls_to_self = 0
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == node.name:
                    calls_to_self += 1
            if calls_to_self >= 2:
                self.found = True
                return
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            calls_to_self = 0
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == node.name:
                    calls_to_self += 1
            if calls_to_self >= 2:
                self.found = True
                return
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(tree)
    return visitor.found


def _evaluate_structural_constraint(code: str) -> dict[str, Any]:
    if not code or not code.strip():
        return {
            "adheres_to_constraint": False,
            "reasoning": "No candidate code was available for constraint evaluation.",
            "method": "deterministic_ast",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "adheres_to_constraint": False,
            "reasoning": f"Could not parse candidate code: {exc}",
            "method": "deterministic_ast",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }

    recursive_names = _recursive_function_names(tree)
    has_iteration = _iterative_constructs_present(tree)

    if not recursive_names:
        return {
            "adheres_to_constraint": False,
            "reasoning": "No recursive function call was detected in the submitted code.",
            "method": "deterministic_ast",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }
    if has_iteration:
        return {
            "adheres_to_constraint": False,
            "reasoning": "The submitted code contains an iterative loop or comprehension.",
            "method": "deterministic_ast",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }
    return {
        "adheres_to_constraint": True,
        "reasoning": "A recursive function was detected and no iterative loops or comprehensions were found.",
        "method": "deterministic_ast",
        "prompt": None,
        "raw_response_text": None,
        "judge_usage": None,
        "parse_error": None,
    }


def _evaluate_efficiency_constraint(code: str) -> dict[str, Any]:
    if not code or not code.strip():
        return {
            "adheres_to_constraint": False,
            "reasoning": "No candidate code was available for constraint evaluation.",
            "method": "deterministic_static_heuristic",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "adheres_to_constraint": False,
            "reasoning": f"Could not parse candidate code: {exc}",
            "method": "deterministic_static_heuristic",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }

    if _sort_operations_present(tree):
        return {
            "adheres_to_constraint": False,
            "reasoning": "Detected a sorting operation, which is typically O(n log n), not O(n).",
            "method": "deterministic_static_heuristic",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }
    if _has_nested_loops(tree):
        return {
            "adheres_to_constraint": False,
            "reasoning": "Detected nested iterative loops, which strongly suggests superlinear complexity.",
            "method": "deterministic_static_heuristic",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }
    if _expensive_loop_calls_present(tree):
        return {
            "adheres_to_constraint": False,
            "reasoning": "Detected repeated linear-time list operations inside a loop.",
            "method": "deterministic_static_heuristic",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }
    if _branching_recursion_present(tree):
        return {
            "adheres_to_constraint": False,
            "reasoning": "Detected multiple self-calls in the same function, suggesting superlinear recursion.",
            "method": "deterministic_static_heuristic",
            "prompt": None,
            "raw_response_text": None,
            "judge_usage": None,
            "parse_error": None,
        }
    return {
        "adheres_to_constraint": True,
        "reasoning": "No obvious superlinear control-flow pattern was detected.",
        "method": "deterministic_static_heuristic",
        "prompt": None,
        "raw_response_text": None,
        "judge_usage": None,
        "parse_error": None,
    }


def _evaluation_log_writer(log_path: str) -> Any:
    def _writer(record: dict[str, Any]) -> None:
        append_jsonl(log_path, record)

    return _writer


def _evaluate_constraint(
    judge: JudgeAgent,
    *,
    code: str,
    poison_constraint: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    constraint_type = _constraint_type(poison_constraint)
    if constraint_type == "Negative":
        judge_result = judge.evaluate(code, poison_constraint, context=context)
        return {
            "adheres_to_constraint": judge_result.decision.adheres_to_constraint,
            "reasoning": judge_result.decision.reasoning,
            "method": "llm_judge",
            "prompt": judge_result.invocation.prompt,
            "raw_response_text": judge_result.invocation.raw_text,
            "judge_usage": judge_result.invocation.usage_dict(),
            "parse_error": judge_result.parse_error,
        }
    if constraint_type == "Structural":
        return _evaluate_structural_constraint(code)
    if constraint_type == "Efficiency":
        return _evaluate_efficiency_constraint(code)
    return {
        "adheres_to_constraint": False,
        "reasoning": f"Unknown constraint type: {constraint_type}",
        "method": "unsupported_constraint_type",
        "prompt": None,
        "raw_response_text": None,
        "judge_usage": None,
        "parse_error": None,
    }


def _correctness_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    pass_flags = [bool(item["correctness"]["passed"]) for item in records]
    pass_count = sum(1 for flag in pass_flags if flag)
    task_count = len(records)
    fail_count = task_count - pass_count
    correctness_rate = (pass_count / task_count) if task_count else 0.0
    durations = [float(item["correctness"].get("duration_seconds", 0.0)) for item in records]

    return {
        "task_count": task_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "correctness_rate": round(correctness_rate, 4),
        "correctness_percent": round(correctness_rate * 100.0, 2),
        "average_correctness_duration_seconds": _safe_average(durations),
    }


def _adherence_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    pass_flags = [bool(item["adherence"]["adheres_to_constraint"]) for item in records]
    pass_count = sum(1 for flag in pass_flags if flag)
    task_count = len(records)
    fail_count = task_count - pass_count
    adherence_rate = (pass_count / task_count) if task_count else 0.0

    return {
        "task_count": task_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "constraint_adherence_rate": round(adherence_rate, 4),
        "constraint_adherence_percent": round(adherence_rate * 100.0, 2),
    }


def _token_summary(records: list[dict[str, Any]], usage_key: str = "usage") -> dict[str, Any]:
    def _usage(item: dict[str, Any]) -> dict[str, Any]:
        value = item.get(usage_key)
        if isinstance(value, dict):
            return value
        return {}

    input_tokens = [int(_usage(item).get("input_tokens", 0) or 0) for item in records]
    output_tokens = [int(_usage(item).get("output_tokens", 0) or 0) for item in records]
    total_tokens = [int(_usage(item).get("total_tokens", 0) or 0) for item in records]

    return {
        "average_input_tokens": _safe_average([float(value) for value in input_tokens]),
        "average_output_tokens": _safe_average([float(value) for value in output_tokens]),
        "average_total_tokens": _safe_average([float(value) for value in total_tokens]),
        "total_input_tokens": sum(input_tokens),
        "total_output_tokens": sum(output_tokens),
        "total_tokens": sum(total_tokens),
    }


def _joint_outcome(correct: bool, adherent: bool) -> str:
    if correct and adherent:
        return "correct_and_adherent"
    if correct and not adherent:
        return "correct_not_adherent"
    if not correct and adherent:
        return "incorrect_adherent"
    return "incorrect_not_adherent"


def _joint_outcome_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["joint_outcome"] for item in records)
    total = len(records)
    return {
        "counts": {label: int(counts.get(label, 0)) for label in JOINT_OUTCOME_LABELS},
        "percents": {
            label: round((counts.get(label, 0) / total) * 100.0, 2) if total else 0.0
            for label in JOINT_OUTCOME_LABELS
        },
    }


def _build_condition_records(
    evaluation_records: list[dict[str, Any]],
    condition: str,
) -> list[dict[str, Any]]:
    return [item[condition] for item in evaluation_records]


def _build_group_by_constraint_type(
    evaluation_records: list[dict[str, Any]],
    condition: str,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evaluation_records:
        grouped.setdefault(item["constraint_type"], []).append(item[condition])

    summary: dict[str, Any] = {}
    for constraint_type, condition_records in grouped.items():
        summary[constraint_type] = {
            "correctness": _correctness_summary(condition_records),
            "tokens": _token_summary(condition_records),
        }
        if condition in {"baseline", "experimental"}:
            summary[constraint_type]["adherence"] = _adherence_summary(condition_records)
            summary[constraint_type]["joint_outcomes"] = _joint_outcome_summary(condition_records)
    return summary


def _evaluate_variant(
    *,
    code: str,
    poison_constraint: str,
    test_code: str,
    entry_point: str,
    judge: JudgeAgent,
    context: dict[str, Any],
) -> dict[str, Any]:
    correctness = evaluate_code_correctness(
        code=code or "",
        test_code=test_code or "",
        entry_point=entry_point or "",
        python_executable=sys.executable,
    )
    adherence = _evaluate_constraint(
        judge,
        code=code or "",
        poison_constraint=poison_constraint,
        context=context,
    )
    return {
        "correctness": correctness,
        "adherence": adherence,
        "joint_outcome": _joint_outcome(
            bool(correctness["passed"]),
            bool(adherence["adheres_to_constraint"]),
        ),
    }


def _evaluate_hops(
    *,
    hops: list[dict[str, Any]],
    judge: JudgeAgent,
    poison_constraint: str,
    test_code: str,
    entry_point: str,
    run_id: str,
    task_id: str,
    constraint_type: str,
    condition: str,
) -> list[dict[str, Any]]:
    evaluated_hops: list[dict[str, Any]] = []
    for hop in hops:
        evaluated_hop = copy.deepcopy(hop)
        evaluated_hop.update(
            _evaluate_variant(
                code=hop.get("final_code") or "",
                poison_constraint=poison_constraint,
                test_code=test_code,
                entry_point=entry_point,
                judge=judge,
                context={
                    "run_id": run_id,
                    "task_id": task_id,
                    "stage": "evaluation",
                    "condition": condition,
                    "phase": f"{condition}_hop_{hop.get('hop_number', 'unknown')}_adherence",
                    "constraint_type": constraint_type,
                    "hop_number": hop.get("hop_number"),
                },
            )
        )
        evaluated_hops.append(evaluated_hop)
    return evaluated_hops


def _build_multihop_summary(evaluation_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    max_hops = max(
        max((len(item.get("baseline_hops", [])) for item in evaluation_records), default=0),
        max((len(item.get("experimental_hops", [])) for item in evaluation_records), default=0),
    )
    if max_hops == 0:
        return None

    summary: dict[str, Any] = {}
    for condition in ("baseline", "experimental"):
        condition_summary: dict[str, Any] = {}
        for hop_index in range(max_hops):
            hop_records = [
                item[f"{condition}_hops"][hop_index]
                for item in evaluation_records
                if len(item.get(f"{condition}_hops", [])) > hop_index
            ]
            if not hop_records:
                continue
            condition_summary[f"hop_{hop_index + 1}"] = {
                "correctness": _correctness_summary(hop_records),
                "adherence": _adherence_summary(hop_records),
                "tokens": _token_summary(hop_records),
                "joint_outcomes": _joint_outcome_summary(hop_records),
            }
        summary[condition] = condition_summary
    return summary


def _per_task_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": record["task_id"],
        "constraint_type": record["constraint_type"],
        "selection_score": record.get("selection_score"),
        "developer_correct": record["developer"]["correctness"]["passed"],
        "developer_status": record["developer"]["correctness"]["status"],
        "baseline_correct": record["baseline"]["correctness"]["passed"],
        "baseline_adherent": record["baseline"]["adherence"]["adheres_to_constraint"],
        "baseline_joint_outcome": record["baseline"]["joint_outcome"],
        "baseline_total_tokens": record["baseline"]["usage"].get("total_tokens", 0) if record["baseline"]["usage"] else 0,
        "experimental_correct": record["experimental"]["correctness"]["passed"],
        "experimental_adherent": record["experimental"]["adherence"]["adheres_to_constraint"],
        "experimental_joint_outcome": record["experimental"]["joint_outcome"],
        "experimental_total_tokens": record["experimental"]["usage"].get("total_tokens", 0)
        if record["experimental"]["usage"]
        else 0,
        "baseline_method": record["baseline"]["adherence"]["method"],
        "experimental_method": record["experimental"]["adherence"]["method"],
    }


def _write_summary_tables(summary: dict[str, Any], evaluation_records: list[dict[str, Any]], artifacts: RunArtifacts) -> None:
    overall_rows = [
        {
            "condition": "developer",
            "task_count": summary["developer"]["correctness"]["task_count"],
            "correctness_percent": summary["developer"]["correctness"]["correctness_percent"],
            "adherence_percent": "",
            "average_total_tokens": summary["developer"]["tokens"]["average_total_tokens"],
        },
        {
            "condition": "baseline",
            "task_count": summary["baseline"]["correctness"]["task_count"],
            "correctness_percent": summary["baseline"]["correctness"]["correctness_percent"],
            "adherence_percent": summary["baseline"]["adherence"]["constraint_adherence_percent"],
            "average_total_tokens": summary["baseline"]["tokens"]["average_total_tokens"],
        },
        {
            "condition": "experimental",
            "task_count": summary["experimental"]["correctness"]["task_count"],
            "correctness_percent": summary["experimental"]["correctness"]["correctness_percent"],
            "adherence_percent": summary["experimental"]["adherence"]["constraint_adherence_percent"],
            "average_total_tokens": summary["experimental"]["tokens"]["average_total_tokens"],
        },
    ]
    overall_fields = ["condition", "task_count", "correctness_percent", "adherence_percent", "average_total_tokens"]
    write_csv(os.path.join(artifacts.tables_dir, "overall_summary.csv"), overall_fields, overall_rows)
    write_markdown_table(os.path.join(artifacts.tables_dir, "overall_summary.md"), overall_fields, overall_rows)

    constraint_rows: list[dict[str, Any]] = []
    for condition in ("developer", "baseline", "experimental"):
        for constraint_type, metrics in summary["by_constraint_type"][condition].items():
            row = {
                "condition": condition,
                "constraint_type": constraint_type,
                "task_count": metrics["correctness"]["task_count"],
                "correctness_percent": metrics["correctness"]["correctness_percent"],
                "average_total_tokens": metrics["tokens"]["average_total_tokens"],
            }
            if condition in {"baseline", "experimental"}:
                row["adherence_percent"] = metrics["adherence"]["constraint_adherence_percent"]
            else:
                row["adherence_percent"] = ""
            constraint_rows.append(row)
    constraint_fields = [
        "condition",
        "constraint_type",
        "task_count",
        "correctness_percent",
        "adherence_percent",
        "average_total_tokens",
    ]
    write_csv(os.path.join(artifacts.tables_dir, "constraint_type_summary.csv"), constraint_fields, constraint_rows)
    write_markdown_table(
        os.path.join(artifacts.tables_dir, "constraint_type_summary.md"),
        constraint_fields,
        constraint_rows,
    )

    token_rows = [
        {"condition": "developer", **summary["developer"]["tokens"]},
        {"condition": "baseline", **summary["baseline"]["tokens"]},
        {"condition": "experimental", **summary["experimental"]["tokens"]},
    ]
    token_fields = [
        "condition",
        "average_input_tokens",
        "average_output_tokens",
        "average_total_tokens",
        "total_input_tokens",
        "total_output_tokens",
        "total_tokens",
    ]
    write_csv(os.path.join(artifacts.tables_dir, "token_summary.csv"), token_fields, token_rows)
    write_markdown_table(os.path.join(artifacts.tables_dir, "token_summary.md"), token_fields, token_rows)

    joint_rows: list[dict[str, Any]] = []
    for condition in ("baseline", "experimental"):
        for label in JOINT_OUTCOME_LABELS:
            joint_rows.append(
                {
                    "condition": condition,
                    "joint_outcome": label,
                    "count": summary[condition]["joint_outcomes"]["counts"][label],
                    "percent": summary[condition]["joint_outcomes"]["percents"][label],
                }
            )
    joint_fields = ["condition", "joint_outcome", "count", "percent"]
    write_csv(os.path.join(artifacts.tables_dir, "joint_outcomes.csv"), joint_fields, joint_rows)
    write_markdown_table(os.path.join(artifacts.tables_dir, "joint_outcomes.md"), joint_fields, joint_rows)

    multihop_summary = summary.get("multihop")
    if multihop_summary:
        multihop_rows: list[dict[str, Any]] = []
        for condition in ("baseline", "experimental"):
            for hop_label, metrics in multihop_summary.get(condition, {}).items():
                multihop_rows.append(
                    {
                        "condition": condition,
                        "hop": hop_label,
                        "task_count": metrics["correctness"]["task_count"],
                        "correctness_percent": metrics["correctness"]["correctness_percent"],
                        "adherence_percent": metrics["adherence"]["constraint_adherence_percent"],
                        "average_total_tokens": metrics["tokens"]["average_total_tokens"],
                    }
                )
        multihop_fields = [
            "condition",
            "hop",
            "task_count",
            "correctness_percent",
            "adherence_percent",
            "average_total_tokens",
        ]
        write_csv(os.path.join(artifacts.tables_dir, "multihop_summary.csv"), multihop_fields, multihop_rows)
        write_markdown_table(
            os.path.join(artifacts.tables_dir, "multihop_summary.md"),
            multihop_fields,
            multihop_rows,
        )

    per_task_rows = [_per_task_row(record) for record in evaluation_records]
    per_task_fields = list(per_task_rows[0].keys()) if per_task_rows else [
        "task_id",
        "constraint_type",
        "selection_score",
        "developer_correct",
        "developer_status",
        "baseline_correct",
        "baseline_adherent",
        "baseline_joint_outcome",
        "baseline_total_tokens",
        "experimental_correct",
        "experimental_adherent",
        "experimental_joint_outcome",
        "experimental_total_tokens",
        "baseline_method",
        "experimental_method",
    ]
    write_csv(os.path.join(artifacts.tables_dir, "per_task_results.csv"), per_task_fields, per_task_rows)


def _plot_or_note_empty(ax: Any, *, title: str, note: str) -> None:
    ax.set_title(title)
    ax.text(0.5, 0.5, note, ha="center", va="center", transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])


def _generate_figures(summary: dict[str, Any], artifacts: RunArtifacts) -> dict[str, Any]:
    figure_metadata: dict[str, Any] = {}

    constraint_types = ["Negative", "Structural", "Efficiency"]
    baseline_vals = [
        summary["by_constraint_type"]["baseline"].get(constraint_type, {})
        .get("adherence", {})
        .get("constraint_adherence_percent", 0.0)
        for constraint_type in constraint_types
    ]
    experimental_vals = [
        summary["by_constraint_type"]["experimental"].get(constraint_type, {})
        .get("adherence", {})
        .get("constraint_adherence_percent", 0.0)
        for constraint_type in constraint_types
    ]
    adherence_path = os.path.join(artifacts.figures_dir, "adherence_by_constraint_type.png")
    fig, ax = plt.subplots(figsize=(9, 5))
    x_positions = range(len(constraint_types))
    width = 0.35
    ax.bar([value - width / 2 for value in x_positions], baseline_vals, width=width, label="Baseline")
    ax.bar([value + width / 2 for value in x_positions], experimental_vals, width=width, label="Experimental")
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(constraint_types)
    ax.set_ylabel("Constraint Adherence (%)")
    ax.set_title("Constraint Adherence by Constraint Type")
    ax.legend()
    ax.set_ylim(0, 100)
    fig.tight_layout()
    fig.savefig(adherence_path, dpi=200)
    plt.close(fig)
    figure_metadata["adherence_by_constraint_type.png"] = {
        "title": "Constraint Adherence by Constraint Type",
        "caption": "Grouped bar chart comparing baseline and experimental adherence percentages for each constraint type.",
    }

    token_path = os.path.join(artifacts.figures_dir, "token_usage_boxplot.png")
    fig, ax = plt.subplots(figsize=(8, 5))
    token_data = [
        summary["token_distributions"]["baseline_total_tokens"],
        summary["token_distributions"]["experimental_total_tokens"],
    ]
    if any(token_data):
        ax.boxplot(token_data, tick_labels=["Baseline", "Experimental"])
        ax.set_ylabel("Total Tokens per Task")
        ax.set_title("Token Usage Distribution")
    else:
        _plot_or_note_empty(ax, title="Token Usage Distribution", note="No token data available.")
    fig.tight_layout()
    fig.savefig(token_path, dpi=200)
    plt.close(fig)
    figure_metadata["token_usage_boxplot.png"] = {
        "title": "Token Usage Distribution",
        "caption": "Box-and-whisker plot comparing per-task total token usage for baseline and experimental maintainer conditions.",
    }

    joint_path = os.path.join(artifacts.figures_dir, "joint_outcomes.png")
    fig, ax = plt.subplots(figsize=(10, 5))
    baseline_counts = [summary["baseline"]["joint_outcomes"]["counts"][label] for label in JOINT_OUTCOME_LABELS]
    experimental_counts = [summary["experimental"]["joint_outcomes"]["counts"][label] for label in JOINT_OUTCOME_LABELS]
    x_positions = range(len(JOINT_OUTCOME_LABELS))
    ax.bar([value - width / 2 for value in x_positions], baseline_counts, width=width, label="Baseline")
    ax.bar([value + width / 2 for value in x_positions], experimental_counts, width=width, label="Experimental")
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels([label.replace("_", "\n") for label in JOINT_OUTCOME_LABELS])
    ax.set_ylabel("Task Count")
    ax.set_title("Joint Correctness and Constraint Adherence Outcomes")
    ax.legend()
    fig.tight_layout()
    fig.savefig(joint_path, dpi=200)
    plt.close(fig)
    figure_metadata["joint_outcomes.png"] = {
        "title": "Joint Correctness and Constraint Adherence Outcomes",
        "caption": "Grouped bar chart showing counts of tasks in each joint correctness/adherence outcome for baseline and experimental conditions.",
    }

    multihop_summary = summary.get("multihop")
    if multihop_summary:
        multihop_path = os.path.join(artifacts.figures_dir, "multihop_adherence_by_hop.png")
        fig, ax = plt.subplots(figsize=(8, 5))
        baseline_hops = multihop_summary.get("baseline", {})
        experimental_hops = multihop_summary.get("experimental", {})
        hop_labels = sorted(
            set(baseline_hops.keys()) | set(experimental_hops.keys()),
            key=lambda label: int(label.split("_")[-1]),
        )
        x_positions = range(len(hop_labels))
        baseline_vals = [
            baseline_hops.get(label, {}).get("adherence", {}).get("constraint_adherence_percent", 0.0)
            for label in hop_labels
        ]
        experimental_vals = [
            experimental_hops.get(label, {}).get("adherence", {}).get("constraint_adherence_percent", 0.0)
            for label in hop_labels
        ]
        ax.plot(list(x_positions), baseline_vals, marker="o", label="Baseline")
        ax.plot(list(x_positions), experimental_vals, marker="o", label="Experimental")
        ax.set_xticks(list(x_positions))
        ax.set_xticklabels(hop_labels)
        ax.set_ylim(0, 100)
        ax.set_ylabel("Constraint Adherence (%)")
        ax.set_title("Multi-Hop Constraint Adherence by Hop")
        ax.legend()
        fig.tight_layout()
        fig.savefig(multihop_path, dpi=200)
        plt.close(fig)
        figure_metadata["multihop_adherence_by_hop.png"] = {
            "title": "Multi-Hop Constraint Adherence by Hop",
            "caption": "Line chart showing final adherence at each maintainer hop for the baseline and experimental multi-hop pipelines.",
        }

    write_json(artifacts.figure_metadata_path, figure_metadata)
    return figure_metadata


def _select_example(
    evaluation_records: list[dict[str, Any]],
    predicate: Any,
    *,
    exclude_task_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    candidates = [
        record
        for record in evaluation_records
        if predicate(record) and (exclude_task_ids is None or record["task_id"] not in exclude_task_ids)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (float(item.get("selection_score") or 0.0), item["task_id"]), reverse=True)
    return candidates[0]


def _write_example_markdown(path: str, title: str, record: dict[str, Any] | None) -> None:
    if record is None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"# {title}\n\nNo example for this category was available in the evaluated run.\n")
        return

    lines = [
        f"# {title}",
        "",
        f"- Task ID: `{record['task_id']}`",
        f"- Constraint Type: `{record['constraint_type']}`",
        f"- Poison Constraint: {record['poison_constraint']}",
        f"- Baseline Joint Outcome: `{record['baseline']['joint_outcome']}`",
        f"- Experimental Joint Outcome: `{record['experimental']['joint_outcome']}`",
        "",
        "## Task Prompt",
        "```python",
        record["task_prompt"],
        "```",
        "",
        "## Handoff Receipt",
        "```json",
        record.get("handoff_receipt_json") or "",
        "```",
        "",
        "## Baseline Final Code",
        "```python",
        record["baseline"].get("final_code") or "",
        "```",
        "",
        "## Baseline Evaluation",
        f"- Correctness: `{record['baseline']['correctness']['status']}`",
        f"- Adherence: `{record['baseline']['adherence']['adheres_to_constraint']}`",
        f"- Reasoning: {record['baseline']['adherence']['reasoning']}",
        "",
        "## Experimental Final Code",
        "```python",
        record["experimental"].get("final_code") or "",
        "```",
        "",
        "## Experimental Evaluation",
        f"- Correctness: `{record['experimental']['correctness']['status']}`",
        f"- Adherence: `{record['experimental']['adherence']['adheres_to_constraint']}`",
        f"- Reasoning: {record['experimental']['adherence']['reasoning']}",
        "",
    ]

    if record.get("baseline_hops"):
        lines.extend(["## Baseline Hops", ""])
        for hop in record["baseline_hops"]:
            lines.extend(
                [
                    f"### Hop {hop.get('hop_number')}",
                    "```python",
                    hop.get("final_code") or "",
                    "```",
                    f"- Correctness: `{hop['correctness']['status']}`",
                    f"- Adherence: `{hop['adherence']['adheres_to_constraint']}`",
                    f"- Joint Outcome: `{hop['joint_outcome']}`",
                    "",
                ]
            )

    if record.get("experimental_hops"):
        lines.extend(["## Experimental Hops", ""])
        for hop in record["experimental_hops"]:
            lines.extend(
                [
                    f"### Hop {hop.get('hop_number')}",
                    "```python",
                    hop.get("final_code") or "",
                    "```",
                    f"- Correctness: `{hop['correctness']['status']}`",
                    f"- Adherence: `{hop['adherence']['adheres_to_constraint']}`",
                    f"- Joint Outcome: `{hop['joint_outcome']}`",
                    "",
                ]
            )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _write_examples(evaluation_records: list[dict[str, Any]], artifacts: RunArtifacts) -> list[str]:
    chosen_ids: set[str] = set()
    example_specs = [
        (
            "experimental_win.md",
            "Experimental Win",
            lambda item: (
                item["experimental"]["joint_outcome"] == "correct_and_adherent"
                and item["baseline"]["joint_outcome"] != "correct_and_adherent"
            ),
        ),
        (
            "baseline_win.md",
            "Baseline Win",
            lambda item: (
                item["baseline"]["joint_outcome"] == "correct_and_adherent"
                and item["experimental"]["joint_outcome"] != "correct_and_adherent"
            ),
        ),
        (
            "both_fail.md",
            "Both Fail",
            lambda item: (
                item["baseline"]["joint_outcome"] != "correct_and_adherent"
                and item["experimental"]["joint_outcome"] != "correct_and_adherent"
            ),
        ),
        (
            "baseline_surprise_success.md",
            "Baseline Surprise Success",
            lambda item: bool(item["baseline"]["adherence"]["adheres_to_constraint"]),
        ),
    ]

    written_paths: list[str] = []
    for filename, title, predicate in example_specs:
        record = _select_example(evaluation_records, predicate, exclude_task_ids=chosen_ids)
        if record is not None:
            chosen_ids.add(record["task_id"])
        destination = os.path.join(artifacts.examples_dir, filename)
        _write_example_markdown(destination, title, record)
        written_paths.append(destination)
    return written_paths


def _write_study_summary(summary: dict[str, Any], artifacts: RunArtifacts, figure_metadata: dict[str, Any]) -> None:
    def rel(path: str) -> str:
        return os.path.relpath(path, artifacts.run_dir).replace("\\", "/")

    lines = [
        f"# Study Summary: {summary['run_id']}",
        "",
        f"- Experiment Name: {summary['experiment_name']}",
        f"- Experiment Type: `{summary['experiment_type']}`",
        f"- Generated At (UTC): `{summary['generated_at_utc']}`",
        f"- Task Count: `{summary['task_count']}`",
        "",
        "## Key Metrics",
        "",
        "| Condition | Correctness % | Adherence % | Avg Total Tokens |",
        "| --- | --- | --- | --- |",
        f"| Developer | {summary['developer']['correctness']['correctness_percent']} |  | {summary['developer']['tokens']['average_total_tokens']} |",
        f"| Baseline | {summary['baseline']['correctness']['correctness_percent']} | {summary['baseline']['adherence']['constraint_adherence_percent']} | {summary['baseline']['tokens']['average_total_tokens']} |",
        f"| Experimental | {summary['experimental']['correctness']['correctness_percent']} | {summary['experimental']['adherence']['constraint_adherence_percent']} | {summary['experimental']['tokens']['average_total_tokens']} |",
        "",
        "## Artifact Guide",
        "",
        f"- [Manifest]({rel(artifacts.manifest_path)})",
        f"- [Experiment Config]({rel(artifacts.experiment_config_path)})",
        f"- [Curated Task Snapshot]({rel(artifacts.curated_snapshot_path)})",
        f"- [Pipeline Results]({rel(artifacts.pipeline_results_path)})",
        f"- [Evaluation Results]({rel(artifacts.evaluation_results_path)})",
        f"- [Final Metrics]({rel(artifacts.final_metrics_path)})",
        f"- [Pipeline LLM Logs]({rel(artifacts.pipeline_llm_log_path)})",
        f"- [Evaluation LLM Logs]({rel(artifacts.evaluation_llm_log_path)})",
        f"- [Overall Summary Table]({rel(os.path.join(artifacts.tables_dir, 'overall_summary.md'))})",
        f"- [Per-Task Results CSV]({rel(os.path.join(artifacts.tables_dir, 'per_task_results.csv'))})",
        "",
        "## Figures",
        "",
    ]

    for filename, metadata in figure_metadata.items():
        lines.append(f"- [{metadata['title']}]({rel(os.path.join(artifacts.figures_dir, filename))})")
        lines.append(f"  {metadata['caption']}")

    if summary.get("multihop"):
        lines.extend(
            [
                "",
                "## Multi-Hop Artifacts",
                "",
                f"- [Multi-Hop Summary Table]({rel(os.path.join(artifacts.tables_dir, 'multihop_summary.md'))})",
                f"- [Multi-Hop Hop Figure]({rel(os.path.join(artifacts.figures_dir, 'multihop_adherence_by_hop.png'))})",
            ]
        )

    lines.extend(
        [
            "",
            "## Example Pack",
            "",
            f"- [Experimental Win]({rel(os.path.join(artifacts.examples_dir, 'experimental_win.md'))})",
            f"- [Baseline Win]({rel(os.path.join(artifacts.examples_dir, 'baseline_win.md'))})",
            f"- [Both Fail]({rel(os.path.join(artifacts.examples_dir, 'both_fail.md'))})",
            f"- [Baseline Surprise Success]({rel(os.path.join(artifacts.examples_dir, 'baseline_surprise_success.md'))})",
            "",
            "## Notes",
            "",
            "- The evaluator uses deterministic correctness checks for all three code variants.",
            "- Constraint adherence uses deterministic AST/static heuristics for Structural and Efficiency constraints and the Gemini judge for Negative constraints.",
            "",
        ]
    )

    with open(artifacts.study_summary_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_manual_screenshot_checklist(artifacts: RunArtifacts) -> None:
    lines = [
        "# Manual Screenshot Checklist",
        "",
        "- [ ] Folder tree showing the run artifact layout under `results/runs/<run_id>/`",
        "- [ ] Snippet of `inputs/curated_tasks_snapshot.json` showing a tagged HumanEval task",
        "- [ ] Snippet of `outputs/pipeline_results.json` showing the `handoff_receipt` and both conditions",
        "- [ ] Snippet of `logs/pipeline_llm_calls.jsonl` showing prompt/response provenance",
        "- [ ] `figures/adherence_by_constraint_type.png`",
        "- [ ] `figures/token_usage_boxplot.png`",
        "- [ ] `figures/joint_outcomes.png`",
        "- [ ] One example markdown file from the `examples/` directory",
        "",
        "Avoid screenshots of secret material such as API keys.",
        "",
    ]
    with open(artifacts.manual_screenshot_checklist_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def evaluate_pipeline_results(
    *,
    run_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    resolved_run_id = run_id or find_latest_run_id()
    artifacts = RunArtifacts.for_run(resolved_run_id)
    artifacts.ensure_directories()
    initialize_log_file(artifacts.evaluation_llm_log_path, overwrite=False)

    update_manifest(
        artifacts.manifest_path,
        {
            "status": {"evaluation": "running"},
            "evaluation_started_at_utc": utc_now_iso(),
        },
    )

    pipeline_results = load_pipeline_results(artifacts.pipeline_results_path)
    existing_evaluation_by_task = load_existing_evaluation_results(artifacts.evaluation_results_path)
    evaluation_logger = _evaluation_log_writer(artifacts.evaluation_llm_log_path)
    judge = JudgeAgent(llm_logger=evaluation_logger)

    _status_print(
        f"Evaluation started for {resolved_run_id} with {len(pipeline_results)} pipeline records."
    )

    evaluation_records_by_task: dict[str, dict[str, Any]] = {}

    for index, record in enumerate(pipeline_results, start=1):
        task_id = record["task_id"]
        existing_evaluation = existing_evaluation_by_task.get(task_id)
        if existing_evaluation and _evaluation_record_complete(existing_evaluation):
            evaluation_records_by_task[task_id] = existing_evaluation
            _status_print(f"[{index}/{len(pipeline_results)}] Reusing completed evaluation for {task_id}.")
            continue

        _status_print(f"[{index}/{len(pipeline_results)}] Evaluating {task_id}.")
        merged = copy.deepcopy(record)
        poison_constraint = record["poison_constraint"]
        constraint_type = record.get("constraint_type", _constraint_type(poison_constraint))
        try:
            developer_correctness = evaluate_code_correctness(
                code=record["developer"].get("initial_code") or "",
                test_code=record.get("test") or "",
                entry_point=record.get("entry_point") or "",
                python_executable=sys.executable,
            )
            baseline_variant = _evaluate_variant(
                code=record["baseline"].get("final_code") or "",
                poison_constraint=poison_constraint,
                test_code=record.get("test") or "",
                entry_point=record.get("entry_point") or "",
                judge=judge,
                context={
                    "run_id": resolved_run_id,
                    "task_id": task_id,
                    "stage": "evaluation",
                    "condition": "baseline",
                    "phase": "baseline_adherence",
                    "constraint_type": constraint_type,
                },
            )
            experimental_variant = _evaluate_variant(
                code=record["experimental"].get("final_code") or "",
                poison_constraint=poison_constraint,
                test_code=record.get("test") or "",
                entry_point=record.get("entry_point") or "",
                judge=judge,
                context={
                    "run_id": resolved_run_id,
                    "task_id": task_id,
                    "stage": "evaluation",
                    "condition": "experimental",
                    "phase": "experimental_adherence",
                    "constraint_type": constraint_type,
                },
            )

            merged["constraint_type"] = constraint_type
            merged["developer"]["correctness"] = developer_correctness
            merged["baseline"].update(baseline_variant)
            merged["experimental"].update(experimental_variant)
            if record.get("baseline_hops"):
                merged["baseline_hops"] = _evaluate_hops(
                    hops=record.get("baseline_hops", []),
                    judge=judge,
                    poison_constraint=poison_constraint,
                    test_code=record.get("test") or "",
                    entry_point=record.get("entry_point") or "",
                    run_id=resolved_run_id,
                    task_id=task_id,
                    constraint_type=constraint_type,
                    condition="baseline",
                )
            if record.get("experimental_hops"):
                merged["experimental_hops"] = _evaluate_hops(
                    hops=record.get("experimental_hops", []),
                    judge=judge,
                    poison_constraint=poison_constraint,
                    test_code=record.get("test") or "",
                    entry_point=record.get("entry_point") or "",
                    run_id=resolved_run_id,
                    task_id=task_id,
                    constraint_type=constraint_type,
                    condition="experimental",
                )
            merged["evaluation_metadata"] = {
                "run_id": resolved_run_id,
                "evaluated_at_utc": utc_now_iso(),
                "python_executable": sys.executable,
            }
            evaluation_records_by_task[task_id] = merged
            write_json(
                artifacts.evaluation_results_path,
                _ordered_evaluation_results(pipeline_results, evaluation_records_by_task),
            )
            _status_print(f"[{index}/{len(pipeline_results)}] Saved evaluation for {task_id}.")
        except Exception:
            write_json(
                artifacts.evaluation_results_path,
                _ordered_evaluation_results(pipeline_results, evaluation_records_by_task),
            )
            _status_print(
                f"[{index}/{len(pipeline_results)}] Evaluation failed on {task_id}; "
                f"checkpointed {len(evaluation_records_by_task)} completed evaluation records."
            )
            raise

    evaluation_records = _ordered_evaluation_results(pipeline_results, evaluation_records_by_task)

    developer_records = _build_condition_records(evaluation_records, "developer")
    baseline_records = _build_condition_records(evaluation_records, "baseline")
    experimental_records = _build_condition_records(evaluation_records, "experimental")

    summary = {
        "run_id": resolved_run_id,
        "experiment_name": load_json(artifacts.manifest_path, default={}).get("experiment_name"),
        "experiment_type": load_json(artifacts.manifest_path, default={}).get("experiment_type"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task_count": len(evaluation_records),
        "token_efficiency_definition": "Average total tokens per task. Lower values indicate greater token efficiency.",
        "developer": {
            "correctness": _correctness_summary(developer_records),
            "tokens": _token_summary(developer_records),
        },
        "baseline": {
            "correctness": _correctness_summary(baseline_records),
            "adherence": _adherence_summary(baseline_records),
            "tokens": _token_summary(baseline_records),
            "joint_outcomes": _joint_outcome_summary(baseline_records),
        },
        "experimental": {
            "correctness": _correctness_summary(experimental_records),
            "adherence": _adherence_summary(experimental_records),
            "tokens": _token_summary(experimental_records),
            "joint_outcomes": _joint_outcome_summary(experimental_records),
        },
        "baseline_vs_experimental": {
            "correctness_percent_delta": round(
                _correctness_summary(experimental_records)["correctness_percent"]
                - _correctness_summary(baseline_records)["correctness_percent"],
                2,
            ),
            "adherence_percent_delta": round(
                _adherence_summary(experimental_records)["constraint_adherence_percent"]
                - _adherence_summary(baseline_records)["constraint_adherence_percent"],
                2,
            ),
            "average_total_tokens_delta": round(
                _token_summary(experimental_records)["average_total_tokens"]
                - _token_summary(baseline_records)["average_total_tokens"],
                2,
            ),
        },
        "by_constraint_type": {
            "developer": _build_group_by_constraint_type(evaluation_records, "developer"),
            "baseline": _build_group_by_constraint_type(evaluation_records, "baseline"),
            "experimental": _build_group_by_constraint_type(evaluation_records, "experimental"),
        },
        "token_distributions": {
            "developer_total_tokens": [
                int(item["usage"].get("total_tokens", 0) or 0) if item.get("usage") else 0 for item in developer_records
            ],
            "baseline_total_tokens": [
                int(item["usage"].get("total_tokens", 0) or 0) if item.get("usage") else 0 for item in baseline_records
            ],
            "experimental_total_tokens": [
                int(item["usage"].get("total_tokens", 0) or 0) if item.get("usage") else 0 for item in experimental_records
            ],
        },
        "judge_usage": judge.usage_totals(),
    }

    multihop_summary = _build_multihop_summary(evaluation_records)
    if multihop_summary is not None:
        summary["multihop"] = multihop_summary

    write_json(artifacts.evaluation_results_path, evaluation_records)
    write_json(artifacts.final_metrics_path, summary)
    write_json(FINAL_METRICS_PATH, summary)

    _write_summary_tables(summary, evaluation_records, artifacts)
    figure_metadata = _generate_figures(summary, artifacts)
    _write_examples(evaluation_records, artifacts)
    _write_study_summary(summary, artifacts, figure_metadata)
    _write_manual_screenshot_checklist(artifacts)

    update_manifest(
        artifacts.manifest_path,
        {
            "status": {"evaluation": "completed"},
            "evaluation_completed_at_utc": utc_now_iso(),
            "evaluation_summary": {
                "task_count": len(evaluation_records),
                "evaluation_results_path": artifacts.evaluation_results_path,
                "final_metrics_path": artifacts.final_metrics_path,
                "figure_metadata_path": artifacts.figure_metadata_path,
                "study_summary_path": artifacts.study_summary_path,
            },
            "summary": summary,
        },
    )
    _status_print(
        f"Evaluation completed for {resolved_run_id}; saved metrics, tables, figures, examples, and summary artifacts."
    )
    return resolved_run_id, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a run and generate paper-ready artifacts.")
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run identifier to evaluate. Defaults to the most recently modified run directory.",
    )
    args = parser.parse_args()

    resolved_run_id, summary = evaluate_pipeline_results(run_id=args.run_id)
    print(
        f"Saved final metrics for {summary['task_count']} tasks to {FINAL_METRICS_PATH} "
        f"and run {resolved_run_id}",
        flush=True,
    )


if __name__ == "__main__":
    main()
