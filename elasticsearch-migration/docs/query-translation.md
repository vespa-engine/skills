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
select * from products where userQuery();
```

with the request parameter `?query=wireless headphones&type=any&default-index=title`.

`userQuery()` is the idiomatic form — it integrates with the query-profile-defined parser and lets the user supply parameters at request time. For programmatic inlining without a request parameter, use `userInput("...")` (see the `query-builder` skill for the full `userInput` annotation surface).

---

## `match_phrase`

**ES:**

```json
{ "query": { "match_phrase": { "title": "noise cancelling" } } }
```

**YQL:**

```sql
select * from products where title contains phrase("noise", "cancelling");
```

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

The schema must declare `brand` with `indexing: attribute` and `match: word` (or `exact`) — see `concept-mapping.md`.

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
select * from products where price >= 50 and price <= 200;
```

For inclusive/exclusive bracket syntax (`[50;200]`) see the query-builder skill.

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
where {targetHits: 10} nearestNeighbor(embedding, q);
```

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

**ES:**

```json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": { "term": { "variants.color": "red" } }
    }
  }
}
```

**YQL** (when `variants` is `array<variant>` with `struct-field color` indexed):

```sql
select * from products where variants.color contains "red";
```

For per-element constraints across multiple subfields of the same nested element (the main reason `nested` exists in ES), use Vespa's `sameElement` operator:

```sql
select * from products
where variants contains sameElement(color contains "red", stock > 0);
```

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
| all(group(brand) max(10) each(output(count())));
```

The full grouping grammar is its own surface — load `query-builder/docs/grouping.md` for the full reference.

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

ES highlighting has no native Vespa equivalent at the search API. Common approaches:

- Use `bolding` indexing on the field and request `summary` features that include match positions.
- Generate snippets client-side from the returned `summary` text and the user's query terms.

This is a known gap — surface it to the user early if they depend on it.

---

## Cross-references

- `query-builder` skill — full YQL grammar, operators, rank features, grouping, ML model integration
- `concept-mapping.md` (this skill) — for the schema declarations these queries assume
- `fetching-docs.md` (this skill) — for live YQL and rank-feature reference URLs
