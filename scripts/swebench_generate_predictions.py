"""Generate SWE-bench prediction JSONL with MT-Agent.

This script handles the inference stage before `swebench.harness.run_evaluation`:
1. Load SWE-bench instances from Hugging Face datasets
2. Prepare a local checkout for each instance at `base_commit`
3. Run MT-Agent against that checkout
4. Export the resulting git diff as `model_patch`

Example:
    uv run python scripts/swebench_generate_predictions.py \
        --dataset_name princeton-nlp/SWE-bench_Lite \
        --instance_ids sympy__sympy-20590 \
        --output predictions/mt-agent-lite.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from core.agent import create_agent_runtime


DEFAULT_DATASET = "princeton-nlp/SWE-bench_Lite"
DEFAULT_SPLIT = "test"
DEFAULT_REPOS_ROOT = ".swebench/repos"
DEFAULT_OUTPUT = "predictions/mt-agent.jsonl"
DEFAULT_GIT_RETRIES = 3


def log(message: str) -> None:
    print(message, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SWE-bench predictions with MT-Agent")
    parser.add_argument("--dataset_name", default=DEFAULT_DATASET)
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--instance_ids", nargs="+", help="Specific SWE-bench instance IDs")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of instances")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--repos_root", default=DEFAULT_REPOS_ROOT)
    parser.add_argument(
        "--repo_source",
        default="https://github.com/swe-bench-repos",
        help="Base URL for mirrored repositories",
    )
    parser.add_argument(
        "--model_name_or_path",
        default=os.environ.get("MODEL_NAME", "mt-agent"),
        help="Value written into predictions.jsonl",
    )
    parser.add_argument(
        "--max_workers_note",
        default="Use SWE-bench harness --max_workers there; this script runs sequentially.",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def load_instances(dataset_name: str, split: str, instance_ids: list[str] | None, limit: int | None) -> list[dict]:
    log(f"[dataset] loading {dataset_name} split={split}")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: datasets. Install it in the evaluation environment first, "
            "for example `uv add datasets` or `pip install datasets`."
        ) from exc

    dataset = load_dataset(dataset_name, split=split)
    rows = list(dataset)

    if instance_ids:
        wanted = set(instance_ids)
        rows = [row for row in rows if row["instance_id"] in wanted]
        missing = wanted - {row["instance_id"] for row in rows}
        if missing:
            raise SystemExit(f"Instance IDs not found in dataset {dataset_name}/{split}: {sorted(missing)}")

    if limit is not None:
        rows = rows[:limit]

    log(f"[dataset] loaded {len(rows)} instances")
    return rows


def run_git(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def has_commit(repo_dir: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo_dir,
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def run_git_with_retry(cmd: list[str], cwd: Path | None = None, retries: int = DEFAULT_GIT_RETRIES) -> None:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, retries + 1):
        try:
            subprocess.run(cmd, cwd=cwd, check=True)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt >= retries:
                break
            wait_seconds = attempt * 2
            log(f"[git] attempt {attempt}/{retries} failed: {' '.join(cmd)}")
            log(f"[git] retrying in {wait_seconds}s")
            time.sleep(wait_seconds)
    assert last_error is not None
    raise last_error


def ensure_repo(instance: dict, repos_root: Path, repo_source: str) -> Path:
    repo_key = instance["repo"].replace("/", "__")
    repo_dir = repos_root / repo_key
    repo_url = f"{repo_source}/{repo_key}.git"
    base_commit = instance["base_commit"]

    repos_root.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        log(f"[repo] cloning {repo_url} -> {repo_dir}")
        run_git_with_retry(["git", "clone", repo_url, str(repo_dir)])
    else:
        if has_commit(repo_dir, base_commit):
            log(f"[repo] found base commit locally, skip fetch: {base_commit}")
        else:
            log(f"[repo] refreshing {repo_dir}")
            run_git_with_retry(["git", "fetch", "--all", "--tags"], cwd=repo_dir)

    if not has_commit(repo_dir, base_commit):
        raise RuntimeError(
            f"Base commit {base_commit} is still unavailable in {repo_dir}. "
            "Check network access or repo mirror health."
        )

    log(f"[repo] resetting {repo_dir.name} to {base_commit}")
    subprocess.run(["git", "reset", "--hard", base_commit], cwd=repo_dir, check=True)
    subprocess.run(["git", "clean", "-fdx"], cwd=repo_dir, check=True)
    log(f"[repo] ready at {base_commit}")
    return repo_dir


def build_prompt(instance: dict) -> str:
    repo = instance["repo"]
    issue = instance["instance_id"]
    base_commit = instance["base_commit"]
    problem = instance["problem_statement"].strip()

    return f"""You are solving one SWE-bench task.

