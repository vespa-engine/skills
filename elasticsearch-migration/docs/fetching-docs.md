# Fetching Fresh ES and Vespa Documentation

This page is the detail behind the "Fetching fresh docs" section of `SKILL.md`. It documents *how* to retrieve current documentation at query time so the skill itself never embeds (and never stales) the source material.

> Prefer fetching over recalling. Both projects move fast. If the user is going to act on a doc citation, verify it against the live source.

---

## Vespa — LLM-friendly endpoints

Vespa actively supports LLM-driven workflows. There are three retrieval modes; pick by use case.

### 1. Per-page markdown (`.html.md`) — preferred

Any Vespa documentation page accepts a `.md` suffix and returns clean markdown. **Note**: many older URLs (e.g. `/en/reference/schema-reference.html`) now serve only a redirect stub — fetch the `.md` form of the *current* canonical path, which you can get from `llms.txt` (see below). Examples (verified current at time of writing):

| Page | URL |
|---|---|
| Migration guide | `https://docs.vespa.ai/en/learn/migrating-from-elastic-search.html.md` |
| Schemas (basics) | `https://docs.vespa.ai/en/basics/schemas.html.md` |
| Schema reference | `https://docs.vespa.ai/en/reference/schemas/schemas.html.md` |
| YQL reference | `https://docs.vespa.ai/en/reference/querying/yql.html.md` |
| Rank features | `https://docs.vespa.ai/en/reference/ranking/rank-features.html.md` |
| Document JSON format | `https://docs.vespa.ai/en/reference/schemas/document-json-format.html.md` |
| Nearest neighbor search | `https://docs.vespa.ai/en/querying/nearest-neighbor-search.html.md` |
| HNSW / ANN | `https://docs.vespa.ai/en/querying/approximate-nn-hnsw.html.md` |
| Grouping | `https://docs.vespa.ai/en/querying/grouping.html.md` |
| Ranking intro | `https://docs.vespa.ai/en/ranking/ranking-intro.html.md` |
| Indexing language | `https://docs.vespa.ai/en/reference/writing/indexing-language.html.md` |
| Attributes | `https://docs.vespa.ai/en/content/attributes.html.md` |
| Tensor user guide | `https://docs.vespa.ai/en/ranking/tensor-user-guide.html.md` |

Workflow:

```
WebFetch(url="https://docs.vespa.ai/en/reference/schemas/schemas.html.md",
         prompt="Summarize the indexing pipeline grammar and list all valid indexing directives.")
```

If a URL returns a "Redirecting…" stub, fetch `llms.txt` and re-resolve the canonical path — the doc tree is reorganized periodically.

This is the cheapest and most precise option when you already know which page you need.

### 2. `llms.txt` — the curated index

When you don't know the exact page, fetch:

```
https://docs.vespa.ai/llms.txt
```

This is a structured list of canonical docs (titles + URLs). Use it as a router: parse it, pick the relevant page, then fetch that page's `.html.md` form.

### 3. `llms-full.txt` — the firehose

```
https://docs.vespa.ai/llms-full.txt
```

A concatenated corpus of the canonical documentation suitable for one-shot ingestion. **Token-heavy** — use only when the user explicitly wants breadth (e.g. "give me an overview of Vespa's capabilities") or when you're seeding context for a longer migration session.

### Heuristic

```
known page → fetch .html.md
unknown page → fetch llms.txt → find page → fetch .html.md
broad survey → fetch llms-full.txt
```

---

## Elasticsearch — no llms.txt (yet)

Elastic.co does not currently publish an `llms.txt` or `llms-full.txt`. As of this writing:

```
https://www.elastic.co/llms.txt                                            → 404
https://www.elastic.co/guide/en/elasticsearch/reference/current/llms.txt   → 404
```

Use fallbacks in this order.

### Fallback 1 — source markdown on GitHub (preferred)

