# Run 1 Results

## Experiment

- Run ID: `run1_core_full`
- Experiment name: Run 1 Core Two-Agent Handoff
- Experiment type: `run1_core`
- Task count: `50`

Run 1 is the core two-agent comparison:

- Baseline: maintainer sees code only
- Experimental: maintainer sees code plus the structured `HandoffReceipt`

## Completion Status

Run 1 is fully complete.

- Pipeline generation complete
- Evaluation complete
- Figures generated
- Tables generated
- Example packs generated

Key files:

- `results/runs/run1_core_full/study_summary.md`
- `results/runs/run1_core_full/outputs/final_metrics.json`
- `results/runs/run1_core_full/tables/overall_summary.md`
- `results/runs/run1_core_full/tables/per_task_results.csv`

## Main Findings

### Overall Metrics

- Developer correctness: `82.0%`
- Baseline correctness: `84.0%`
- Experimental correctness: `86.0%`
- Baseline adherence: `36.0%`
- Experimental adherence: `70.0%`
- Correctness delta, experimental minus baseline: `+2.0` points
- Adherence delta, experimental minus baseline: `+34.0` points
- Average total token delta, experimental minus baseline: `+373.68`

The main result is strong: structured handoffs substantially improved constraint adherence while also slightly improving correctness.

### Joint Outcomes

Baseline:

- Correct and adherent: `32.0%`
- Correct but not adherent: `52.0%`
- Incorrect but adherent: `4.0%`
- Incorrect and not adherent: `12.0%`

Experimental:

- Correct and adherent: `62.0%`
- Correct but not adherent: `24.0%`
- Incorrect but adherent: `8.0%`
- Incorrect and not adherent: `6.0%`

This is a useful discussion result for the paper: the structured handoff sharply increased the proportion of tasks that were both correct and constraint-adherent.

## By Constraint Type

### Baseline

- Structural: correctness `76.47%`, adherence `5.88%`
- Efficiency: correctness `87.5%`, adherence `62.5%`
- Negative: correctness `88.24%`, adherence `41.18%`

### Experimental

- Structural: correctness `88.24%`, adherence `76.47%`
- Efficiency: correctness `81.25%`, adherence `62.5%`
- Negative: correctness `88.24%`, adherence `70.59%`

The strongest effect appears on Structural constraints. The explicit handoff materially reduced the maintainer’s tendency to refactor recursive solutions back into loop-based versions.

## Most Relevant Run 1 Figures

- `results/runs/run1_core_full/figures/adherence_by_constraint_type.png`
- `results/runs/run1_core_full/figures/token_usage_boxplot.png`
- `results/runs/run1_core_full/figures/joint_outcomes.png`

Recommended use in the paper:

- Use `adherence_by_constraint_type.png` in Results
- Use `token_usage_boxplot.png` for the efficiency/cost comparison
- Use `joint_outcomes.png` in Discussion or Results for the quality/adherence interaction

## Most Relevant Run 1 Tables

- `results/runs/run1_core_full/tables/overall_summary.md`
- `results/runs/run1_core_full/tables/per_task_results.csv`

## Qualitative Examples

Run 1 example pack:

- `results/runs/run1_core_full/examples/experimental_win.md`
- `results/runs/run1_core_full/examples/baseline_win.md`
- `results/runs/run1_core_full/examples/both_fail.md`
- `results/runs/run1_core_full/examples/baseline_surprise_success.md`

These are ready-made discussion artifacts for the paper’s anomaly and case-study sections.

## Suggested Interpretation

Run 1 supports the main thesis of the project: when the downstream maintainer receives a structured record of the original task and explicit constraints, constraint adherence improves substantially relative to a code-only handoff. The effect is especially strong for Structural constraints and still meaningful for Negative constraints.
