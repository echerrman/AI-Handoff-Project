# Study Summary: run3_ablation_full

- Experiment Name: Run 3 Prompt-Only Ablation
- Experiment Type: `run3_ablation`
- Generated At (UTC): `2026-04-19T22:58:19.121422+00:00`
- Task Count: `50`

## Key Metrics

| Condition | Correctness % | Adherence % | Avg Total Tokens |
| --- | --- | --- | --- |
| Developer | 96.0 |  | 506.78 |
| Baseline | 98.0 | 32.0 | 429.48 |
| Experimental | 98.0 | 30.0 | 687.14 |

## Artifact Guide

- [Manifest](manifest.json)
- [Experiment Config](inputs/experiment_config.json)
- [Curated Task Snapshot](inputs/curated_tasks_snapshot.json)
- [Pipeline Results](outputs/pipeline_results.json)
- [Evaluation Results](outputs/evaluation_results.json)
- [Final Metrics](outputs/final_metrics.json)
- [Pipeline LLM Logs](logs/pipeline_llm_calls.jsonl)
- [Evaluation LLM Logs](logs/evaluation_llm_calls.jsonl)
- [Overall Summary Table](tables/overall_summary.md)
- [Per-Task Results CSV](tables/per_task_results.csv)

## Figures

- [Constraint Adherence by Constraint Type](figures/adherence_by_constraint_type.png)
  Grouped bar chart comparing baseline and experimental adherence percentages for each constraint type.
- [Token Usage Distribution](figures/token_usage_boxplot.png)
  Box-and-whisker plot comparing per-task total token usage for baseline and experimental maintainer conditions.
- [Joint Correctness and Constraint Adherence Outcomes](figures/joint_outcomes.png)
  Grouped bar chart showing counts of tasks in each joint correctness/adherence outcome for baseline and experimental conditions.

## Example Pack

- [Experimental Win](examples/experimental_win.md)
- [Baseline Win](examples/baseline_win.md)
- [Both Fail](examples/both_fail.md)
- [Baseline Surprise Success](examples/baseline_surprise_success.md)

## Notes

- The evaluator uses deterministic correctness checks for all three code variants.
- Constraint adherence uses deterministic AST/static heuristics for Structural and Efficiency constraints and the Gemini judge for Negative constraints.