Most current Elastic reference docs are authored in markdown in the `elastic/docs-content` repo (the unified docs source); some legacy material still lives under `docs/` in `elastic/elasticsearch`. Try the new repo first:

- **Canonical (new):** <https://github.com/elastic/docs-content/tree/main/reference>
  Raw base: `https://raw.githubusercontent.com/elastic/docs-content/main/reference/<path>`
- **Legacy (still has content):** <https://github.com/elastic/elasticsearch/tree/main/docs>
  Raw base: `https://raw.githubusercontent.com/elastic/elasticsearch/main/docs/<path>`

Example:

```
WebFetch(url="https://raw.githubusercontent.com/elastic/docs-content/main/reference/query-languages/query-dsl/query-dsl-match-query.md",
         prompt="Extract the parameters and defaults for the match query.")
```

Caveats:
- Exact file layout shifts between major versions and between the two repos as content is migrated. If a path 404s, browse the tree on GitHub for the new location, or pin a version branch instead of `main`.
- Some pages live in adjacent repos (`elasticsearch-net`, `kibana`, integrations). Search the `elastic/` org if neither of the above has it.

### Fallback 2 — WebFetch on the published HTML

The current canonical URL pattern is `https://www.elastic.co/docs/...` (the legacy `https://www.elastic.co/guide/en/elasticsearch/reference/current/...` pattern is partially redirected but many pages now 404 there):

```
WebFetch(url="https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query",
         prompt="...")
```

Common path prefixes under `/docs/`:
- `/docs/reference/elasticsearch/mapping-reference/...` — field types (`text`, `keyword`, `dense_vector`, `sparse_vector`, …)
- `/docs/reference/query-languages/query-dsl/...` — Query DSL pages
- `/docs/reference/aggregations/...` — aggregations
- `/docs/api/doc/elasticsearch/operation/...` — REST API operations (e.g. `_bulk`)

Use this when GitHub source is awkward (deeply versioned references, generated pages, language-specific client docs).

### Fallback 3 — probe with `llms-txt-support` first

If the `llms-txt-support` skill is available in the session, run it against `elastic.co` and any other vendor doc site at the start of the migration. It's a cheap probe in case the vendor has added an `llms.txt` since this skill was written. The skill returns immediately with a "not found" if no llms.txt exists.

---

## Anti-patterns

**Don't:**

- Quote ES or Vespa documentation from memory when the user is about to act on it. The doc may have changed.
- Paste large doc excerpts into this skill's files. They will go stale. Link instead.
- Trust the first GitHub path you remember — verify the file exists at the expected path on `main` (or the user's version branch).
- Use `llms-full.txt` for a single-page question. It's wasteful.

---

## Quick-reference URLs (verify before relying on them)

| Resource | URL |
|---|---|
| Vespa migration guide (markdown) | <https://docs.vespa.ai/en/learn/migrating-from-elastic-search.html.md> |
| Vespa llms.txt | <https://docs.vespa.ai/llms.txt> |
| Vespa llms-full.txt | <https://docs.vespa.ai/llms-full.txt> |
| Vespa schema reference | <https://docs.vespa.ai/en/reference/schemas/schemas.html.md> |
| Vespa YQL reference | <https://docs.vespa.ai/en/reference/querying/yql.html.md> |
| Elasticsearch reference (HTML, current) | <https://www.elastic.co/docs/reference/elasticsearch> |
| Elasticsearch Query DSL (HTML) | <https://www.elastic.co/docs/reference/query-languages/query-dsl> |
| Elasticsearch REST API (HTML) | <https://www.elastic.co/docs/api/doc/elasticsearch> |
| Elasticsearch docs source (new) | <https://github.com/elastic/docs-content/tree/main/reference> |
| Elasticsearch docs source (legacy) | <https://github.com/elastic/elasticsearch/tree/main/docs> |
| ElasticDump | <https://github.com/elasticsearch-dump/elasticsearch-dump> |
| Vespa sample-apps (parser lives here) | <https://github.com/vespa-engine/sample-apps> |
