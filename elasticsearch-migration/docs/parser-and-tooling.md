# Migration Tooling: `vespa feed` + `ES_Vespa_parser.py` (with Logstash for streaming)

This page covers the tooling for an ES → Vespa migration: the Vespa sample-apps starter parser for converting the mapping, and the `vespa feed` CLI for loading documents (with Logstash as the alternative for continuous streaming). Treat the parser as scaffolding — it saves you typing the obvious parts, but every migration still needs hand-edits.

> Don't embed tool source code or doc contents here — link to the upstream sources. See `fetching-docs.md` for live URLs.

---

## Phase 1 — exporting from Elasticsearch

You need two things from the source cluster:

- the **mapping**, which drives the Vespa schema (next phase)
- the **documents**, which become Vespa feed input (phase 5)

These have different best tools.

### Export the mapping (curl is enough)

The mapping is small and JSON-shaped. A single ES API call is the simplest path:

```bash
curl -s http://localhost:9200/products/_mapping | jq . > mapping.json
```

This gives you `{ "products": { "mappings": { "properties": { ... } } } }` ready to feed to `ES_Vespa_parser.py` (below) or to read by hand.

### Migrate documents (choose by use case)

Two paths, and the right one depends on whether this is a **one-shot bulk migration** or a **continuous stream**.

#### Recommended for bulk migration: `vespa feed` (CLI)

