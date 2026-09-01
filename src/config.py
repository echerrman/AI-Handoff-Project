from __future__ import annotations

import os

from dotenv import load_dotenv


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))

CACHE_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, ".cache"))
DATA_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "data"))
RESULTS_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "results"))
RUNS_DIR = os.path.abspath(os.path.join(RESULTS_DIR, "runs"))
ENV_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, ".env"))

CURATED_TASKS_PATH = os.path.join(DATA_DIR, "curated_tasks.json")
PIPELINE_RESULTS_PATH = os.path.join(DATA_DIR, "pipeline_results.json")
FINAL_METRICS_PATH = os.path.join(RESULTS_DIR, "final_metrics.json")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(RUNS_DIR, exist_ok=True)

# Keep Hugging Face caches inside the project root before any HF import occurs.
os.environ["HF_HOME"] = CACHE_DIR
os.environ["HF_DATASETS_CACHE"] = CACHE_DIR
HF_HOME = CACHE_DIR
HF_DATASETS_CACHE = CACHE_DIR

load_dotenv(ENV_PATH, override=False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

DEVELOPER_MODEL = os.getenv("GEMINI_DEVELOPER_MODEL", "gemini-2.5-flash-lite")
MAINTAINER_MODEL = os.getenv("GEMINI_MAINTAINER_MODEL", "gemini-2.5-flash-lite")
JUDGE_MODEL = os.getenv("GEMINI_JUDGE_MODEL", "gemini-2.5-flash-lite")

DEFAULT_MAX_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1600"))
DEFAULT_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.0"))
GEMINI_RATE_LIMIT_SECONDS = float(os.getenv("GEMINI_RATE_LIMIT_SECONDS", "4.5"))

HUMANEVAL_DATASET = os.getenv("HUMANEVAL_DATASET", "openai_humaneval")
CURATION_SIZE = int(os.getenv("CURATION_SIZE", "50"))
CURATION_SEED = int(os.getenv("CURATION_SEED", "42"))

DEFAULT_EXPERIMENT_NAME = os.getenv("EXPERIMENT_NAME", "Context-Aware Handoff Study")
DEFAULT_EXPERIMENT_TYPE = os.getenv("EXPERIMENT_TYPE", "run1_core")
CORRECTNESS_TIMEOUT_SECONDS = float(os.getenv("CORRECTNESS_TIMEOUT_SECONDS", "10.0"))
RUN2_DEFAULT_TASK_LIMIT = int(os.getenv("RUN2_DEFAULT_TASK_LIMIT", "15"))
