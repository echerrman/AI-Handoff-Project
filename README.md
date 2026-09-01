# Context-Aware Handoffs Research Study

This repository contains a role-specialized LLM-agent study on context-aware handoffs in code maintenance pipelines.

## Repository Setup

- Secrets are not committed. Use `.env.example` as the template for your local `.env`.
- Install dependencies with `pip install -r requirements.txt`.
- Keep `.cache/` and `.venv/` local; they are intentionally ignored by Git.

## Writing Docs

For paper drafting, start with these root-level documents:

- `STUDY_PROCESS_AND_METHODS.md`
- `RUN1_RESULTS.md`
- `RUN2_RESULTS.md`
- `RUN3_RESULTS.md`

## Research Setup

- Model family: Gemini, instantiated as role-specialized agents over a shared backbone.
- Agent roles: `DeveloperAgent`, `MaintainerAgent`, and `JudgeAgent` in `src/agents.py`.
- Dataset: curated 50-task subset of HumanEval with assigned poison constraints.
- Constraint types: Negative, Structural, and Efficiency.
- Core artifact root: `results/runs/`.

## Experiments

- Run 1 (`run1_core`): 2-agent baseline vs context-aware handoff on the 50-task curated dataset.
- Run 2 (`run2_multihop`): 3-agent multi-hop extension on a 15-task subset to test context degradation across hops.
- Run 3 (`run3_ablation`): prompt-only ablation that removes the explicit constraint field from the experimental handoff.

## How the Pipeline Works

1. `src/dataset_prep.py` downloads HumanEval into the project-local `.cache/` directory and writes `data/curated_tasks.json`.
2. `src/handoff_pipeline.py` runs the role-specialized LLM pipeline and writes a run-scoped artifact folder.
3. `src/evaluator.py` executes correctness checks, constraint adherence checks, and paper-facing report generation.
4. `src/study_runner.py` orchestrates all planned runs and then generates cross-run reports and this README.

## Evaluation and Reporting

- Correctness is evaluated deterministically by executing the HumanEval tests against candidate code in a subprocess sandbox with a timeout.
- Structural and Efficiency constraints are judged deterministically from AST/static heuristics.
- Negative constraints are judged with the Gemini-based `JudgeAgent`.
- Each run stores prompts, raw model outputs, token usage, timings, retries, figures, tables, example cases, and a narrative study summary.

## Current Results Snapshot

- Run 1 Baseline adherence: 36.0%
- Run 1 Experimental adherence: 70.0%
- Run 2 Baseline adherence: 26.67%
- Run 2 Experimental adherence: 73.33%
- Run 3 Prompt-only adherence: 30.0%

## Where to Find Things

- Curated dataset: `data/curated_tasks.json`
- Latest top-level metrics mirror: `results/final_metrics.json`
- Per-run artifacts: `results/runs/<run_id>/`
- Cross-run comparison package: `results/study_overview/`
- Cross-run overview: `results/study_overview/study_overview.md`

## Per-Run Artifact Layout

- `inputs/`: exact inputs and experiment configuration
- `outputs/`: pipeline results, evaluation results, and final metrics
- `logs/`: raw LLM prompt/response JSONL logs
- `tables/`: CSV and Markdown tables for the paper
- `figures/`: PNG figures plus figure metadata
- `examples/`: qualitative example packs
- `study_summary.md`: run-level narrative summary

## Models and Agent Definitions

- Developer default model: loaded from `GEMINI_DEVELOPER_MODEL`, currently defaulting to `gemini-2.5-flash-lite`.
- Maintainer default model: loaded from `GEMINI_MAINTAINER_MODEL`, currently defaulting to `gemini-2.5-flash-lite`.
- Judge default model: loaded from `GEMINI_JUDGE_MODEL`, currently defaulting to `gemini-2.5-flash-lite`.
- The code includes fallback handling for transient quota/unavailability issues across compatible Gemini flash variants.

## Reproduction

Run the full study with:

```powershell
.\.venv\Scripts\python.exe src\study_runner.py --overwrite
```

## Citation-Relevant Components

- HumanEval benchmark and associated paper
- Hugging Face `datasets` library
- Google Gemini API / `google-genai` SDK
- Pydantic for structured schemas

## Notes

- In this project, an `agent` means a role-conditioned LLM instance with its own prompt policy, interface, and task in the handoff pipeline.
- The same Gemini model family can back multiple agents while still supporting a valid multi-agent experimental design.
