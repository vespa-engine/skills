# Elasticsearch Query DSL → YQL

Side-by-side translations for the most common ES query patterns. The aim is *result-set parity* (same matching documents), not bit-for-bit scoring parity — see the ranking discussion in `SKILL.md`.

> For full YQL syntax (operators, grammar, all rank features), use the `query-builder` skill.

All examples assume a schema named `products` with at least: `title` (text/index), `brand` (keyword/attribute), `price` (double/attribute), `published` (long/attribute), `embedding` (tensor with HNSW).

---

## `match` (text search)

**ES:**

```json
{ "query": { "match": { "title": "wireless headphones" } } }
```

**YQL:**

```sql
select * from products where title contains text("wireless headphones");
```

`text()` is the idiomatic translation for ES `match`: you name the target field explicitly, it tokenizes the input via Vespa's linguistics (same as ES `match`), and by default it ORs the resulting tokens with `weakAnd` semantics. Use `text()` when you have the search string in your YQL pipeline and don't need a separate request parameter.

If the search string is supplied as a request parameter (the typical "search box" case), use `userQuery()` instead, which reads from `model.queryString`:

```sql
select * from products where userQuery();
```

with the request parameters `?query=wireless+headphones&default-index=title`. See the `query-builder` skill for the full `text()` / `userInput()` / `userQuery()` annotation surfaces.

---

## `match_phrase`

**ES:**

```json
{ "query": { "match_phrase": { "title": "noise cancelling" } } }
```

**YQL:**

```sql
select * from products where title contains ({grammar:"phrase"}text("noise cancelling"));
```

`text()` with `grammar:"phrase"` tokenizes the input via the same linguistics as `match`, then requires the tokens to occur as an ordered phrase in `title`. Equivalent low-level form: `title contains phrase("noise", "cancelling")` (where you tokenize yourself). Prefer the `text()` form so the linguistics stays consistent with the `match` translation above.

---

## `term` (exact-match on keyword)

**ES:**

```json
{ "query": { "term": { "brand": "sony" } } }
```

**YQL:**

```sql
select * from products where brand contains "sony";
```

The schema must declare `brand` with `indexing: attribute` and a `match` mode — pick deliberately:

| ES `term` semantic | Vespa equivalent | Notes |
|---|---|---|
| Tokens are *not* processed (byte-exact, case-sensitive) | `match: exact` | Strictest equivalent — `"Sony"` and `"sony"` are different |
| Tokens are not split, but case-insensitive (typical with ES `keyword` + lowercase normalizer) | `match: word` | Most common practical equivalent — Vespa's `contains` does token-equality after lower-casing |

If your ES index used a lowercase normalizer on the `keyword` field (very common), `match: word` is the right choice. If you specifically rely on byte-exact identifiers (SKUs, hashes), use `match: exact`. See `concept-mapping.md` for the full schema-side declaration.

---

## `terms` (multi-value match)

**ES:**

```json
{ "query": { "terms": { "brand": ["sony", "bose", "apple"] } } }
```

**YQL:**

```sql
select * from products where brand in ("sony", "bose", "apple");
```

Or, equivalently, with `weightedSet` if you want per-value scoring weights — see `query-builder`.

---

## `range`

**ES:**

```json
{ "query": { "range": { "price": { "gte": 50, "lte": 200 } } } }
```

**YQL:**

```sql
select * from products where range(price, 50, 200);
```

The `range()` operator is the direct equivalent of ES's single `range` query — one clause in, one clause out. Avoid `price >= 50 and price <= 200`: it's two separate clauses to Vespa, which can produce slightly different planning. For half-open intervals use `Infinity` / `-Infinity` (e.g. `range(price, 50, Infinity)`). For inclusive/exclusive bracket syntax, see the query-builder skill.

---

## `bool` (must / should / must_not / filter)

**ES:**

