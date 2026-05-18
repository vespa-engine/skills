"""Aggregate grading and timing results into benchmark.json.

Usage:
    vespaskills aggregate --iteration 1
"""

import json
import math
import sys
from pathlib import Path

from vespaskills.evals.config import REPO_ROOT
from vespaskills.logger import get_logger

logger = get_logger()


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _fmt(key: str, value: float) -> str:
    if key == "pass_rate" or key == "invocation_rate":
        return f"{value:.1%}"
    if key == "cost_usd":
        return f"${value:.4f}"
    if key == "duration_ms":
        return f"{value / 1000:,.1f}s"
    return f"{value:,.0f}"


def _signed(key: str, value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{_fmt(key, abs(value))}"


def render_markdown(benchmark: dict) -> str:
    """Render benchmark.json content as a markdown report."""
    skill = benchmark.get("skill", "?")
    iteration = benchmark.get("iteration", "?")
    summary = benchmark.get("run_summary", {})
    delta = benchmark.get("delta", {})
    per_eval = benchmark.get("per_eval", {})

    metric_keys = (
        "pass_rate",
        "invocation_rate",
        "duration_ms",
        "total_input_tokens",
        "output_tokens",
        "cost_usd",
    )

    def cell(stats: dict, key: str) -> str:
        if key not in stats:
            return "—"
        v = stats[key]
        return _fmt(key, v["mean"] if isinstance(v, dict) else v)

    lines = [f"# Skill Benchmark — {skill} (iteration {iteration})", ""]

    if summary:
        lines += [
            "## Summary (mean per eval)",
            "",
            "| Metric | with_skill | without_skill | Δ abs | Δ % |",
            "|---|---:|---:|---:|---:|",
        ]
        w = summary.get("with_skill", {})
        wo = summary.get("without_skill", {})
        for k in metric_keys:
            if k not in w and k not in wo:
                continue
            d_abs = _signed(k, delta[k]) if k in delta else "—"
            pct = delta.get(f"{k}_pct")
            d_pct = f"{'+' if pct >= 0 else ''}{pct:.1%}" if pct is not None else "—"
            lines.append(f"| {k.replace('_', ' ')} | {cell(w, k)} | {cell(wo, k)} | {d_abs} | {d_pct} |")
        lines.append("")
        n = w.get("eval_count") or wo.get("eval_count") or "?"
        invoked = w.get("invoked_count")
        if invoked is not None:
            lines.append(f"- Evals: **{n}**, invoked (with_skill): **{invoked}/{n}**")
        else:
            lines.append(f"- Evals: **{n}**")
        lines.append("")

    if per_eval:
        lines += [
            "## Per-eval breakdown",
            "",
            "| Eval | pass (with) | pass (without) | invoked | cost (with) | cost (without) |",
            "|---|:---:|:---:|:---:|---:|---:|",
        ]
        for name, runs in per_eval.items():
            w = runs.get("with_skill", {})
            o = runs.get("without_skill", {})
            wp = f"{w['passed']}/{w['total']}" if "passed" in w else "—"
            op = f"{o['passed']}/{o['total']}" if "passed" in o else "—"
            inv = "✓" if w.get("invoked") else ("✗" if "invoked" in w else "—")
            wc = _fmt("cost_usd", w["cost_usd"]) if "cost_usd" in w else "—"
            oc = _fmt("cost_usd", o["cost_usd"]) if "cost_usd" in o else "—"
            lines.append(f"| {name} | {wp} | {op} | {inv} | {wc} | {oc} |")
        lines.append("")

    return "\n".join(lines)


def mean_stddev(values: list[float]) -> dict:
    if not values:
        return {"mean": 0, "stddev": 0}
    n = len(values)
    m = sum(values) / n
    if n < 2:
        return {"mean": round(m, 4), "stddev": 0}
    variance = sum((x - m) ** 2 for x in values) / (n - 1)
    return {"mean": round(m, 4), "stddev": round(math.sqrt(variance), 4)}


def run(args):
    """Run aggregate command with parsed args."""
    with open(args.evals_json) as f:
        evals_data = json.load(f)

    skill_name = evals_data["skill_name"]
    suffix = getattr(args, "workspace_suffix", "") or ""
    iter_dir = REPO_ROOT / f"{skill_name}-workspace{suffix}" / f"iteration-{args.iteration}"

    if not iter_dir.exists():
        logger.error(f"{iter_dir} not found")
        sys.exit(1)

    usage_keys = (
        "duration_ms",
        "total_input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "input_tokens",
        "output_tokens",
        "cost_usd",
    )
    configs: dict[str, dict[str, list]] = {
        "with_skill": {"pass_rate": [], "invoked": [], **{k: [] for k in usage_keys}},
        "without_skill": {"pass_rate": [], "invoked": [], **{k: [] for k in usage_keys}},
    }
    per_eval = {}

    for eval_dir in sorted(iter_dir.iterdir()):
        if not eval_dir.is_dir() or not eval_dir.name.startswith("eval-"):
            continue
        eval_name = eval_dir.name.removeprefix("eval-")
        per_eval[eval_name] = {}

        for run_type in ("with_skill", "without_skill"):
            run_dir = eval_dir / run_type
            grading = load_json(run_dir / "grading.json")
            timing = load_json(run_dir / "timing.json")

            if not grading and not timing:
                continue

            entry = {}
            if grading:
                entry["pass_rate"] = grading["summary"]["pass_rate"]
                entry["passed"] = grading["summary"]["passed"]
                entry["total"] = grading["summary"]["total"]
                configs[run_type]["pass_rate"].append(grading["summary"]["pass_rate"])

            if timing:
                entry["duration_ms"] = timing.get("duration_ms", 0)
                entry["exit_code"] = timing.get("exit_code", -1)
                for key in (*usage_keys, "num_turns", "invoked", "mode"):
                    if key in timing:
                        entry[key] = timing[key]
                for key in usage_keys:
                    if key in timing:
                        configs[run_type][key].append(timing[key])
                if "invoked" in timing:
                    configs[run_type]["invoked"].append(bool(timing["invoked"]))

            per_eval[eval_name][run_type] = entry

    run_summary = {}
    for config_name, metrics in configs.items():
        if not metrics["pass_rate"] and not any(metrics[k] for k in usage_keys):
            continue
        summary_entry = {"eval_count": len(metrics["pass_rate"])}
        if metrics["pass_rate"]:
            summary_entry["pass_rate"] = mean_stddev(metrics["pass_rate"])
        if metrics["invoked"]:
            summary_entry["invocation_rate"] = round(sum(metrics["invoked"]) / len(metrics["invoked"]), 4)
            summary_entry["invoked_count"] = sum(metrics["invoked"])
        for key in usage_keys:
            if metrics[key]:
                summary_entry[key] = mean_stddev(metrics[key])
                summary_entry[f"{key}_total"] = round(sum(metrics[key]), 4)
        run_summary[config_name] = summary_entry

    delta = {}
    if "with_skill" in run_summary and "without_skill" in run_summary:
        w, wo = run_summary["with_skill"], run_summary["without_skill"]
        if "pass_rate" in w and "pass_rate" in wo:
            delta["pass_rate"] = round(w["pass_rate"]["mean"] - wo["pass_rate"]["mean"], 4)
        for key in usage_keys:
            if key in w and key in wo:
                diff = w[key]["mean"] - wo[key]["mean"]
                delta[key] = round(diff, 4)
                if wo[key]["mean"]:
                    delta[f"{key}_pct"] = round(diff / wo[key]["mean"], 4)

    benchmark = {
        "skill": skill_name,
        "iteration": args.iteration,
        "run_summary": run_summary,
        "delta": delta,
        "per_eval": per_eval,
    }

    out_path = iter_dir / "benchmark.json"
    with open(out_path, "w") as f:
        json.dump(benchmark, f, indent=2)

    md_path = iter_dir / "benchmark.md"
    md = render_markdown(benchmark)
    md_path.write_text(md, encoding="utf-8")

    if not getattr(args, "quiet", False):
        print(md)
    logger.success(f"Saved to: {out_path}")
    logger.success(f"Markdown report: {md_path}")
