#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# User-editable paths
# ---------------------------------------------------------------------------
AGENT_PROJECT_PATH="${HOME}/projects/MT-Agent"
SWEBENCH_PATH="${HOME}/projects/SWE-bench"

# ---------------------------------------------------------------------------
# User-editable evaluation settings
# ---------------------------------------------------------------------------
DATASET_NAME="SWE-bench/SWE-bench_Lite"
SPLIT="test"
PREDICTIONS_PATH="${AGENT_PROJECT_PATH}/predictions/mt-agent-lite.jsonl"
RUN_ID="mt-agent-lite"
MAX_WORKERS=1
INSTANCE_IDS=()

# Optional harness knobs
NAMESPACE=""
TIMEOUT=1800

# ---------------------------------------------------------------------------
# Command assembly
# ---------------------------------------------------------------------------
cd "${SWEBENCH_PATH}"

CMD=(
  python
  -m
  swebench.harness.run_evaluation
  --dataset_name "${DATASET_NAME}"
  --split "${SPLIT}"
  --predictions_path "${PREDICTIONS_PATH}"
  --max_workers "${MAX_WORKERS}"
  --run_id "${RUN_ID}"
  --timeout "${TIMEOUT}"
)

if [[ -n "${NAMESPACE}" ]]; then
  CMD+=(--namespace "${NAMESPACE}")
fi

if [[ ${#INSTANCE_IDS[@]} -gt 0 ]]; then
  CMD+=(--instance_ids "${INSTANCE_IDS[@]}")
fi

echo "[eval] agent project: ${AGENT_PROJECT_PATH}"
echo "[eval] swe-bench path: ${SWEBENCH_PATH}"
echo "[eval] dataset: ${DATASET_NAME}"
echo "[eval] split: ${SPLIT}"
echo "[eval] predictions: ${PREDICTIONS_PATH}"
echo "[eval] run id: ${RUN_ID}"
echo "[eval] max workers: ${MAX_WORKERS}"
echo "[eval] command: ${CMD[*]}"

"${CMD[@]}"