The `vespa feed` CLI is the fastest and primary recommended way to load documents into Vespa. It uses the high-performance Java [vespa-feed-client](https://docs.vespa.ai/en/clients/vespa-feed-client.html) under the hood (async HTTP/2, dynamic throttling, retries) and outperforms streaming ETL tools for raw throughput. Per Vespa's own pyvespa docs: *"the Vespa CLI is preferred if you really care about performance."*

The CLI feeds JSONL — one Vespa document operation per line. So the typical migration shape is:

1. Snapshot ES `_source` objects to NDJSON (any tool — scroll API, `_reindex`-to-snapshot, or `elasticdump`).
2. Reshape each line into Vespa's `{"put": "id:...", "fields": {...}}` form with a one-liner.
3. Feed.

Example end-to-end:

```bash
# 1. dump from ES (elasticdump is fine for this; line-delimited JSON)
elasticdump \
  --input=http://localhost:9200/products \
  --output=data.json \
  --type=data

# 2. reshape to Vespa feed JSONL
jq -c '{"put": ("id:products:products::" + ._id), "fields": ._source}' \
   < data.json > feed.jsonl

# 3. feed
vespa feed --target <endpoint> feed.jsonl
```

`elasticdump` produces NDJSON — per its README, *"line-delimited JSON files. The dump file itself is not valid JSON, but each line is."* Reference: <https://github.com/elasticsearch-dump/elasticsearch-dump>.

For partial updates, conditional writes, and tuning feed-client concurrency, defer to the `feed-operations` skill.

#### Recommended for continuous streaming: Logstash

When you don't want a one-shot bulk load — e.g. you're running ES and Vespa side-by-side during a multi-week cutover and need to keep them in sync — **Logstash** with `logstash-output-vespa_feed` is the right tool. It reads from ES (or any of its many inputs: Kafka, JDBC, files), transforms in flight, and writes to Vespa with built-in retries, backpressure, and a dead-letter queue for failed docs. No intermediate file on disk.

Vespa's tutorial walks through five recipes, including ES → Vespa: <https://blog.vespa.ai/logstash-vespa-tutorials/>.

Install the Vespa output plugin once:

```bash
bin/logstash-plugin install logstash-output-vespa_feed
```

Minimal `es_to_vespa.conf`:

```
input {
  elasticsearch {
    hosts => ["http://localhost:9200"]
    index => "products"
    docinfo => true
    docinfo_fields => ["_id"]
    docinfo_target => "@metadata"
  }
}

filter {
  mutate {
    add_field => { "id" => "%{[@metadata][_id]}" }
  }
  mutate {
    remove_field => ["@timestamp", "@version"]
  }
}

output {
  vespa_feed {
    vespa_url => "http://localhost:8080"
    document_type => "products"
    namespace => "products"
  }
}
```

Run with:

```bash
bin/logstash -f es_to_vespa.conf
```

#### Programmatic alternatives

For language-native pipelines: [vespa-feed-client](https://docs.vespa.ai/en/clients/vespa-feed-client.html) (Java library — what the CLI wraps), [pyvespa](https://github.com/vespa-engine/pyvespa) (Python async — use `feed_async_iterable` for I/O-bound feeds), or the `/document/v1/` HTTP API directly.

### What to check before moving on

- Mapping JSON has a single top-level `<index>: { mappings: { properties: { ... } } }`. Multi-type indices (legacy) need to be split.
- Document count delivered to Vespa matches `GET /products/_count` from the source cluster.

---

## Phase 2 — converting the mapping with `ES_Vespa_parser.py`

The Vespa sample-apps repo includes a starter parser that reads a mapping JSON and emits:

- A skeleton `.sd` schema
- A minimal `services.xml`
- A `feed.json` shaped roughly like Vespa's document JSON format

Find the latest version under <https://github.com/vespa-engine/sample-apps> (search the tree for `ES_Vespa_parser`). The exact path drifts over time — fetch the current README before linking the user to a permalink.

### Typical invocation

```bash
python ES_Vespa_parser.py \
  --mapping mapping.json \
  --data data.json \
  --output ./vespa-app
```

(Flag names vary by version — read the parser's `--help`.)

The `--data` argument is optional and only useful if you took the dump-to-disk path above. If you're streaming with Logstash, the parser is purely a *schema scaffold* — generate the schema, deploy, then point your Logstash pipeline at the new app.

### What the parser does well

- Picks a sensible default field type per ES type (`text` → `string`, `keyword` → `string` + attribute, numeric/date pass through).
- Produces a deploy-able app skeleton you can `vespa deploy` immediately, so you have a baseline to iterate from.
- Generates feed-ready JSONL from exported documents (when `--data` is provided).

### What the parser does *not* do — expect to hand-edit

1. **Rank profile.** The generated default profile is trivial (`nativeRank` or similar). All real ranking — BM25 weighting, second-phase features, learned models — must be added by hand. See the `query-builder` skill.
2. **`nested` and `object` fields.** The parser flattens or skips them. Re-model them as `array<struct>` per `concept-mapping.md`.
3. **Analyzer-specific behavior.** ES analyzers (edge n-gram, stemmer per language, custom token filters) do not survive the conversion. Set `match` mode and language linguistics on each field deliberately. To stay close to ES analyzer behavior, look at Vespa's Lucene Linguistics component — see `SKILL.md`.
4. **Embedding fields.** ES `dense_vector` is usually mapped to a tensor without HNSW config — add `index { hnsw { ... } }` and pick a `distance-metric` yourself.
5. **Document IDs.** The parser typically produces `id:default:<schema>::<es-id>`. Pick a namespace before going to production.
6. **`indexing:` directives.** Defaults are conservative (often just `summary`). Walk every field and decide: do you filter / sort / rank on it? If yes, add `attribute`. Do you search it? If yes, add `index`.

### Validation checklist after running the parser

- `vespa deploy ./vespa-app` succeeds without errors (deploy validates the schema).
- After feeding a sample with Logstash (or `vespa feed`), `vespa query 'select * from <schema> where true' | head` returns hits.
- A representative ES query, translated to YQL (see `query-translation.md`), returns roughly the right top-K.

---

## Phase 5 — feeding the data

The primary recommended path is the `vespa feed` CLI (fastest, async HTTP/2 with dynamic throttling). Feed the parser-emitted `feed.json` (or a hand-massaged JSONL equivalent) with:

```bash
vespa feed --target <endpoint> feed.json
```

Or, from raw NDJSON dumped from ES, reshape and feed in two steps:

```bash
jq -c '{"put": ("id:mynamespace:products::" + ._id), "fields": ._source}' < data.json > feed.jsonl
vespa feed feed.jsonl
```

**Streaming alternative** — if you set up a Logstash pipeline in phase 1 (incremental cutover, side-by-side ES + Vespa), repoint its `vespa_url` / `document_type` at the new app and you're done; the same pipeline handles ongoing writes.

**Programmatic alternative** — use [vespa-feed-client](https://docs.vespa.ai/en/clients/vespa-feed-client.html) (Java), [pyvespa](https://github.com/vespa-engine/pyvespa) (Python async, `feed_async_iterable` for best throughput), or the `/document/v1/` HTTP API directly.

The `feed-operations` skill covers partial updates, conditional writes, and feed-client concurrency tuning.

---

## When to skip the parser

If the ES mapping is small (< ~20 fields) or unusual (heavy use of nested, custom analyzers, dynamic templates), you'll spend more time fixing the parser output than writing the schema by hand. Consider:

1. Reading the mapping with a human-in-the-loop walkthrough,
2. Writing the `.sd` field-by-field with the `schema-authoring` skill,
3. Dumping documents from ES and reshaping with `jq` straight into `vespa feed` (steps shown in phase 5 above).

This is often faster and gives a cleaner result.

---

## Cross-references

- `concept-mapping.md` — what each parser-output field *should* become
- `query-translation.md` — verifying functional parity after deploy
- `schema-authoring` skill — for hand-tuning the `.sd` files
- `app-package` skill — for the services.xml the parser emits
- `feed-operations` skill — for serious feeding (concurrency, retries, partial updates)
- `vespa-cli` skill — for `vespa deploy` / `vespa feed` mechanics
