# Migration Tooling: ElasticDump + `ES_Vespa_parser.py`

This page covers the two helper tools the Vespa migration guide ships with, plus what each one does *not* do. Treat both as scaffolding — they save you typing the obvious parts, but every migration still needs hand-edits.

> Don't embed tool source code or doc contents here — link to the upstream sources. See `fetching-docs.md` for live URLs.

---

## Phase 1 — exporting from Elasticsearch with `elasticdump`

`elasticdump` (`npm install -g elasticdump`) is the canonical way to get an ES index and its data onto disk as JSON.

### Export the mapping

```bash
elasticdump \
  --input=http://localhost:9200/products \
  --output=mapping.json \
  --type=mapping
```

### Export the documents

```bash
elasticdump \
  --input=http://localhost:9200/products \
  --output=data.json \
  --type=data \
  --limit=1000
```

`--limit` controls the batch size per scroll operation (default 100), not a document cap. The output is **NDJSON** — line-delimited JSON, where each line is a `{ _id, _source, ... }` document. Per the elasticdump README: *"line-delimited JSON files. The dump file itself is not valid JSON, but each line is."* Valid `--type` values include `mapping`, `data`, `settings`, `analyzer`, `alias`, `template`, `component_template`, `index_template`, `policy`, and `index`.

### What to check before moving on

- The mapping JSON has a single top-level `<index>: { mappings: { properties: { ... } } }`. Multi-type indices (legacy) need to be split.
- Document counts in the export match `GET /products/_count` from the source cluster.
- For very large indices, prefer `--type=data` with a stream-to-file consumer rather than the array form — much cheaper to feed later.

Other valid export tools: the ES `_search` scroll API, the `reindex` API to a file system snapshot, or any consumer that writes `_source` objects to JSONL. The Vespa side only cares about the resulting files.

Upstream reference: <https://github.com/elasticsearch-dump/elasticsearch-dump>

---

## Phase 2 — converting the mapping with `ES_Vespa_parser.py`

The Vespa sample-apps repo includes a starter parser that reads an `elasticdump` mapping JSON and emits:

- A skeleton `.sd` schema
- A minimal `services.xml`
- A `feed.json` shaped roughly like Vespa's document JSON format

Find the latest version under: <https://github.com/vespa-engine/sample-apps> (search the tree for `ES_Vespa_parser`). The exact path drifts over time — fetch the current README before linking the user to a permalink.

### Typical invocation

```bash
python ES_Vespa_parser.py \
  --mapping mapping.json \
  --data data.json \
  --output ./vespa-app
```

(Flag names vary by version — read the parser's `--help`.)

### What the parser does well

- Picks a sensible default field type per ES type (`text` → `string`, `keyword` → `string` + attribute, numeric/date pass through).
- Produces a deploy-able app skeleton you can `vespa deploy` immediately, so you have a baseline to iterate from.
- Generates feed-ready JSONL from the exported documents.

### What the parser does *not* do — expect to hand-edit

1. **Rank profile.** The generated default profile is trivial (`nativeRank` or similar). All real ranking — BM25 weighting, second-phase features, learned models — must be added by hand. See the `query-builder` skill.
2. **`nested` and `object` fields.** The parser flattens or skips them. Re-model them as `array<struct>` per `concept-mapping.md`.
3. **Analyzer-specific behavior.** ES analyzers (edge n-gram, stemmer per language, custom token filters) do not survive the conversion. Set `match` mode and language linguistics on each field deliberately.
4. **Embedding fields.** ES `dense_vector` is usually mapped to a tensor without HNSW config — add `index { hnsw { ... } }` and pick a `distance-metric` yourself.
5. **Document IDs.** The parser typically produces `id:default:<schema>::<es-id>`. Pick a real namespace before going to production.
6. **`indexing:` directives.** Defaults are conservative (often just `summary`). Walk every field and decide: do you filter / sort / rank on it? If yes, add `attribute`. Do you search it? If yes, add `index`.

### Validation checklist after running the parser

- `vespa deploy ./vespa-app` succeeds without errors (deploy validates the schema).
- A `vespa query 'select * from <schema> where true' | head` returns hits after feeding.
- A representative ES query, translated to YQL (see `query-translation.md`), returns roughly the right top-K.

---

## Phase 5 — feeding the data

The parser-emitted `feed.json` (or a hand-massaged equivalent) feeds with:

```bash
vespa feed --target <endpoint> feed.json
```

Or, for raw NDJSON without the parser — note `elasticdump` already emits NDJSON, so process it line-by-line rather than treating the file as a JSON array:

```bash
jq -c '{"put": ("id:mynamespace:products::" + ._id), "fields": ._source}' < data.json > feed.jsonl
vespa feed feed.jsonl
```

For partial updates, conditional writes, and tuning feed-client concurrency, defer to the `feed-operations` skill.

---

## When to skip the parser

If the ES mapping is small (< ~20 fields) or unusual (heavy use of nested, custom analyzers, dynamic templates), you'll spend more time fixing the parser output than writing the schema by hand. Consider:

1. Reading the mapping with a human-in-the-loop walkthrough,
2. Writing the `.sd` field-by-field with the `schema-authoring` skill,
3. Generating `feed.json` directly from `data.json` with a small `jq` script as shown above.

This is often faster and gives a cleaner result.

---

## Cross-references

- `concept-mapping.md` — what each parser-output field *should* become
- `query-translation.md` — verifying functional parity after deploy
- `schema-authoring` skill — for hand-tuning the `.sd` files
- `app-package` skill — for the services.xml the parser emits
- `feed-operations` skill — for serious feeding (concurrency, retries, partial updates)
- `vespa-cli` skill — for `vespa deploy` / `vespa feed` mechanics
