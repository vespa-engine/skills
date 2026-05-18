---
name: "elasticsearch-migration"
description: "Migrate from Elasticsearch to Vespa — map ES indices and mappings to Vespa schemas, translate Query DSL to YQL, plan reindexing, and bridge ranking differences. Use when the user mentions migrating from Elasticsearch, ES→Vespa, porting an ES index, or replacing Elasticsearch with Vespa."
---

# Elasticsearch → Vespa Migration

## Overview

This skill guides a migration from an existing Elasticsearch (or OpenSearch) deployment to Vespa.ai. It is the high-level coordinator: it covers the end-to-end flow, the conceptual mapping between the two systems, and the points where divergence is unavoidable (most notably ranking). Detailed work in each phase delegates to the other Vespa skills in this plugin:

- `schema-authoring` — writing `.sd` schemas, indexing pipelines, field types
- `app-package` — services.xml, deployment.xml, embedders, app layout
- `query-builder` — YQL, rank profiles, grouping, ML model integration
- `feed-operations` — bulk feeding, partial updates, conditional writes
- `vespa-cli` — deploy, target config, auth, CI/CD
- `pyvespa` — Python-driven equivalent of the above

**Do not copy Elasticsearch or Vespa documentation into this skill.** Both projects move quickly and embedded docs go stale. Instead, fetch fresh docs on demand using the patterns in [Fetching fresh docs](#fetching-fresh-docs-llm-friendly-resources) and the dedicated `docs/fetching-docs.md`.

## When to use this skill

Trigger this skill when the user says something like:

- "Help me migrate from Elasticsearch to Vespa."
- "I have an ES index — how do I port it to Vespa?"
- "Translate this ES query to Vespa."
- "We're replacing Elasticsearch with Vespa."
- "Map my ES mapping to a Vespa schema."

For pure schema, query, or feeding tasks where the user is *not* coming from Elasticsearch, use the corresponding focused skill (`schema-authoring`, `query-builder`, `feed-operations`) directly instead.

## The migration phases

The [canonical Vespa migration guide](https://docs.vespa.ai/en/learn/migrating-from-elastic-search.html) walks through the flow. We break it into five operational phases below for clarity (the official guide groups some of these together). Fetch the latest version via `https://docs.vespa.ai/en/learn/migrating-from-elastic-search.html.md` (note the `.md` suffix — see [Fetching fresh docs](#fetching-fresh-docs-llm-friendly-resources)).

| Phase | Goal | Tool / Skill |
|---|---|---|
| 1. Export | Pull ES mapping + documents | mapping: `curl /<index>/_mapping`; documents: any tool that produces NDJSON (`elasticdump`, ES scroll API, `_reindex`-to-snapshot). For continuous side-by-side cutover, use **Logstash** with `logstash-output-vespa_feed` instead |
| 2. Convert | Translate ES mapping → Vespa schema (`.sd`) + sample app package | `ES_Vespa_parser.py` (from Vespa sample-apps) as a starting point; manual review required → see `schema-authoring` |
| 3. Generate app package | Wire schemas into a deployable application package | `app-package` skill |
| 4. Deploy | Push the app package to Vespa (Cloud or self-hosted) | `vespa-cli` skill |
| 5. Feed + verify | Load docs into the new app, validate queries and ranking | **`vespa feed` CLI** (recommended — fastest path, wraps the async HTTP/2 vespa-feed-client). Logstash for streaming; `vespa-feed-client` / pyvespa / `/document/v1/` for programmatic. See `feed-operations` + `query-builder` skills |

Treat each phase as a checkpoint. Validate the schema deploys cleanly *before* feeding; validate feeding succeeds *before* tuning ranking; validate functional query parity *before* attempting score parity (which is not always achievable — see [Ranking divergence](#ranking-divergence)).

For the export step, see `docs/parser-and-tooling.md` for the Logstash pipeline, the dump-to-disk alternatives, and the parser's known limitations.

## Concept mapping (cheat sheet)

| Elasticsearch | Vespa |
|---|---|
| index | schema (`.sd` file under `schemas/`) |
| mapping (field types + options) | schema fields + `indexing:` directives |
| `_id` (flat string) | hierarchical document id: `id:namespace:doctype:[group]:user-key` |
| `_source` (raw doc echo) | `indexing: summary` on each field that should be returned |
| (no ES equivalent) | `namespace` — purely a logical id-collision separator in Vespa; pick any short constant string |
| index name / `_index` | the schema name (which is also the document-type segment in the id) |
| Query DSL (JSON) | YQL: `select … from <schema> where …` |
| analyzers / tokenizers / filters | match modes (`text`, `exact`, `word`, `gram`) + linguistics config |
| `keyword` field | string field with `indexing: attribute` + `match: word` (or `exact`) |
| `text` field | string field with `indexing: index` (+ `summary` if returned) |
| numeric / date / boolean | `int`, `long`, `float`, `double`, `byte`, `bool`, `string` (ISO date) — all need `attribute` to filter/sort/rank on |
| `nested` field | `array<struct>` in schema with explicit struct field declarations |
| `object` field | flatten to top-level fields *or* model as a `struct` |
| aliases | document selections + multi-schema queries (no aliasing layer) |
| bulk API (`_bulk`, NDJSON metadata+data lines) | no bulk endpoint — single-doc ops to `/document/v1/` over HTTP/2; throughput via multiplexing in `vespa feed` CLI / `vespa-feed-client` (Java) / pyvespa (async) |
| reindex API | redeploy schema + `vespa visit` to refeed (or use Vespa's reindexing) |
| `function_score` / Painless scoring | rank profile with `first-phase` / `second-phase` / `global-phase` expressions |
| dense_vector + kNN | `tensor<float>(x[N])` field + `nearestNeighbor` operator with HNSW index |
| sparse_vector / ELSER | sparse tensor + `dotProduct` ranking, or use a colbert/splade embedder |
| pipelines (ingest) | `document-processing` cluster in services.xml + custom doc processors |

The full expansion with example before/after snippets lives in `docs/concept-mapping.md`. Load it when the user asks about a specific field type or feature.

## Indexing directives — the critical conceptual shift

Elasticsearch maps a field's *type* (e.g. `text`, `keyword`) to a default set of inverted-index / doc-values behaviors. Vespa makes those choices explicit per field via the `indexing:` pipeline:

| Directive | Enables |
|---|---|
| `index` | Tokenized inverted index → text search, `userQuery()`, BM25, weakAnd |
| `attribute` | Column store → filtering, sorting, grouping, ranking features, fast match |
| `summary` | Field is returned in search results |

A field can have any combination. **A field with no `indexing:` is stored but invisible to queries**, which is the most common first-time-migrator surprise. Two rules of thumb:

- ES `text` field → Vespa `string` with `indexing: index | summary`
- ES `keyword` field used for filters/aggregations → Vespa `string` with `indexing: attribute | summary` and `match: word` (or `exact` for code-style ids)

For the full indexing pipeline grammar, match modes, and linguistics, load the `schema-authoring` skill.

## Ranking divergence

This is the section to read carefully before promising stakeholders "the same results".

- Elasticsearch's default `_score` is BM25 over the matched terms in `text` fields, with optional `function_score` / script scoring on top.
- Vespa scores are **whatever you write in a rank profile** — there is no implicit default. The closest equivalent is a rank profile that uses `bm25(field)` as its `first-phase` expression, but the per-field normalization, length normalization parameters, and tie-breaking behavior are not identical.

How close can you actually get? The November 2024 [Vespa vs Elasticsearch benchmark](https://blog.vespa.ai/elasticsearch-vs-vespa-performance-comparison/) measured top-10 overlap with deliberately apples-to-apples configurations: **0.79 for lexical (WAND), 0.94 for vector (ANN), 0.81 for hybrid**. The residual lexical gap is mostly down to *linguistics* (tokenization on dots, stemmer choice — porter2 came closest to Vespa's default), not BM25 math. Translation: vector parity is achievable; BM25 parity needs Lucene Linguistics on the Vespa side.

Practical implications:

1. **Do not expect bit-for-bit score parity.** Aim for *result-set* parity first (same top-K documents for representative queries), then rank-correlation parity (Spearman / NDCG), then absolute score parity only if a downstream system depends on the score values. ~0.8 lexical overlap with default linguistics is roughly the ceiling.
2. **Rewrite custom scoring as rank profiles.** Painless scripts → ranking expressions. `function_score` modifiers → second-phase or global-phase math over query and document features. The `query-builder` skill has the full rank-profile reference.
3. **Vespa makes multi-phase ranking explicit.** Most ES users do not realize they are doing a single-phase rank with no rescoring. Use the migration as an opportunity to introduce a cheap `first-phase` (BM25 or `nativeRank`) and an expressive `second-phase` (cross-encoder, LightGBM, learned-to-rank).

## Gotchas

1. **`ES_Vespa_parser.py` is a starter, not a finished tool.** It produces a valid skeleton but does not infer good indexing directives, does not model `nested` or `object` fields well, and never produces a useful rank profile. Expect to hand-edit every generated `.sd` file. See `docs/parser-and-tooling.md`.

2. **Document IDs are hierarchical, not flat.** `_id: "abc123"` becomes `id:mynamespace:mydoctype::abc123`. The namespace is a *logical* id-collision separator — it has no functional role beyond that and can be any short constant string (per the [Vespa documents reference](https://docs.vespa.ai/en/documents.html)); the doc-type segment must match the schema name. Picking namespaces *before* feeding is much easier than rewriting IDs afterward.

3. **`keyword` vs `text` mapping is not symmetric.** ES `keyword` fields are case-sensitive exact-match by default; in Vespa, get this with `match: word` on an `attribute`-backed string. ES `text` fields are tokenized and lowercased — Vespa's `indexing: index` does the same by default but the tokenizer is different (linguistics-aware, not ES analyzer-aware). Plan to re-tune analyzers.

   If you need to preserve ES analyzer behavior (custom token filters, language-specific stemmers, edge n-grams, etc.), look at Vespa's **Lucene Linguistics** component — it replaces Vespa's default linguistics with Apache Lucene's, supporting 40 languages and making analyzer parity much easier. Docs: <https://docs.vespa.ai/en/lucene-linguistics.html>. Sample apps (Minimal, Advanced, Going-Crazy, Non-Java): <https://github.com/vespa-engine/sample-apps> under `examples/lucene-linguistics/`. A dedicated "lucene-linguistics-migration" skill may follow as a phase-2 extension.

4. **Nested and object fields need explicit modeling.** Vespa has no implicit `nested` analog; use `array<struct>` for repeated nested objects and reference subfields with `field.subfield` syntax in YQL. Some users prefer to split nested data into a separate parent/child schema with `referenced` joins.

5. **Ranking is not portable.** Translating an ES query is mechanical; translating its scoring is not. Budget time for it explicitly.

6. **The feed APIs work very differently — and the performance picture is asymmetric.** ES uses the [Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html) with NDJSON payloads where each operation is a metadata line + a data line (no metadata line for deletes). **Vespa has no bulk endpoint** — clients write documents individually via `/document/v1/`, and throughput comes from HTTP/2 multiplexing in the underlying [vespa-feed-client](https://docs.vespa.ai/en/vespa-feed-client.html) (which is what `vespa feed` and the Logstash output both wrap). The benchmark numbers ([blog.vespa.ai](https://blog.vespa.ai/elasticsearch-vs-vespa-performance-comparison/), Nov 2024) are predictable, not random:

   | Workload | Winner | Margin (per CPU core) |
   |---|---|---|
   | Initial bootstrap write (empty → 1M docs) | **Elasticsearch** | ~3x |
   | Refeed (rewrite all docs while serving queries) | Vespa | ~comparable |
   | Partial updates (e.g. price/stock) | **Vespa** | ~4x (up to 9x absolute throughput) |
   | Mixed write + query workload | **Vespa** | ~2.5x write, also faster queries |

   Why: ES Lucene segments are immutable, so partial updates do read-update-write (always); Vespa's attribute store is mutable, so most partial updates are in-place. If your real workload is heavy on price/inventory updates (typical e-commerce), expect Vespa to be substantially more CPU-efficient than ES even though raw bootstrap throughput favors ES. For tuning, see `connections` / `max-streams-per-connection` on the feed client — and the `feed-operations` skill.

7. **Vespa is real-time; Elasticsearch is near-real-time.** This is the biggest behavioral change most migrators don't anticipate. When `vespa feed` receives an ack, the document is **already visible in searches** — write-to-visibility is effectively zero. Elasticsearch acks once the doc is in the translog, but visibility waits for the next [refresh](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-refresh.html) (default 1s, but [often pushed much higher in production](https://vinted.engineering/2024/09/05/goodbye-elasticsearch-hello-vespa/) — Vinted went from 300s refresh in ES to 5s end-to-end in Vespa after migrating). Practical impact:
   - Test code that does `feed → refresh → query` against ES can drop the refresh step in Vespa.
   - Code that *relies on* refresh-interval lag (e.g. waiting for an indexing pipeline to "settle") will see Vespa behave differently.
   - For very high-throughput indexing into ES, tuning `refresh_interval` is a common optimization; in Vespa there is no equivalent knob — visibility is always immediate.

8. **Aliases don't exist.** ES alias-based blue/green index swaps map onto Vespa's *application package versioning* (redeploy with a new schema and let convergence handle the cutover) or onto multi-schema queries (`select … from sources schema_v1, schema_v2 where …`). The ES "nightly reindex into a new index + force-merge + alias-swap" pattern doesn't translate — Vespa has no force-merge step (no segment-merge cost) and no alias layer, but it also has no nightly-batch performance windfall to recover. Plan the cutover as a re-deploy, not an index swap.

9. **Date math, scripts, and runtime fields don't translate 1:1.** ES `"now-1d"`, painless filters, and runtime fields each need a Vespa-side analog: relative dates → use the container's `current_time` or compute in the client; painless filters → ranking expressions or document selections; runtime fields → derived fields in the indexing pipeline.

For deeper before/after examples, load `docs/concept-mapping.md` and `docs/query-translation.md`.

## Fetching fresh docs (LLM-friendly resources)

**Critical: prefer fetching live docs over recalling what you remember.** Both Elasticsearch and Vespa evolve faster than any model's training cut-off. Use the patterns below.

### Vespa documentation (LLM-friendly, well-supported)

| Resource | URL | When to use |
|---|---|---|
| llms.txt index | `https://docs.vespa.ai/llms.txt` | Navigate to a specific page when you don't know its URL |
| llms-full.txt | `https://docs.vespa.ai/llms-full.txt` | Bulk-load when the user wants a broad survey (large — token-heavy) |
| Per-page markdown | Any `…/page.html` URL → append `.md` | First choice: you already know the page. The migration guide itself is `https://docs.vespa.ai/en/learn/migrating-from-elastic-search.html.md` |

**Default workflow:** if you know the page, fetch its `.html.md` form via `WebFetch`. Otherwise grab `llms.txt`, find the page, then fetch its `.html.md`. Only reach for `llms-full.txt` for broad multi-topic questions.

### Elasticsearch documentation (no llms.txt available)

Elastic.co does not currently publish an `llms.txt`. Fallbacks, in order of preference:

1. **Source markdown on GitHub.** Elasticsearch reference docs live in `https://github.com/elastic/elasticsearch/tree/main/docs/reference` — fetch raw markdown via `https://raw.githubusercontent.com/elastic/elasticsearch/main/docs/reference/<path>`. This is the authoritative source that the published HTML is built from.
2. **WebFetch on `www.elastic.co/guide/en/elasticsearch/reference/current/…`.** Returns HTML; the model has to interpret it but the content is current.
3. **Probe with `llms-txt-support` first** in case Elastic publishes one in future — cheap insurance and the skill is already on most Claude installs.

**Never paste ES doc content into this skill.** Fetch on demand, summarize for the user, and link to the source.

See `docs/fetching-docs.md` for concrete `WebFetch` invocations and worked examples for both projects.

## Worked starting point

When the user kicks off a migration, the typical first turn looks like:

1. Ask for (or fetch) the ES mapping JSON for the index in question.
2. Walk through the mapping field-by-field, producing a `.sd` schema — defer to `schema-authoring` for syntax.
3. Generate a minimal `services.xml` + `app-package` layout — defer to `app-package`.
4. Feed a small sample of documents into the new app package and confirm `select * from <schema> where true` returns them — defer to `feed-operations`. Catch schema-deploy and ingest issues before pivoting to queries; iterating on the schema is cheaper than iterating on YQL against an empty index.
5. Pick one representative query from their current ES workload and translate it to YQL — defer to `query-translation.md` and `query-builder`.

Resist the urge to do everything in one turn. Each phase has its own gotchas that are easier to surface in isolation.

---

> **For deeper detail**, load `docs/concept-mapping.md` (field-by-field mapping), `docs/query-translation.md` (Query DSL → YQL), `docs/parser-and-tooling.md` (Logstash + `ES_Vespa_parser.py`), or `docs/fetching-docs.md` (LLM-friendly doc-fetching patterns) from this skill's directory as needed.
>
> **Related skills:** `schema-authoring` (for the `.sd` you'll be writing), `app-package` (for services.xml / deployment), `query-builder` (for YQL and rank profiles), `feed-operations` (for bulk feeding), `vespa-cli` (for deploy), `pyvespa` (for a Python-driven workflow).
