"""CLI entry point for vespaskills."""

import argparse
import sys
from pathlib import Path

from vespaskills.evals.config import EVALS_JSON, TRIGGER_EVALS_CSV


def main():
    parser = argparse.ArgumentParser(
        prog="vespaskills",
        description="Vespa AI skills evaluation framework",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- eval (injection mode — prepends SKILL.md into prompt) ---
    p_eval = subparsers.add_parser("eval", help="Run skill evaluations (injection mode)")
    p_eval.add_argument("--eval", type=str, help="Run specific eval by name")
    p_eval.add_argument("--iteration", type=int, help="Iteration number (default: auto)")
    p_eval.add_argument("--skip-baseline", action="store_true", help="Skip without-skill runs")
    p_eval.add_argument("--skip-with-skill", action="store_true", help="Skip with-skill runs")
    p_eval.add_argument("--evals-json", type=Path, default=EVALS_JSON, help="Path to evals.json")
    p_eval.add_argument("--model", type=str, help="Model override")
    p_eval.add_argument(
        "--provider",
        type=str,
        choices=["claude", "codex"],
        help="Coding agent harness (default: EVAL_PROVIDER env var or 'claude')",
    )

    # --- eval-discovery (discovery mode — plugin loaded via --plugin-dir) ---
    p_disc = subparsers.add_parser(
        "eval-discovery",
        help="Run evaluations in discovery mode (plugin via --plugin-dir)",
    )
    p_disc.add_argument("--eval", type=str, help="Run specific eval by name")
    p_disc.add_argument("--iteration", type=int, help="Iteration number (default: auto)")
    p_disc.add_argument("--skip-baseline", action="store_true", help="Skip without-plugin runs")
    p_disc.add_argument("--skip-with-skill", action="store_true", help="Skip with-plugin runs")
    p_disc.add_argument("--evals-json", type=Path, default=EVALS_JSON, help="Path to evals.json")
    p_disc.add_argument("--model", type=str, help="Model override")

    # --- grade ---
    p_grade = subparsers.add_parser("grade", help="Grade eval outputs")
    p_grade.add_argument("--iteration", type=int, required=True, help="Iteration number")
    p_grade.add_argument("--eval", type=str, help="Grade specific eval by name")
    p_grade.add_argument("--llm-rubric", action="store_true", help="Use LLM-based rubric grading")
    p_grade.add_argument("--evals-json", type=Path, default=EVALS_JSON)
    p_grade.add_argument(
        "--workspace-suffix",
        type=str,
        default="",
        help="Workspace dir suffix (e.g. '-discovery' for eval-discovery outputs)",
    )

    # --- aggregate ---
    p_agg = subparsers.add_parser("aggregate", help="Aggregate grading results into benchmark")
    p_agg.add_argument("--iteration", type=int, required=True)
    p_agg.add_argument("--evals-json", type=Path, default=EVALS_JSON)
    p_agg.add_argument(
        "--workspace-suffix",
        type=str,
        default="",
        help="Workspace dir suffix (e.g. '-discovery' for eval-discovery outputs)",
    )
    p_agg.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress markdown report stdout (still written to file)"
    )

    # --- trigger ---
    p_trig = subparsers.add_parser("trigger", help="Run skill trigger evaluations")
    p_trig.add_argument("--csv", type=Path, default=TRIGGER_EVALS_CSV)
    p_trig.add_argument("--skill", type=str, help="Filter by skill name")
    p_trig.add_argument("--id", type=str, help="Run specific test by ID")
    p_trig.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Trials per test (default: 1, recommended: 3)",
    )
    p_trig.add_argument("--timeout", type=int, default=90, help="Timeout per run in seconds")

    # --- generate ---
    p_gen = subparsers.add_parser("generate", help="Generate AGENTS.md and README skills table")
    p_gen.add_argument(
        "--check",
        action="store_true",
        help="Validate artifacts are up-to-date (CI mode)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "eval":
        from vespaskills.evals.run_evals import run

        run(args)
    elif args.command == "eval-discovery":
        from vespaskills.evals.run_discovery_evals import run

        run(args)
    elif args.command == "grade":
        from vespaskills.evals.grade import run

        run(args)
    elif args.command == "aggregate":
        from vespaskills.evals.aggregate import run

        run(args)
    elif args.command == "trigger":
        from vespaskills.evals.run_trigger_evals import run

        run(args)
    elif args.command == "generate":
        from vespaskills.generate import run

        run(args)


if __name__ == "__main__":
    main()
