# Vespa.ai Skills

AI coding assistant skills for [Vespa.ai](https://vespa.ai). Works with **Claude Code**, **OpenAI Codex**, **Google Gemini CLI**, and **Cursor**.

Each skill is a self-contained folder with a `SKILL.md` as the single source of truth and a `docs/` folder with detailed reference material.

## Installation

### Claude Code

Add the marketplace and install skills using `/plugin` inside Claude Code:

```
/plugin marketplace add vespaai-playground/skills
/plugin install schema-authoring
/plugin install app-package
/plugin install query-builder
/plugin install feed-operations
/plugin install vespa-cli
/plugin install pyvespa
/plugin install elasticsearch-migration
```

Or from a local clone:

```bash
git clone git@github.com:vespaai-playground/skills.git
```
```
/plugin marketplace add ./skills
/plugin install schema-authoring
```

### OpenAI Codex

Clone the repo into your project (or a parent directory). Codex reads `AGENTS.md` automatically when present in the working tree:

```bash
git clone git@github.com:vespaai-playground/skills.git
```

### Google Gemini CLI

```bash
git clone git@github.com:vespaai-playground/skills.git
# Gemini CLI reads AGENTS.md automatically when present in the working tree
```

### Cursor

Clone the repo — Cursor discovers skills via `.cursor-plugin/`:

```bash
git clone git@github.com:vespaai-playground/skills.git
# Cursor reads .cursor-plugin/plugin.json automatically
```

> **Private repos**: All platforms work with local clones, so public vs private doesn't matter — just clone via SSH and the tools read from the local filesystem.

## Skills

<!-- SKILLS:BEGIN -->
| Skill | Description |
|-------|-------------|
| [`app-package`](app-package/SKILL.md) | Scaffold and configure Vespa application packages, including services.xml, schemas, deployment.xml, query profiles, and embedder components. |
| [`elasticsearch-migration`](elasticsearch-migration/SKILL.md) | Migrate from Elasticsearch to Vespa — map ES indices and mappings to Vespa schemas, translate Query DSL to YQL, plan reindexing, and bridge ranking differences. Use when the user mentions migrating from Elasticsearch, ES→Vespa, porting an ES index, or replacing Elasticsearch with Vespa. |
| [`feed-operations`](feed-operations/SKILL.md) | Vespa document CRUD operations and bulk feeding — covers document ID format, JSON wire format for put/update/remove, REST API endpoints, CLI commands, partial updates, conditional writes, bulk feeding, and document visiting/export. |
| [`pyvespa`](pyvespa/SKILL.md) | Python API for Vespa.ai — define schemas, deploy applications, feed documents, query, and manage Vespa from Python using pyvespa. |
| [`query-builder`](query-builder/SKILL.md) | Build Vespa YQL queries and design rank profiles. Covers YQL syntax, operators, grouping, rank-profile phases, ML model integration, and query tensor inputs. |
| [`schema-authoring`](schema-authoring/SKILL.md) | Writing, validating, and evolving Vespa .sd schema files — covers field types, indexing pipelines, match modes, tensors, rank profiles, structs, fieldsets, and common pitfalls. |
| [`vespa-cli`](vespa-cli/SKILL.md) | Vespa CLI for deploying, managing, and debugging Vespa.ai applications -- covers target configuration, authentication, deployment lifecycle, production pipelines, document operations, log inspection, testing, and CI/CD integration. |
<!-- SKILLS:END -->

## Example Prompts

**Schema authoring:**
> "Create a Vespa schema for a product catalog with title, description, price, category, and a 384-dim embedding for semantic search."

**Application package:**
> "Scaffold a Vespa application package with a HuggingFace embedder for the e5-small-v2 model."

**Query building:**
> "Write a hybrid search query that combines BM25 text matching with nearest-neighbor vector search, using reciprocal rank fusion."

**Feed operations:**
> "Generate a JSONL feed file for 3 sample products and show me the vespa feed command to load them."

## Development

### Generating artifacts

A single script generates all platform-specific manifests from the `SKILL.md` files:

```bash
python generate.py          # Generate AGENTS.md, cursor/plugin.json, README table
python generate.py --check  # CI mode — exits 1 if any generated file is out of date
```

### Evaluations

Run the skill benchmark suite with `uv run vespaskills eval` / `eval-discovery` / `aggregate`. See [`evals/README.md`](evals/README.md) for the commands and an example report.

### Adding a new skill

1. Create a new folder at the root: `my-skill/`
2. Add a `SKILL.md` with YAML frontmatter (`name` and `description`)
3. Add reference docs in `my-skill/docs/` as needed
4. Add an entry to `platforms/claude/marketplace.json`
5. Run `python generate.py`

## Contributing

Contributions are welcome! Please:

1. Keep `SKILL.md` files under 500 lines — use `docs/` for detailed references
2. Run `python generate.py --check` before submitting a PR
3. Verify technical accuracy against [docs.vespa.ai](https://docs.vespa.ai)

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Links

- [Vespa Documentation](https://docs.vespa.ai)
- [Vespa GitHub](https://github.com/vespa-engine/vespa)
- [Sample Applications](https://github.com/vespa-engine/sample-apps)

Copyright Vespa.ai. Licensed under the terms of the Apache 2.0 license. See LICENSE in the project root.
