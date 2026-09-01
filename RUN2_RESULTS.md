# Run 2 Results

## Experiment

- Run ID: `run2_multihop_subset15`
- Experiment name: Run 2 Multi-Hop Extension
- Experiment type: `run2_multihop`
- Task count: `15`

Run 2 extends the core setup to a three-agent pipeline:

- Developer produces the initial code
- Baseline condition passes through two maintainer hops without structured context
- Experimental condition passes through two maintainer hops with structured handoff context

## Completion Status

Run 2 is fully complete.

- Multi-hop pipeline generation complete
- Evaluation complete
- Multi-hop tables and figures generated
- Example packs generated

Key files:

- `results/runs/run2_multihop_subset15/study_summary.md`
- `results/runs/run2_multihop_subset15/outputs/final_metrics.json`
- `results/runs/run2_multihop_subset15/tables/multihop_summary.md`
- `results/runs/run2_multihop_subset15/tables/per_task_results.csv`

## Main Findings

### Overall Final-Hop Metrics

- Developer correctness: `93.33%`
- Baseline final correctness: `86.67%`
- Experimental final correctness: `100.0%`
- Baseline final adherence: `26.67%`
- Experimental final adherence: `73.33%`
- Correctness delta, experimental minus baseline: `+13.33` points
- Adherence delta, experimental minus baseline: `+46.66` points
- Average total token delta, experimental minus baseline: `+510.4`

Run 2 is the strongest quantitative result in the study. The context-aware multi-hop pipeline preserved both correctness and adherence much better than the baseline.

### Joint Outcomes

Baseline final hop:

- Correct and adherent: `20.0%`
- Correct but not adherent: `66.67%`
- Incorrect but adherent: `6.67%`
- Incorrect and not adherent: `6.67%`

Experimental final hop:

- Correct and adherent: `73.33%`
- Correct but not adherent: `26.67%`
- Incorrect but adherent: `0.0%`
- Incorrect and not adherent: `0.0%`

This is a very useful paper result because it shows that the structured handoff does not just survive an extra hop; it remains clearly stronger after additional context degradation risk.

## Multi-Hop Progression

### Baseline

- Hop 1: correctness `93.33%`, adherence `26.67%`, avg tokens `425.93`
- Hop 2: correctness `86.67%`, adherence `26.67%`, avg tokens `366.53`

### Experimental

- Hop 1: correctness `100.0%`, adherence `66.67%`, avg tokens `855.0`
- Hop 2: correctness `100.0%`, adherence `73.33%`, avg tokens `876.93`

The baseline loses correctness across hops and never improves its adherence. The experimental pipeline retains perfect correctness across both maintainer hops and improves adherence from hop 1 to hop 2.

## By Constraint Type

### Baseline

- Structural: correctness `100.0%`, adherence `0.0%`
- Efficiency: correctness `75.0%`, adherence `75.0%`
- Negative: correctness `83.33%`, adherence `16.67%`

### Experimental

- Structural: correctness `100.0%`, adherence `100.0%`
- Efficiency: correctness `100.0%`, adherence `50.0%`
- Negative: correctness `100.0%`, adherence `66.67%`

Run 2 again shows the strongest separation on Structural and Negative constraints.

## Most Relevant Run 2 Figures

- `results/runs/run2_multihop_subset15/figures/multihop_adherence_by_hop.png`
- `results/runs/run2_multihop_subset15/figures/adherence_by_constraint_type.png`
- `results/runs/run2_multihop_subset15/figures/joint_outcomes.png`

Recommended use in the paper:

- Use `multihop_adherence_by_hop.png` as the main figure for the multi-hop extension
- Use `joint_outcomes.png` to show quality + adherence together

## Most Relevant Run 2 Tables

- `results/runs/run2_multihop_subset15/tables/multihop_summary.md`
- `results/runs/run2_multihop_subset15/tables/overall_summary.md`
- `results/runs/run2_multihop_subset15/tables/per_task_results.csv`

## Qualitative Examples

Run 2 example pack:

- `results/runs/run2_multihop_subset15/examples/experimental_win.md`
- `results/runs/run2_multihop_subset15/examples/baseline_win.md`
- `results/runs/run2_multihop_subset15/examples/both_fail.md`
- `results/runs/run2_multihop_subset15/examples/baseline_surprise_success.md`

## Suggested Interpretation

Run 2 strengthens the main claim from Run 1. The structured handoff does not merely help on a single transfer; it appears to resist context degradation across multiple maintainer hops. This makes Run 2 an especially strong centerpiece for the discussion section.
