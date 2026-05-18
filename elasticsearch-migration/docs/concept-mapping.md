# ES → Vespa Concept Mapping (field-by-field)

This is the expanded reference for the cheat sheet in `SKILL.md`. Each section shows a representative ES mapping snippet and the equivalent Vespa schema declaration, plus the *why* behind any non-obvious translation. Use it when the user asks about a specific field type.

> Always verify against the current docs — both ES and Vespa evolve. See `fetching-docs.md` for live URLs.

---

## Index → Schema

An ES index maps to a Vespa schema. The schema file name, the `schema` declaration, and the inner `document` declaration must all match.

**ES** (mapping API):

```json
PUT /products
{
  "mappings": { "properties": { ... } }
}
```

**Vespa** (`schemas/products.sd`):

```
schema products {
    document products {
        # fields go here
    }

    rank-profile default {
        first-phase { expression: nativeRank }
    }
}
```

The schema must also be referenced from `services.xml`:

```xml
<documents>
  <document type="products" mode="index"/>
</documents>
```

See `app-package` skill for services.xml details.

---

## `text` field

**ES:**

```json
"title": { "type": "text", "analyzer": "standard" }
```

**Vespa:**

```
field title type string {
    indexing: index | summary
}
```

- `indexing: index` tokenizes and adds to the inverted index (text search).
- `indexing: summary` makes the field available in returned hits (the ES `_source` echo).
- Use `nativeRank` (Vespa's default rank feature, computed without extra config) as the first-phase expression. It's the safest starting point for migrations because BM25 parity with ES requires matching Lucene analyzers as well — see Vespa's Lucene Linguistics component referenced from `SKILL.md`.
- Once you've configured Lucene Linguistics (or accepted Vespa's default linguistics), opt into BM25 by adding `index { enable-bm25 }` to the field and using `bm25(title)` in the rank profile. Per the rank-features reference: *"the field must be enabled to be used with the bm25 feature; set the enable-bm25 flag in the index section of the field definition."*

Vespa's default tokenizer is linguistics-aware (CJK, accent folding, stemming by language) but is *not* the ES standard analyzer. Plan to compare hit sets on representative queries; do not expect identical tokenization.

Reference: <https://docs.vespa.ai/en/reference/schemas/schemas.html>

---

## `keyword` field

**ES:**

```json
"sku": { "type": "keyword" }
```

**Vespa:**

```
field sku type string {
    indexing: attribute | summary
    attribute: fast-search
    match: word
}
```

- `indexing: attribute` puts the field in the column store (filtering, sorting, grouping, ranking).
- `attribute: fast-search` adds a B-tree dictionary for sub-linear `=` and range lookups (use for high-cardinality filter fields).
- `match: word` makes the comparison case-insensitive token-equality (closest to ES `keyword`). Use `match: exact` for code-style identifiers where you want byte-exact equality.

Reference: <https://docs.vespa.ai/en/content/attributes.html>

---

## Numeric, date, boolean

**ES:**

```json
"price":     { "type": "double" },
"in_stock":  { "type": "boolean" },
"published": { "type": "date" }
```

**Vespa:**

```
field price type double {
    indexing: attribute | summary
}

field in_stock type bool {
    indexing: attribute | summary
}

field published_raw type string {
    indexing: summary
}

field published type long {
    indexing: input published_raw | to_epoch_second | attribute | summary
}
```

