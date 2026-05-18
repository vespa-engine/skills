"""Run skill evaluations: execute a coding agent with and without skills,
capture outputs, and organize results into workspace directories.

Usage:
    vespaskills eval
    vespaskills eval --eval fix-subtle-bugs
    vespaskills eval --model claude-sonnet-4-20250514
    vespaskills eval --skip-baseline
    vespaskills eval --iteration 2
"""

import json
import shutil
import sys
from pathlib import Path

from vespaskills.evals.config import REPO_ROOT
from vespaskills.evals.providers import get_provider
from vespaskills.logger import get_logger

logger = get_logger()


def load_evals(evals_path: Path, eval_name: str | None = None) -> dict:
    """Load eval definitions from evals.json."""
    with open(evals_path) as f:
        data = json.load(f)
    if eval_name:
        data["evals"] = [e for e in data["evals"] if e["name"] == eval_name]
        if not data["evals"]:
            logger.error(f"No eval found with name '{eval_name}'")
            sys.exit(1)
    return data


def get_next_iteration(workspace: Path) -> int:
    """Find the next iteration number."""
    if not workspace.exists():
        return 1
    existing = [
        int(d.name.split("-")[1]) for d in workspace.iterdir() if d.is_dir() and d.name.startswith("iteration-")
    ]
    return max(existing, default=0) + 1


def run_single_eval(
    eval_def: dict,
    skill_path: Path | None,
    eval_dir: Path,
    run_type: str,
    provider,
) -> dict:
    """Run a single eval trial and save results."""
    run_dir = eval_dir / run_type
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"    [{run_type}] Running ({provider.name})...")

    # Read skill content if needed
    skill_content = None
    if skill_path and run_type == "with_skill":
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            skill_content = skill_md.read_text()

    # Copy any fixture files into outputs dir. Fixture paths are resolved
    # relative to REPO_ROOT so eval configs are location-independent.
    for fixture in eval_def.get("files", []):
        src = Path(fixture)
        if not src.is_absolute():
            src = REPO_ROOT / src
        if src.exists():
            dest = outputs_dir / src.name
            shutil.copy2(src, dest)

    # Run the agent directly in the outputs directory
    result = provider.run_prompt(
        prompt=eval_def["prompt"],
        work_dir=outputs_dir,
        skill_content=skill_content,
    )

    # Collect any files that leaked to common paths outside outputs_dir
    # (Claude sometimes resolves relative paths like "schemas/foo.sd" against repo root)
    for leaked_dir in ("schemas",):
        leaked_path = REPO_ROOT / leaked_dir
        if leaked_path.exists() and leaked_path.is_dir():
            dest = outputs_dir / leaked_dir
            dest.mkdir(parents=True, exist_ok=True)
            for f in leaked_path.rglob("*"):
                if f.is_file():
                    target = dest / f.relative_to(leaked_path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(target))
                    logger.debug(f"    Recovered leaked file: {leaked_dir}/{f.relative_to(leaked_path)}")
            # Clean up the empty leaked directory
            shutil.rmtree(leaked_path, ignore_errors=True)

    # Save timing
    usage = provider.extract_usage(result.stdout)
    timing = {
        "provider": provider.name,
        "model": provider.model or "(default)",
        "duration_ms": result.duration_ms,
        "exit_code": result.exit_code,
        **usage,
    }
    with open(run_dir / "timing.json", "w") as f:
        json.dump(timing, f, indent=2)

    # Save raw transcript
    with open(run_dir / "transcript.json", "w") as f:
        f.write(result.stdout or "{}")

    # Save stderr for debugging
    if result.stderr:
        with open(run_dir / "stderr.txt", "w") as f:
            f.write(result.stderr)

    status = "ok" if result.exit_code == 0 else "error"
    if result.exit_code == 0:
        logger.success(f"    [{run_type}] {status} ({result.duration_ms}ms, {len(result.output_files)} files)")
    else:
        logger.warning(f"    [{run_type}] {status} ({result.duration_ms}ms, {len(result.output_files)} files)")
    return timing


def run(args):
    """Run eval command with parsed args."""
    provider = get_provider(model=args.model, provider_name=getattr(args, "provider", None))

    evals_data = load_evals(args.evals_json, args.eval)
    skill_name = evals_data["skill_name"]
    skill_path = REPO_ROOT / evals_data["skill_path"]

    if not skill_path.exists():
        logger.error(f"Skill path not found: {skill_path}")
        sys.exit(1)

    workspace = REPO_ROOT / f"{skill_name}-workspace"
    iteration = args.iteration or get_next_iteration(workspace)
    iter_dir = workspace / f"iteration-{iteration}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Skill: {skill_name}")
    logger.info(f"Provider: {provider.name}")
    logger.info(f"Model: {provider.model or '(default)'}")
    logger.info(f"Workspace: {iter_dir}")
    logger.info(f"Evals: {len(evals_data['evals'])}")

    all_timings = {}

    for eval_def in evals_data["evals"]:
        eval_name = eval_def["name"]
        eval_dir = iter_dir / f"eval-{eval_name}"
        eval_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "eval_id": eval_def["id"],
            "eval_name": eval_name,
            "prompt": eval_def["prompt"],
            "expected_output": eval_def["expected_output"],
            "assertions": eval_def.get("assertions", []),
        }
        with open(eval_dir / "eval_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"  [{eval_name}]")
        timings = {}

        if not args.skip_with_skill:
            timings["with_skill"] = run_single_eval(eval_def, skill_path, eval_dir, "with_skill", provider)

        if not args.skip_baseline:
            timings["without_skill"] = run_single_eval(eval_def, None, eval_dir, "without_skill", provider)

        all_timings[eval_name] = timings

    summary = {
        "skill": skill_name,
        "iteration": iteration,
        "provider": provider.name,
        "model": provider.model or "(default)",
        "eval_count": len(evals_data["evals"]),
        "timings": all_timings,
    }
    with open(iter_dir / "run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.success(f"Done. Results in: {iter_dir}")
    logger.info("Next steps:")
    logger.info(f"  1. Review outputs in {iter_dir}/eval-*/{{with,without}}_skill/outputs/")
    logger.info("  2. Draft assertions based on what you see")
    logger.info(f"  3. Run: vespaskills grade --iteration {iteration}")
    logger.info(f"  4. Run: vespaskills aggregate --iteration {iteration}")