```json
{
  "query": {
    "bool": {
      "must":     [ { "match": { "title": "headphones" } } ],
      "filter":   [ { "term": { "brand": "sony" } } ],
      "should":   [ { "match": { "title": "wireless" } } ],
      "must_not": [ { "range": { "price": { "gt": 500 } } } ]
    }
  }
}
```

**YQL:** wrap the matcher in `rank(...)` so the `should`-style clause influences score but not matching:

```sql
select * from products
where rank(
  title contains "headphones"
    and brand contains "sony"
    and !(price > 500),
  title contains "wireless"
);
```

Per the YQL reference: *"The first, and only the first, argument of the `rank()` function determines whether a document is a match, but all arguments are used for calculating rank features."*

Notes:
- ES `filter` and `must` collapse into the same `and`-clauses inside the first `rank()` argument. The ES distinction (`filter` skips scoring) does not exist in YQL — Vespa controls scoring exclusively via rank profiles.
- ES `must_not` → `!(...)` per the YQL `!` operator.
- ES `should` → additional arguments to `rank(...)`. They contribute rank features (e.g. `bm25(title)` for the matched terms) without changing the match set.
- For "at least N of M should match" with implicit scoring, prefer the `weakAnd` operator instead (see `query-builder`).

---

## `multi_match`

**ES:**

```json
{
  "query": {
    "multi_match": {
      "query": "wireless headphones",
      "fields": ["title^2", "description"]
    }
  }
}
```

**YQL:** declare a `fieldset` in the schema:

```
fieldset default {
    fields: title, description
}
```

Then:

```sql
select * from products where userQuery();
```

with `?query=wireless+headphones&default-index=default` — the request searches all fields in the fieldset. Per-field boosting (`title^2`) moves into the rank profile's `bm25(title) * 2 + bm25(description)` expression.

---

## `function_score` / custom scoring

**ES:**

```json
{
  "query": {
    "function_score": {
      "query": { "match": { "title": "headphones" } },
      "functions": [
        { "field_value_factor": { "field": "popularity", "factor": 1.5 } }
      ],
      "score_mode": "sum"
    }
  }
}
```

**Vespa:** put the math in a rank profile.

```
rank-profile popular_boost {
    first-phase {
        expression: bm25(title) + 1.5 * attribute(popularity)
    }
}
```

Reference at query time with `?ranking.profile=popular_boost`.

For complex multi-stage scoring (filter + cheap rerank + ML model), use Vespa's three-phase ranking (`first-phase`, `second-phase`, `global-phase`) — see `query-builder`.

---

## kNN / vector search

**ES:**

```json
{
  "knn": {
    "field": "embedding",
    "query_vector": [...],
    "k": 10,
    "num_candidates": 100
  }
}
```

**YQL:**

```sql
select * from products
where {targetHits: 100} nearestNeighbor(embedding, q);
```

with `?hits=10` as a separate request parameter.

The mental model is *different* between the two engines, so a 1:1 parameter map is misleading. The idiomatic mapping:

| Elasticsearch | Vespa | What it controls |
|---|---|---|
| `size` (request body) | `hits` request param | Final number of results returned to client |
| `num_candidates` (default `1.5 × k`, must be ≥ `k`) | `targetHits` annotation | HNSW visit count AND candidates exposed to first-phase ranking |
| `k` (default = `size`) | (no separate analog — see below) | ES intermediate kNN result size |

Why the asymmetry: in ES, kNN retrieval has no ranking phase between the HNSW walk and the final result, so ES needs two knobs (`num_candidates` for recall, `k` for output). In Vespa, `targetHits` is *both* the HNSW exploration budget *and* the input to first-phase ranking — the ranking phase replaces ES's separate `k` knob. Set `targetHits` to match the *recall* you want (i.e. ES's `num_candidates`), and use `hits` for the final return size.

