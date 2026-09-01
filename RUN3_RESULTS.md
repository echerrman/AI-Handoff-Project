# Run 3 Results

## Experiment

- Run ID: `run3_ablation_full`
- Experiment name: Run 3 Prompt-Only Ablation
- Experiment type: `run3_ablation`
- Task count: `50`

Run 3 compares:

- Baseline: code-only maintainer input
- Prompt-only ablation: original prompt plus code artifact, but no separately extracted explicit constraint field

This run tests whether simply passing more original context is enough, or whether explicitly extracting and structuring the constraint is the critical ingredient.

## Completion Status

Run 3 is fully complete.

- Pipeline generation complete
- Evaluation complete
- Figures generated
- Tables generated
- Example packs generated

Key files:

- `results/runs/run3_ablation_full/study_summary.md`
- `results/runs/run3_ablation_full/outputs/final_metrics.json`
- `results/runs/run3_ablation_full/tables/overall_summary.md`
- `results/runs/run3_ablation_full/tables/per_task_results.csv`

## Main Findings

### Overall Metrics

- Developer correctness: `96.0%`
- Baseline correctness: `98.0%`
- Experimental correctness: `98.0%`
- Baseline adherence: `32.0%`
- Prompt-only adherence: `30.0%`
- Correctness delta, experimental minus baseline: `0.0` points
- Adherence delta, experimental minus baseline: `-2.0` points
- Average total token delta, experimental minus baseline: `+257.66`

Run 3 is the key negative result in the study. Passing the original prompt without a separately structured explicit constraint did not improve adherence. It was slightly worse than baseline while also using more tokens.

### Joint Outcomes

Baseline:

- Correct and adherent: `30.0%`
- Correct but not adherent: `68.0%`
- Incorrect but adherent: `2.0%`
- Incorrect and not adherent: `0.0%`

Prompt-only ablation:

- Correct and adherent: `28.0%`
- Correct but not adherent: `70.0%`
- Incorrect but adherent: `2.0%`
- Incorrect and not adherent: `0.0%`

## By Constraint Type

### Baseline

- Structural: correctness `100.0%`, adherence `0.0%`
- Efficiency: correctness `93.75%`, adherence `62.5%`
- Negative: correctness `100.0%`, adherence `35.29%`

### Prompt-Only Ablation

- Structural: correctness `100.0%`, adherence `0.0%`
- Efficiency: correctness `93.75%`, adherence `62.5%`
- Negative: correctness `100.0%`, adherence `29.41%`

The ablation result is especially informative because it isolates the contribution of the explicit structured constraint field. The data suggests that prompt-only context is not enough to recover the Run 1 adherence gains.

## Most Relevant Run 3 Figures

- `results/runs/run3_ablation_full/figures/adherence_by_constraint_type.png`
- `results/runs/run3_ablation_full/figures/token_usage_boxplot.png`
- `results/runs/run3_ablation_full/figures/joint_outcomes.png`

For cross-run writing, pair this run with:

- `results/study_overview/figures/ablation_comparison.png`

## Most Relevant Run 3 Tables

- `results/runs/run3_ablation_full/tables/overall_summary.md`
- `results/runs/run3_ablation_full/tables/per_task_results.csv`
- `results/study_overview/tables/ablation_comparison.md`

## Qualitative Examples

Run 3 example pack:

- `results/runs/run3_ablation_full/examples/experimental_win.md`
- `results/runs/run3_ablation_full/examples/baseline_win.md`
- `results/runs/run3_ablation_full/examples/both_fail.md`
- `results/runs/run3_ablation_full/examples/baseline_surprise_success.md`

## Suggested Interpretation

Run 3 is important because it shows that the main effect in Run 1 was not just caused by giving the downstream maintainer "more context." Instead, the evidence points toward the explicit, structured representation of constraints as the key mechanism. This is a strong methodological point for the paper.
