# Study Summary: run2_multihop_subset15

- Experiment Name: Run 2 Multi-Hop Extension
- Experiment Type: `run2_multihop`
- Generated At (UTC): `2026-04-19T19:52:08.023149+00:00`
- Task Count: `15`

## Key Metrics

| Condition | Correctness % | Adherence % | Avg Total Tokens |
| --- | --- | --- | --- |
| Developer | 93.33 |  | 538.87 |
| Baseline | 86.67 | 26.67 | 366.53 |
| Experimental | 100.0 | 73.33 | 876.93 |

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
- [Multi-Hop Constraint Adherence by Hop](figures/multihop_adherence_by_hop.png)
  Line chart showing final adherence at each maintainer hop for the baseline and experimental multi-hop pipelines.

## Multi-Hop Artifacts

- [Multi-Hop Summary Table](tables/multihop_summary.md)
- [Multi-Hop Hop Figure](figures/multihop_adherence_by_hop.png)

## Example Pack

- [Experimental Win](examples/experimental_win.md)
- [Baseline Win](examples/baseline_win.md)
- [Both Fail](examples/both_fail.md)
- [Baseline Surprise Success](examples/baseline_surprise_success.md)

## Notes

- The evaluator uses deterministic correctness checks for all three code variants.
- Constraint adherence uses deterministic AST/static heuristics for Structural and Efficiency constraints and the Gemini judge for Negative constraints.