Per the [nearest-neighbor-search guide](https://docs.vespa.ai/en/querying/nearest-neighbor-search-guide.html): *"the `hits` parameter controls how many results are returned in the response. Number of `hits` requested does not impact `totalTargetHits`"* — and *"Vespa exposes exactly `targetHits` documents to the first-phase ranking expression"*. So `targetHits` should be substantially larger than `hits` (often 10–100×) to give the ranker a real candidate pool. The Nov 2024 [ES vs Vespa benchmark](https://blog.vespa.ai/elasticsearch-vs-vespa-performance-comparison/) used `targetHits=100, hits=10` for exactly this reason.

**`hnsw.exploreAdditionalHits`** is an *advanced tuning knob*, **defaulting to 0** — don't set it in a migration baseline. Per the Vespa docs, *"increasing hnsw.exploreAdditionalHits improves accuracy (recall@k) at the cost of a slower query"*. It only matters when you've already calibrated `targetHits` and need more graph exploration *without* exposing the extra candidates to ranking (rare; most of the time, just bump `targetHits`). The Vespa blog post ["A Short Guide to Tweaking Vespa's ANN Parameters"](https://blog.vespa.ai/tweaking-ann-parameters/) covers when to reach for it.

Declare the query tensor in the rank profile and pass it at request time:

```
rank-profile semantic {
    inputs {
        query(q) tensor<float>(x[384])
    }
    first-phase {
        expression: closeness(field, embedding)
    }
}
```

Request: `?yql=...&input.query(q)=[...]&hits=10&ranking.profile=semantic`.

Hybrid (text + vector):

```sql
select * from products
where ({targetHits: 100} nearestNeighbor(embedding, q))
   or userQuery();
```

Then rank with a profile that combines `closeness(field, embedding)` and `bm25(title)`. Note `closeness` takes the literal word `field` as its first argument (per the rank-features reference).

Reference: <https://docs.vespa.ai/en/querying/nearest-neighbor-search.html>

---

## `nested` query

### Background — what ES `nested` actually does

Per the [Elasticsearch nested query reference](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-nested-query): the nested query *"searches nested field objects as if they were indexed as separate documents."* Each nested object becomes its own internal Lucene document — so a parent with 100 nested children produces 101 Lucene documents under the hood. This is the *only* way ES preserves per-element relationships in arrays-of-objects; without `nested`, ES flattens arrays of objects at index time and clauses can match across different elements (a "red variant" clause + an "in-stock" clause can be satisfied by *two different* variants, returning a false positive).

So an ES `nested` query is really doing two things at once: (a) telling ES to look inside the special per-element index, and (b) constraining the inner clauses to all match the *same* element.

### Vespa — single subfield (no `sameElement` needed)

If you're just constraining one subfield, you don't need per-element semantics. With `variants` declared as `array<variant>` with `struct-field color` indexed:

**ES:**

```json
{ "query": { "nested": { "path": "variants", "query": { "term": { "variants.color": "red" } } } } }
```

**YQL:**

```sql
select * from products where variants.color contains "red";
```

The dotted-path `variants.color contains "red"` matches any document where any element has color=red — same result-set as the ES nested query above, because there's only one inner clause to satisfy. The schema needs `struct-field color { indexing: attribute }` (or `index`) for the subfield to be queryable; see `concept-mapping.md`.

### Vespa — multiple subfields on the same element (`sameElement`)

This is the *canonical* reason ES `nested` exists, and the only translation that needs `sameElement`:

**ES** (find products with a red, in-stock variant — both conditions on the *same* variant):

```json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "must": [
            { "term":  { "variants.color": "red" } },
            { "range": { "variants.stock": { "gt": 0 } } }
          ]
        }
      }
    }
  }
}
```

**YQL:**

```sql
select * from products
where variants contains sameElement(color contains "red", stock > 0);
```

Per the YQL reference: *"the `sameElement()` operator lets you denote conditions that must match within the same element in multivalue fields containing structs or strings"*. All conditions inside `sameElement(...)` must be satisfied by the *same* struct element.

Without `sameElement`, this is what you get instead — and it's wrong:

```sql
-- BAD: matches docs with ANY red variant AND ANY in-stock variant (possibly different variants)
select * from products
where variants.color contains "red" and variants.stock > 0;
```

A product with a red out-of-stock variant + a blue in-stock variant would match this broken form, but not the corrected `sameElement` form — exactly the false positive that ES `nested` was designed to prevent.

### Schema requirements for `sameElement`

For `sameElement` to work on `array<struct>`, each subfield used in the operator must be exposed via a `struct-field` block with `indexing: attribute` (or `index` for tokenized text). Without it, the subfield isn't queryable. Example minimum schema:

```
field variants type array<variant> {
    indexing: summary
    struct-field color { indexing: attribute  match: word }
    struct-field stock { indexing: attribute }
}
```

`sameElement` also works on `map<key, value>` fields — you can write `where my_map contains sameElement(key contains "Coldplay", value > 10)` to find entries where the key matches AND the value passes the constraint *on the same map entry*. Same indexing rule applies: the `key` and `value` struct-fields must be attribute or index.

### When you don't need it

If your translation has a single subfield constraint (or constraints across truly unrelated subfields where cross-element matches are fine), plain dotted-path YQL is simpler and cheaper. Reach for `sameElement` only when the original ES query used `nested` *and* had multiple inner clauses that needed to apply to the same element.

---

## Aggregations / facets

ES `aggs` ↔ Vespa **grouping**. The shape is very different — Vespa grouping is a YQL-side expression language. Example:

**ES:**

```json
{ "aggs": { "brands": { "terms": { "field": "brand", "size": 10 } } } }
```

**YQL:**

```sql
select * from products
where true
| all(group(brand) max(10) each(output(count() as(brands))));
```

Per the [grouping language reference](https://docs.vespa.ai/en/reference/grouping-syntax.html), `as(label)` attaches to the aggregation *inside* `output(...)` — not to `each(...)`. The label aligns the result key with the ES aggregation name (`"brands": ...`), so consumers reading the response don't have to remap field names. The full grouping grammar is its own surface — load `query-builder/docs/grouping.md` for the full reference.

---

## Sort

**ES:**

```json
{ "sort": [ { "price": "asc" } ] }
```

**YQL:**

```sql
select * from products where ... order by price asc;
```

Vespa sorts on `attribute`-backed fields only.

---

## Pagination

**ES:** `from` + `size` (or `search_after`).

**Vespa:** `offset` + `hits` request parameters, or use `select … limit N offset M`. For deep pagination prefer grouping-based cursors over offset (see `query-builder`).

---

## Highlighting

ES highlighting maps to Vespa's **dynamic summaries + bolding** — less flexible than ES highlighting, but no client-side snippet generation needed. Matched query terms come back wrapped in `<hi>...</hi>` tags inside the returned summary text.

Two pieces:

- In the schema, set `summary: dynamic` on the field (so the summary is computed from matched terms, not the raw value) and `bolding: on` to wrap matches.
- At query time, set `presentation.bolding=true` (or rely on the schema-level config).

Snippet length, match-window, and surround characters are tuned via `vespa.config.search.summary.juniperrc` inside the `<content>` cluster in `services.xml` (parameters: `max_matches`, `length`, `surround_max`, `min_length`).

Reference: <https://docs.vespa.ai/en/document-summaries.html>

Caveat: Vespa's default highlight wrap is the `<hi>` element. Per the schema reference: *"The default XML element used to highlight the search terms is `<hi>` — to override, set `container.qr-searchers` configuration"* — so you *can* swap in `<strong>` / `<em>` / per-tenant tags by configuring `<open>` and `<close>` elements, but it's a container-level config rather than a per-query parameter like in ES. If downstream code depends on highlight-tag flexibility per request, plan a small client-side rewrite.

---

## Cross-references

- `query-builder` skill — full YQL grammar, operators, rank features, grouping, ML model integration
- `concept-mapping.md` (this skill) — for the schema declarations these queries assume
- `fetching-docs.md` (this skill) — for live YQL and rank-feature reference URLs
