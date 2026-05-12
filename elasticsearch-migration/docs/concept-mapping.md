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
    index {
        enable-bm25
    }
}
```

- `indexing: index` tokenizes and adds to the inverted index (text search).
- `indexing: summary` makes the field available in returned hits (the ES `_source` echo).
- `index { enable-bm25 }` lets the rank profile use `bm25(title)` as a feature. Per the rank-features reference: *"the field must be enabled to be used with the bm25 feature; set the enable-bm25 flag in the index section of the field definition."*

Vespa's tokenizer is linguistics-aware (CJK, accent folding, stemming by language) but is *not* the ES standard analyzer. Plan to compare hit sets on representative queries; do not expect identical tokenization.

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

field published type long {
    indexing: attribute | summary
}
```

- Always add `indexing: attribute` if you intend to filter, sort, group, or rank on the field. Without it, the value is stored but unusable in WHERE clauses.
- Vespa has no first-class date type; the convention is `long` holding seconds-since-epoch (or use a `string` if you want ISO-8601 readability — at the cost of range queries).

Reference: <https://docs.vespa.ai/en/reference/schemas/schemas.html>

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
        distance-metric: angular
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
- `angular` is cosine distance. Use `prenormalized-angular` when your vectors are already unit-normalized — it skips the normalization step at query time and is faster.
- HNSW defaults (per the schema reference): `max-links-per-node: 16`, `neighbors-to-explore-at-insert: 200`. Tune per your recall/latency target.
- For very high recall you can also use `nearestNeighbor` without an HNSW index (brute force over the attribute) — useful for smaller collections.

Reference: <https://docs.vespa.ai/en/querying/approximate-nn-hnsw.html>

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
- For very large nested collections, prefer a parent/child schema split with `reference` joins (covered in `schema-authoring`).

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

- `namespace` is a tenant-level grouping (any non-empty string). Pick one per logical dataset.
- `<schema>` must match the schema name (here `products`).
- `[<group>]` is optional and used for streaming search.
- `<user-defined-key>` is what corresponds to the ES `_id`.

Pick the namespace and group convention *before* feeding. Rewriting IDs after the fact is painful.

Reference: <https://docs.vespa.ai/en/reference/schemas/document-json-format.html>

---

## Bulk feeding (ES `_bulk` ↔ `vespa feed`)

**ES:**

```
POST /_bulk
{ "index": { "_index": "products", "_id": "abc123" } }
{ "title": "Widget", "price": 9.99 }
```

**Vespa** (JSONL file, one document per line):

```json
{"put": "id:mynamespace:products::abc123", "fields": {"title": "Widget", "price": 9.99}}
```

Feed with:

```bash
vespa feed --target <endpoint> docs.jsonl
```

Use the `feed-operations` skill for partial updates, conditional writes, and visiting/exports.

Reference: <https://docs.vespa.ai/en/reference/schemas/document-json-format.html>

---

## Aliases

Vespa has no alias layer. Two patterns approximate the common use cases:

- **Blue/green index swap** → redeploy the application package with a new schema version; Vespa's deploy convergence handles the cutover.
- **Read across multiple indices** → YQL `select … from sources s1, s2 where …` queries multiple schemas in one call.

---

## Pipelines / ingest processors

**ES:** ingest pipelines (`processors: [...]`).

**Vespa:** declare a `document-processing` cluster in `services.xml` and write custom doc processors (Java) or use the schema's `indexing:` pipeline for inline transformations (lowercase, tokenize, embed, etc.).

For embedding text → vector inline at indexing time, use the `embed` indexing primitive with a configured embedder component (see `app-package` skill).

---

## Cross-references

- `schema-authoring` — for the full schema grammar, match modes, rank-profile syntax, linguistics
- `query-builder` — for the full YQL surface and rank-feature catalog
- `app-package` — for services.xml, embedders, deployment
- `feed-operations` — for the full document JSON format and feed-CLI tuning
- `fetching-docs.md` (in this skill) — for live-doc retrieval patterns
