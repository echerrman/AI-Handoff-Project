# Study Process and Methods

## Study Status

The study execution is complete.

- Run 1 (`run1_core_full`) finished pipeline generation and evaluation.
- Run 2 (`run2_multihop_subset15`) finished pipeline generation and evaluation.
- Run 3 (`run3_ablation_full`) finished pipeline generation and evaluation.
- Cross-run reporting was generated under `results/study_overview/`.

At this point, the main work left is paper writing and selecting which generated tables, figures, and examples to cite in the manuscript.

## Core Research Setup

This project studies whether structured, context-aware handoffs help role-specialized LLM agents preserve explicit task constraints during software engineering workflows.

- Model family: Gemini
- API SDK: `google-genai`
- Agent roles: `DeveloperAgent`, `MaintainerAgent`, and `JudgeAgent`
- Dataset source: HumanEval test split
- Curated benchmark: 50 tagged tasks stored in `data/curated_tasks.json`
- Constraint types:
  - Negative: avoid built-in standard-library logic
  - Structural: use recursion and avoid iteration
  - Efficiency: maintain O(n) or better

In this project, an "agent" means a role-conditioned LLM instance with a distinct prompt policy, input contract, and task in the handoff pipeline, even when multiple agents share the same Gemini backbone.

## Files and Pipeline

The study pipeline is implemented in:

- `src/config.py`
- `src/dataset_prep.py`
- `src/agents.py`
- `src/handoff_pipeline.py`
- `src/correctness.py`
- `src/evaluator.py`
- `src/study_runner.py`
- `src/study_reporting.py`

The execution flow is:

1. `src/dataset_prep.py` downloads and curates HumanEval into a 50-task JSON file.
2. `src/handoff_pipeline.py` runs the Developer -> Maintainer pipeline and writes run-scoped artifacts.
3. `src/evaluator.py` executes correctness checks, constraint adherence checks, and report generation.
4. `src/study_runner.py` orchestrates all planned runs and retries incomplete pipeline or evaluation stages until a run is fully complete.
5. `src/study_reporting.py` generates cross-run comparison artifacts and the root README.

## Dataset and Constraints

The dataset preparation step:

- downloads `openai/openai_humaneval`
- keeps all Hugging Face caching inside the project-local `.cache/` directory
- filters and scores tasks into a curated 50-problem set
- attaches one explicit poison constraint per task

Key source files:

- `data/curated_tasks.json`
- `results/runs/run1_core_full/inputs/curated_tasks_snapshot.json`
- `results/runs/run2_multihop_subset15/inputs/curated_tasks_snapshot.json`
- `results/runs/run3_ablation_full/inputs/curated_tasks_snapshot.json`

## Experimental Conditions

### Run 1: Core Two-Agent Handoff

- Developer receives the HumanEval prompt plus the poison constraint.
- Baseline maintainer receives only the code artifact.
- Experimental maintainer receives the code plus a structured `HandoffReceipt`.

### Run 2: Multi-Hop Extension

- Developer produces the initial solution.
- Baseline passes code through two maintainer hops without structured context.
- Experimental passes structured handoff context through two maintainer hops.

### Run 3: Prompt-Only Ablation

- Baseline stays the same as Run 1.
- Experimental removes the explicit extracted constraint field and provides only the original prompt plus the code artifact.

## Evaluation Design

Evaluation combines deterministic checks and LLM judging.

- Correctness:
  - implemented in `src/correctness.py`
  - executes HumanEval tests locally in a subprocess with timeouts
- Structural constraints:
  - checked deterministically with AST/static analysis
- Efficiency constraints:
  - checked deterministically with static heuristics
- Negative constraints:
  - judged by Gemini through `JudgeAgent`

This means the study is fully evaluated, but only the Negative-constraint adherence decisions depend on an LLM judge.

## Artifact Layout

Each run writes a complete artifact package under `results/runs/<run_id>/`.

Within each run directory:

- `manifest.json`: run metadata and status
- `inputs/`: configuration and curated task snapshot
- `outputs/`: pipeline outputs, evaluation outputs, and final metrics
- `logs/`: raw LLM call logs for pipeline and evaluation
- `tables/`: CSV and Markdown tables for the paper
- `figures/`: PNG figures and figure metadata
- `examples/`: qualitative example cases
- `study_summary.md`: concise run-level summary
- `manual_screenshot_checklist.md`: optional screenshot checklist

Cross-run assets live under:

- `results/study_overview/`

## Final Study Outputs Already Generated

Per-run summaries:

- `results/runs/run1_core_full/study_summary.md`
- `results/runs/run2_multihop_subset15/study_summary.md`
- `results/runs/run3_ablation_full/study_summary.md`

Per-run metrics:

- `results/runs/run1_core_full/outputs/final_metrics.json`
- `results/runs/run2_multihop_subset15/outputs/final_metrics.json`
- `results/runs/run3_ablation_full/outputs/final_metrics.json`

Cross-run outputs:

- `results/study_overview/study_overview.md`
- `results/study_overview/tables/run_comparison.md`
- `results/study_overview/tables/condition_comparison.md`
- `results/study_overview/tables/ablation_comparison.md`
- `results/study_overview/figures/cross_run_adherence.png`
- `results/study_overview/figures/cross_run_correctness.png`
- `results/study_overview/figures/ablation_comparison.png`

## Recommended Figures for the Paper

The following figures are already present and are strong candidates for the manuscript.

### Cross-Run Figures

- `results/study_overview/figures/cross_run_adherence.png`
- `results/study_overview/figures/cross_run_correctness.png`
- `results/study_overview/figures/ablation_comparison.png`

### Run-Level Figures

- `results/runs/run1_core_full/figures/adherence_by_constraint_type.png`
- `results/runs/run1_core_full/figures/token_usage_boxplot.png`
- `results/runs/run1_core_full/figures/joint_outcomes.png`
- `results/runs/run2_multihop_subset15/figures/multihop_adherence_by_hop.png`
- `results/runs/run2_multihop_subset15/figures/joint_outcomes.png`
- `results/runs/run3_ablation_full/figures/adherence_by_constraint_type.png`

## Recommended Tables for the Paper

- `results/study_overview/tables/run_comparison.md`
- `results/study_overview/tables/condition_comparison.md`
- `results/study_overview/tables/ablation_comparison.md`
- `results/runs/run1_core_full/tables/overall_summary.md`
- `results/runs/run2_multihop_subset15/tables/overall_summary.md`
- `results/runs/run3_ablation_full/tables/overall_summary.md`
- `results/runs/run2_multihop_subset15/tables/multihop_summary.md`

## Writing Guidance

If you are moving from execution to paper drafting, the most useful sequence is:

1. Read this file for the methods/process overview.
2. Read `RUN1_RESULTS.md`, `RUN2_RESULTS.md`, and `RUN3_RESULTS.md` for experiment-specific findings.
3. Use `results/study_overview/` for cross-run tables and figures.
4. Pull qualitative case studies from each run’s `examples/` directory.

## Bottom Line

The study itself is done. The remaining task is synthesis: deciding which generated metrics, figures, and examples best support the final paper narrative.