Repository: {repo}
Instance ID: {issue}
Base commit: {base_commit}

Issue statement:
{problem}

Requirements:
1. Inspect the repository and modify files directly in the workspace.
2. Keep the fix minimal and focused on the issue.
3. Do not describe a patch in prose.
4. End after you have made the code changes needed for the fix.
"""


def run_agent_on_instance(repo_dir: Path, prompt: str) -> tuple[str, str]:
    log(f"[agent] creating runtime in {repo_dir}")
    runtime = create_agent_runtime(workspace=str(repo_dir))
    thread_id = uuid.uuid4().hex
    runtime.session.set_thread_id(thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    state_input = {
        "messages": [HumanMessage(content=prompt)],
        "query_source": "batch",
    }

    try:
        log("[agent] invoking graph")
        runtime.graph.invoke(state_input, config)
        log("[agent] initial invoke completed")
        auto_resume_interrupts(runtime, config)
        log("[agent] approval handling completed")
        final_text = get_last_assistant_message(runtime, config)
        log("[agent] exporting git diff")
        patch = run_git(["git", "diff", "--binary"], repo_dir)
        log(f"[agent] diff length={len(patch)} chars")
        return final_text, patch
    finally:
        if runtime.checkpoint_manager is not None:
            runtime.checkpoint_manager.__exit__(None, None, None)


def auto_resume_interrupts(runtime, config: dict) -> None:
    while True:
        snapshot = runtime.graph.get_state(config)
        if not snapshot.next:
            return

        decisions: dict[str, bool] = {}
        for task in snapshot.tasks:
            for intr in getattr(task, "interrupts", []):
                value = intr.value
                if isinstance(value, list):
                    for item in value:
                        call_id = item.get("call_id")
                        if call_id:
                            decisions[call_id] = True
                elif isinstance(value, dict):
                    call_id = value.get("call_id")
                    if call_id:
                        decisions[call_id] = True

        log(f"[agent] auto-approving {len(decisions)} tool calls")
        runtime.graph.invoke(Command(resume=decisions), config)


def get_last_assistant_message(runtime, config: dict) -> str:
    snapshot = runtime.graph.get_state(config)
    values = getattr(snapshot, "values", {}) or {}
    messages = values.get("messages", [])
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message.content if isinstance(message.content, str) else str(message.content)
    return ""


def write_predictions(instances: list[dict], predictions: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for pred in predictions:
            f.write(json.dumps(pred, ensure_ascii=False) + "\n")
    log(f"[output] wrote {len(predictions)} predictions to {output_path}")
    log(f"[output] instances={ [instance['instance_id'] for instance in instances] }")


def main() -> int:
    args = parse_args()
    instances = load_instances(args.dataset_name, args.split, args.instance_ids, args.limit)
    repos_root = Path(args.repos_root).resolve()
    output_path = Path(args.output).resolve()

    predictions: list[dict] = []

    for idx, instance in enumerate(instances, start=1):
        instance_id = instance["instance_id"]
        log(f"[run] [{idx}/{len(instances)}] instance={instance_id}")
        repo_dir = ensure_repo(instance, repos_root, args.repo_source)
        prompt = build_prompt(instance)
        final_text, patch = run_agent_on_instance(repo_dir, prompt)

        if not patch.strip():
            print(f"Warning: empty patch for {instance_id}", file=sys.stderr, flush=True)

        predictions.append({
            "instance_id": instance_id,
            "model_name_or_path": args.model_name_or_path,
            "model_patch": patch,
        })

    write_predictions(instances, predictions, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
