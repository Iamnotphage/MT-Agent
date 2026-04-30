#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# User-editable paths
# ---------------------------------------------------------------------------
AGENT_PROJECT_PATH="${HOME}/projects/MT-Agent"

# ---------------------------------------------------------------------------
# User-editable run settings
# ---------------------------------------------------------------------------
DATASET_NAME="SWE-bench/SWE-bench_Lite"
SPLIT="test"
LIMIT=10
INSTANCE_IDS=()

MODEL_NAME_OR_PATH="mt-agent-lite"
REPOS_ROOT=".swebench/repos"
REPO_SOURCE="https://github.com/swe-bench-repos"
OUTPUT_PATH="predictions/mt-agent-lite.jsonl"
ERROR_OUTPUT="predictions/mt-agent-lite.errors.jsonl"
OFFLINE_REPOS=1
RESUME=1
CONTINUE_ON_ERROR=0

# ---------------------------------------------------------------------------
# Command assembly
# ---------------------------------------------------------------------------
cd "${AGENT_PROJECT_PATH}"

CMD=(
  uv
  run
  python
  scripts/swebench_generate_predictions.py
  --dataset_name "${DATASET_NAME}"
  --split "${SPLIT}"
  --output "${OUTPUT_PATH}"
  --error_output "${ERROR_OUTPUT}"
  --repos_root "${REPOS_ROOT}"
  --model_name_or_path "${MODEL_NAME_OR_PATH}"
)

if [[ ${OFFLINE_REPOS} -eq 1 ]]; then
  CMD+=(--offline_repos)
else
  CMD+=(--repo_source "${REPO_SOURCE}")
fi

if [[ ${RESUME} -eq 1 ]]; then
  CMD+=(--resume)
fi

if [[ ${CONTINUE_ON_ERROR} -eq 1 ]]; then
  CMD+=(--continue_on_error)
fi

if [[ ${LIMIT} -gt 0 ]]; then
  CMD+=(--limit "${LIMIT}")
fi

if [[ ${#INSTANCE_IDS[@]} -gt 0 ]]; then
  CMD+=(--instance_ids "${INSTANCE_IDS[@]}")
fi

echo "[predict] agent project: ${AGENT_PROJECT_PATH}"
echo "[predict] dataset: ${DATASET_NAME}"
echo "[predict] split: ${SPLIT}"
echo "[predict] limit: ${LIMIT}"
echo "[predict] output: ${OUTPUT_PATH}"
echo "[predict] error output: ${ERROR_OUTPUT}"
echo "[predict] offline repos: ${OFFLINE_REPOS}"
echo "[predict] resume: ${RESUME}"
echo "[predict] continue on error: ${CONTINUE_ON_ERROR}"
echo "[predict] command: ${CMD[*]}"

"${CMD[@]}"
