#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# User-editable paths
# ---------------------------------------------------------------------------
AGENT_PROJECT_PATH="${HOME}/projects/MT-Agent"

# ---------------------------------------------------------------------------
# User-editable prefetch settings
# ---------------------------------------------------------------------------
DATASET_NAME="SWE-bench/SWE-bench_Lite"
SPLIT="test"
LIMIT=0
INSTANCE_IDS=()

REPOS_ROOT=".swebench/repos"
REPO_SOURCE="https://github.com/swe-bench-repos"
GIT_RETRIES=3

cd "${AGENT_PROJECT_PATH}"
mkdir -p "${REPOS_ROOT}"

echo "[prefetch] agent project: ${AGENT_PROJECT_PATH}"
echo "[prefetch] dataset: ${DATASET_NAME}"
echo "[prefetch] split: ${SPLIT}"
echo "[prefetch] limit: ${LIMIT}"
echo "[prefetch] repos root: ${REPOS_ROOT}"

mapfile -t REPO_ROWS < <(
  uv run python - "${DATASET_NAME}" "${SPLIT}" "${LIMIT}" "${INSTANCE_IDS[@]}" <<'PY'
from collections import defaultdict
import sys

dataset_name = sys.argv[1]
split = sys.argv[2]
limit = int(sys.argv[3])
instance_ids = set(sys.argv[4:])

from datasets import load_dataset

rows = list(load_dataset(dataset_name, split=split))
if instance_ids:
    rows = [row for row in rows if row["instance_id"] in instance_ids]
if limit > 0:
    rows = rows[:limit]

repos = defaultdict(set)
for row in rows:
    repos[row["repo"]].add(row["base_commit"])

for repo in sorted(repos):
    commits = sorted(repos[repo])
    print(repo + "\t" + "\t".join(commits))
PY
)

echo "[prefetch] repos to prepare: ${#REPO_ROWS[@]}"

retry_git() {
  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if [[ ${attempt} -ge ${GIT_RETRIES} ]]; then
      return 1
    fi
    local wait_seconds=$((attempt * 2))
    echo "[prefetch] retry ${attempt}/${GIT_RETRIES}: $*"
    echo "[prefetch] sleeping ${wait_seconds}s"
    sleep "${wait_seconds}"
    attempt=$((attempt + 1))
  done
}

has_commit() {
  local repo_dir="$1"
  local commit="$2"
  git -C "${repo_dir}" rev-parse --verify "${commit}^{commit}" >/dev/null 2>&1
}

for row in "${REPO_ROWS[@]}"; do
  IFS=$'\t' read -r repo commits_str <<< "${row}"
  repo_key="${repo//\//__}"
  repo_dir="${REPOS_ROOT}/${repo_key}"
  repo_url="${REPO_SOURCE}/${repo_key}.git"
  needs_fetch=0

  if [[ ! -d "${repo_dir}/.git" ]]; then
    echo "[prefetch] cloning ${repo_url}"
    retry_git git clone "${repo_url}" "${repo_dir}"
    echo "[prefetch] clone completed ${repo_key}"
  else
    echo "[prefetch] using existing repo ${repo_dir}"
    needs_fetch=1
  fi

  IFS=$'\t' read -r -a commit_list <<< "${commits_str}"
  missing_count=0
  for commit in "${commit_list[@]}"; do
    if ! has_commit "${repo_dir}" "${commit}"; then
      missing_count=$((missing_count + 1))
    fi
  done

  if [[ ${missing_count} -gt 0 ]]; then
    needs_fetch=1
    echo "[prefetch] missing commits before fetch: ${repo_key} count=${missing_count}"
  fi

  if [[ ${needs_fetch} -eq 1 ]]; then
    echo "[prefetch] fetching ${repo_key}"
    retry_git git -C "${repo_dir}" fetch --all --tags
  else
    echo "[prefetch] skip fetch ${repo_key}; required commits already present"
  fi

  for commit in "${commit_list[@]}"; do
    if ! has_commit "${repo_dir}" "${commit}"; then
      echo "[prefetch] missing commit after fetch: ${repo_key} ${commit}"
      exit 1
    fi
  done

  echo "[prefetch] ready ${repo_key} commits=${#commit_list[@]}"
done

echo "[prefetch] completed"