- Always add `indexing: attribute` if you intend to filter, sort, group, or rank on the field. Without it, the value is stored but unusable in WHERE clauses.
- **Vespa has no `date` field type. Best practice is to use a `long`** holding seconds-since-epoch — per the [indexing docs](https://docs.vespa.ai/en/writing/indexing.html#date-indexing). If the ES source ships ISO-8601 strings, route them through the `to_epoch_second` indexing primitive as shown.
- For a "last-modified" style field, declare it **outside** the `document` block with `indexing: now | attribute | summary` to get a synthetic per-update timestamp.
- Avoid storing dates as strings if you need range queries; the `long` form gives you efficient inclusive/exclusive ranges and ordering.

Reference: <https://docs.vespa.ai/en/writing/indexing.html#date-indexing>

---

## `dense_vector` (kNN search)

**ES:**

```json
"embedding": {
  "type": "dense_vector",
  "dims": 384,
  "index": true,
  "similarity": "cosine"
}
```

**Vespa:**

```
field embedding type tensor<float>(x[384]) {
    indexing: summary | attribute | index
    attribute {
        distance-metric: prenormalized-angular
    }
    index {
        hnsw {
            max-links-per-node: 16
            neighbors-to-explore-at-insert: 200
        }
    }
}
```

- Valid `distance-metric` values per the schema reference: `euclidean`, `angular`, `dotproduct`, `prenormalized-angular`, `hamming`, `geodegrees`.
- **Normalize embeddings at the embedder layer and use the dot-product family on both sides.** Elasticsearch 8.12+ internally treats `similarity: cosine` as "dot product over normalized vectors", and its recommended high-performance setting is `similarity: dot_product` with caller-normalized vectors. The Vespa equivalent is `distance-metric: prenormalized-angular` (skips the at-query normalization). This is also the apples-to-apples convention used in the [Nov 2024 Elasticsearch vs Vespa benchmark](https://blog.vespa.ai/elasticsearch-vs-vespa-performance-comparison/): both engines configured with normalized embeddings + dot-product / prenormalized-angular, yielding ~0.94 top-10 vector overlap. Use plain `angular` only if you genuinely cannot normalize at the embedder.
- HNSW parameter equivalence:

  | ES (`dense_vector` index_options) | Vespa (`index { hnsw { ... } }`) | ES default | Vespa default |
  |---|---|---|---|
  | `m` | `max-links-per-node` | 16 | 16 |
  | `ef_construction` | `neighbors-to-explore-at-insert` | 100 | **200** |

  Note the `ef_construction` asymmetry: Vespa's default is 2× ES's, which biases toward recall over indexing speed. The benchmark referenced above set both engines to `M=16, ef_construction=200` (the [original HNSW paper](https://arxiv.org/abs/1603.09320) defaults) to compare apples-to-apples — a reasonable target if you want recall parity rather than ES-default behavior. If you specifically need to reproduce ES defaults, set `neighbors-to-explore-at-insert: 100`.
- Note that Elasticsearch 8.14+ changed the default `dense_vector` index type to `int8_hnsw` (scalar quantization to bytes). The benchmark kept ES on `hnsw` (float) to compare at equal precision; if your source index uses `int8_hnsw`, configure Vespa with an int8 tensor (`tensor<int8>(x[N])`) for the same accuracy/footprint tradeoff.
- For very high recall you can also use `nearestNeighbor` without an HNSW index (brute force over the attribute) — useful for smaller collections, and per the benchmark this is what *both* engines fall back to when the pre-filter matches very few docs.

Reference: <https://docs.vespa.ai/en/approximate-nn-hnsw.html>

---

## `sparse_vector` (ELSER-style)

**ES:**

```json
"tokens": { "type": "sparse_vector" }
```

**Vespa:**

```
field tokens type tensor<float>(t{}) {
    indexing: attribute | summary
}
```

Rank with a tensor dot-product in the rank profile (e.g. `sum(query(t) * attribute(tokens))`); see the `query-builder` skill for the exact expression form. For ELSER-equivalent quality, consider Vespa's built-in `splade-embedder` (see `app-package` skill — embedders section) rather than reusing the ES tokens directly.

Reference: <https://docs.vespa.ai/en/ranking/tensor-user-guide.html>

---

## `nested` field

**ES:**

```json
"variants": {
  "type": "nested",
  "properties": {
    "color": { "type": "keyword" },
    "stock": { "type": "integer" }
  }
}
```

**Vespa** — both `struct` and the `array<struct>` field are declared **inside** the `document` block:

```
schema products {
    document products {

        struct variant {
            field color type string {}
            field stock type int {}
        }

        field variants type array<variant> {
            indexing: summary
            struct-field color {
                indexing: attribute
                attribute: fast-search
                match: word
            }
            struct-field stock {
                indexing: attribute
            }
        }
    }
}
```

- Vespa does not have a `nested` type. Use `array<struct>` with `struct-field` declarations to expose subfields to the indexing pipeline.
- The schema reference is explicit: `struct` is *"contained in document"*. Declaring it outside is a deploy error.
- When you have **few parents and many children** (e.g. a small product catalogue with many reviews per product, or a tenant config referenced by many events), prefer a parent/child schema split with `reference` joins instead of inlining everything as `array<struct>`. Covered in `schema-authoring`.

Reference: <https://docs.vespa.ai/en/reference/schemas/schemas.html>

---

## `object` field (flat / un-nested)

**ES:**

```json
"address": {
  "properties": {
    "city": { "type": "keyword" },
    "zip":  { "type": "keyword" }
  }
}
```

**Vespa option A** — flatten:

```
field address_city type string { indexing: attribute | summary  match: word }
field address_zip  type string { indexing: attribute | summary  match: word }
```

**Vespa option B** — struct:

```
struct address {
    field city type string {}
    field zip  type string {}
}

field address type address {
    indexing: summary
    struct-field city { indexing: attribute  match: word }
    struct-field zip  { indexing: attribute  match: word }
}
```

Prefer flattening for simple two-or-three-field objects; prefer struct when you want to keep the original grouping in returned hits.

---

## Document ID

**ES:**

```
_id: "abc123"
```

**Vespa:**

```
id:mynamespace:products::abc123
```

Format breakdown: `id:<namespace>:<schema>:[<group>]:<user-defined-key>`.

- `namespace` is a *logical* id-collision separator — per the [Vespa documents reference](https://docs.vespa.ai/en/documents.html), it "has no function in Vespa beyond [collision-prevention], and can just be set to any short constant value". It is **not** a tenant boundary or security boundary.
- `<schema>` must match the schema name (here `products`).
- `[<group>]` is optional and used for streaming search / grouping; leave empty for plain indexed docs.
- `<user-defined-key>` is what corresponds to the ES `_id`.

Pick the namespace and group convention *before* feeding. Rewriting IDs after the fact is painful.

Reference: <https://docs.vespa.ai/en/reference/schemas/document-json-format.html>

---

## Bulk feeding (ES `_bulk` ↔ `vespa feed` over HTTP/2)

Note these are *not* directly equivalent APIs. **Vespa has no bulk endpoint** — clients send single-document operations to `/document/v1/`, and throughput comes from HTTP/2 multiplexing inside the feed client. The wire shape and concurrency model are different; only the JSON payload of an individual `put` looks similar.

**ES** (`POST /_bulk`, NDJSON with alternating metadata + data lines):

```
{ "index": { "_index": "products", "_id": "abc123" } }
{ "title": "Widget", "price": 9.99 }
```

**Vespa** (JSONL file, one self-contained document operation per line):

```json
{"put": "id:mynamespace:products::abc123", "fields": {"title": "Widget", "price": 9.99}}
```

The Vespa form needs no separate metadata line — the id and operation type are encoded in the `put` field itself.

**Primary path — the `vespa feed` CLI** (fastest, async HTTP/2 with dynamic throttling — wraps the same Java client as below):

```bash
vespa feed --target <endpoint> docs.jsonl
```

Alternatives when the CLI doesn't fit the workflow:

| Client | Use when | Reference |
|---|---|---|
| `vespa-feed-client` (Java) | Embedding the same high-throughput client into a JVM service / CI pipeline | <https://docs.vespa.ai/en/clients/vespa-feed-client.html> |
| `pyvespa` (Python, async) | Python data pipelines, notebooks — use `feed_async_iterable` for I/O-bound feeds | <https://github.com/vespa-engine/pyvespa> |
| `/document/v1/` HTTP API | Any language, no SDK needed | <https://docs.vespa.ai/en/reference/document-v1-api-reference.html> |
| Logstash `vespa_feed` output | Continuous streaming ETL (ES, Kafka, JDBC) — not for raw one-shot throughput | <https://blog.vespa.ai/logstash-vespa-tutorials/> |

Use the `feed-operations` skill for partial updates, conditional writes, and visiting/exports.

Reference: <https://docs.vespa.ai/en/reference/document-json-format.html>

---

## Aliases

Vespa has no alias layer. Two patterns approximate the common use cases:

- **Blue/green index swap** → redeploy the application package with a new schema version; Vespa's deploy convergence handles the cutover.
- **Read across multiple indices** → YQL `select … from sources s1, s2 where …` queries multiple schemas in one call.

---

## Pipelines / ingest processors

**ES:** ingest pipelines (`processors: [...]`).

**Vespa:** prefer the schema's **`indexing:` pipeline** if it does what you need — it covers lowercase, tokenize, embed, split, join, attribute writes, conditional transforms, and more, all declaratively in the `.sd` file. Only reach for a custom Java **document processor** (declared via a `document-processing` cluster in `services.xml`) when the indexing language genuinely can't express the transformation (e.g. external lookups, multi-document side effects, complex stateful logic).

For embedding text → vector inline at indexing time, use the `embed` indexing primitive with a configured embedder component — no Java required (see `app-package` skill).

---

## Cross-references

- `schema-authoring` — for the full schema grammar, match modes, rank-profile syntax, linguistics
- `query-builder` — for the full YQL surface and rank-feature catalog
- `app-package` — for services.xml, embedders, deployment
- `feed-operations` — for the full document JSON format and feed-CLI tuning
- `fetching-docs.md` (in this skill) — for live-doc retrieval patterns
