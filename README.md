# Vespa.ai Skills

AI coding assistant skills for [Vespa.ai](https://vespa.ai). Works with **Claude Code**, **OpenAI Codex**, **Google Gemini CLI**, and **Cursor**.

Each skill is a self-contained folder with a `SKILL.md` as the single source of truth and a `docs/` folder with detailed reference material.

## Installation

### Vespa CLI (recommended)

The [Vespa CLI](https://docs.vespa.ai/en/vespa-cli.html) can install skills directly for Claude Code, Codex, Cursor and Antigravity CLI - no manual cloning required:

```bash
vespa skills install
```

Run `vespa skills list` to see available skills, and `vespa skills update` to refresh previously installed skills to the latest version.

### npx skills

[`npx skills`](https://github.com/vercel-labs/skills) installs skills into any of 70+ supported agent harnesses (Claude Code, Cursor, Codex, and just about every other agent harness):

```bash
npx skills add vespaai-playground/skills
```

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
4. Add an entry to `.claude-plugin/marketplace.json`
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
