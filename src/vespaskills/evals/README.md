# Skill Evaluations

Measure whether Vespa skills improve Claude's output quality on realistic tasks.

## Two Eval Types

**Quality evals** (`run_evals.py`) — Do skills produce better outputs?
- Injects skill content directly into the prompt (controlled comparison)
- Runs each task with and without the skill, compares outputs
- Graded with deterministic checks + LLM rubrics

**Trigger evals** (`run_trigger_evals.py`) — Do skills activate on the right prompts?
- Uses `--plugin-dir` so Claude discovers skills naturally
- Parses stream-json events to detect which skills were invoked
- Tests both should-trigger and should-NOT-trigger cases

## Quick Start

```bash
# Quality evals: run all for schema-authoring
uv run python evals/run_evals.py

# Quality evals: run a single eval
uv run python evals/run_evals.py --eval gotcha-heavy-schema

# Grade outputs (after reviewing and adding assertions to evals.json)
uv run python evals/grade.py --iteration 1

# Grade with LLM rubric (needs ANTHROPIC_API_KEY)
uv run python evals/grade.py --iteration 1 --llm-rubric

# Aggregate results into benchmark.json
uv run python evals/aggregate.py --iteration 1

# Trigger evals: test skill invocation
uv run python evals/run_trigger_evals.py

# Trigger evals: single test
uv run python evals/run_trigger_evals.py --id sa-03

# Trigger evals: multiple trials for reliability
uv run python evals/run_trigger_evals.py --trials 3
```

## Workflow

Following the [skill-creator eval methodology](https://github.com/anthropics/skills/tree/main/skills/skill-creator):

1. **Write prompts** in `evals/evals.json` (no assertions yet)
2. **Run evals** with `run_evals.py` — launches Claude with and without the skill
3. **Review outputs** manually in `{skill}-workspace/iteration-N/eval-*/`
4. **Draft assertions** based on what you observe, add to `evals.json`
5. **Grade** with `grade.py` (deterministic checks + optional LLM rubric)
6. **Aggregate** with `aggregate.py` to produce `benchmark.json`
7. **Iterate** on the skill, rerun into `iteration-N+1/`

## Directory Structure

```
evals/
├── evals.json              # Quality eval test cases (prompts + assertions)
├── trigger_evals.csv       # Trigger eval test cases (should/should-not trigger)
├── config.py               # Path constants
├── providers.py            # Provider abstraction (Claude CLI, Codex CLI)
├── run_evals.py            # Quality eval runner
├── run_trigger_evals.py    # Trigger eval runner
├── grade.py                # Graders: deterministic + LLM rubric
├── aggregate.py            # Benchmark aggregation
└── README.md

schema-authoring-workspace/     # Created by runners (gitignored)
└── iteration-1/
    ├── eval-gotcha-heavy-schema/
    │   ├── eval_metadata.json
    │   ├── with_skill/
    │   │   ├── outputs/        # Files Claude produced
    │   │   ├── timing.json
    │   │   ├── transcript.json
    │   │   └── grading.json    # After running grade.py
    │   └── without_skill/
    │       └── ...
    ├── run_summary.json
    └── benchmark.json          # After running aggregate.py
```

## Assertion Types

Add assertions to `evals.json` after reviewing first outputs:

```json
{
  "assertions": [
    {"type": "file_exists", "path": "*.sd", "text": "Schema file exists"},
    {"type": "content_contains", "path": "*.sd", "pattern": "schema product", "text": "Correct schema name"},
    {"type": "content_matches", "path": "*.sd", "pattern": "tensor<float>\\(x\\[768\\]\\)", "text": "768-dim tensor"}
  ]
}
```

| Type | Fields | Checks |
|------|--------|--------|
| `file_exists` | `path` (glob) | File matching pattern exists |
| `content_contains` | `path`, `pattern` | File contains exact string |
| `content_matches` | `path`, `pattern` | File matches regex |

## Model Override

```bash
# Use default model
uv run python evals/run_evals.py

# Override model
uv run python evals/run_evals.py --model claude-sonnet-4-20250514
```

## Harnesses

Quality evals (`run_evals.py`) can run against either Claude Code or OpenAI
Codex. Discovery and trigger evals remain Claude-only because they depend on
`--plugin-dir` and stream-json event parsing.

```bash
# Default (Claude Code)
vespaskills eval

# OpenAI Codex CLI
vespaskills eval --provider codex
vespaskills eval --provider codex --model <codex-model>

# Or pin via env var (useful for CI):
EVAL_PROVIDER=codex vespaskills eval
```

The codex harness calls `codex exec --json --sandbox workspace-write -C <outputs>`
inside each eval's `outputs/` directory. (`codex exec` is non-interactive by
design, so `workspace-write` is sufficient without the broader
`--dangerously-bypass-approvals-and-sandbox`.) Run `codex --help` to list valid
`-m/--model` values for your installed CLI version.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EVAL_PROVIDER` | `claude` | Harness to use: `claude` or `codex` |
| `EVAL_MODEL` | (CLI default) | Model to use |
| `EVAL_TIMEOUT` | `180` (claude) | Timeout per run in seconds; also used as codex fallback |
| `CODEX_TIMEOUT` | `600` | Codex-specific timeout override (codex is slower than claude) |
| `EVAL_MAX_TURNS` | `20` | Max agent turns per run (Claude only) |
| `CLAUDE_CLI` | `claude` | Path to Claude CLI binary |
| `CODEX_CLI` | `codex` | Path to Codex CLI binary |

## Plugin Setup

The `skills/` directory contains symlinks to the skill directories, enabling
Claude Code plugin discovery via `--plugin-dir .`. This is used by the trigger
eval runner.

If the `vespa-support` plugin (from `vespa-claude`) is installed at user scope
and interferes with trigger evals, disable it for this workspace:

```json
// .claude/settings.local.json
{
  "enabledPlugins": {
    "vespa-support@vespa-claude": false
  }
}
```

## Writing Good Trigger Eval Prompts

Claude only consults skills for tasks it can't easily handle on its own.
Simple questions (e.g. "how do I add BM25 ranking?") won't trigger skills
because Claude answers from training data. Trigger eval prompts must be
**substantive, multi-step tasks** where consulting the skill adds real value.

**Won't trigger** (too simple):
```
how do I add BM25 ranking to my Vespa schema?
```

**Will trigger** (actionable task):
```
Create a vespa schema for a recipe search app — it needs fields for title,
ingredients as an array, cooking_time integer, a 512-dim embedding for semantic
search with HNSW, and a hybrid rank profile. Write it to schemas/recipe.sd
```

## Adding Evals for Other Skills

1. Add test cases to `evals.json` (or create a new one) with `skill_name` and `skill_path`
2. Run: `uv run python evals/run_evals.py --evals-json path/to/evals.json`
3. Same grade/aggregate workflow applies
4. For trigger evals, add rows to `trigger_evals.csv` and update `SKILL_TRIGGER_PATTERNS` in `run_trigger_evals.py`
