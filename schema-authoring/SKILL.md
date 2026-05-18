---
name: "schema-authoring"
description: "Writing, validating, and evolving Vespa .sd schema files — covers field types, indexing pipelines, match modes, tensors, rank profiles, structs, fieldsets, and common pitfalls."
---

# Vespa Schema Authoring

## Overview

A Vespa **schema** (`.sd` file) defines a document type: its fields, indexing behavior, matching rules, and ranking configuration. Schemas live under `schemas/` in a Vespa application package.

This skill applies when the user needs to create, modify, or troubleshoot `.sd` schema files -- including field definitions, indexing pipelines, match modes, tensor/HNSW config, rank profiles, structs, fieldsets, or document references.

> **For deeper detail**, load `docs/field-types.md`, `docs/schema-patterns.md`, `docs/tensors-and-hnsw.md`, `docs/example-ecommerce-schema.md`, or `docs/gotchas-extended.md` from this skill's directory as needed.

## Quick Reference

| Concept | Purpose | Syntax |
|---|---|---|
| Field | Named, typed data element | `field title type string { ... }` |
| Indexing pipeline | Controls storage/indexing | `indexing: summary \| index` |
| Match mode | How queries match content | `match { exact }` |
| Attribute | In-memory column for sort/group/filter | `indexing: attribute` |
| Index | Inverted index for text search | `indexing: index` |
| Summary | Included in result output | `indexing: summary` |
| Tensor | Multi-dimensional numeric data | `tensor<float>(x[384])` |
| HNSW | ANN index on tensors | `index { hnsw { ... } }` |
| Struct | Composite sub-type | `struct address { ... }` |
| Fieldset | Virtual group of fields | `fieldset default { fields: title, body }` |
| Rank profile | Scoring configuration | `rank-profile bm25 { ... }` |
| Reference | Parent-child document link | `reference<parent_schema>` |

## Minimal Skeleton

```sd
schema my_doc {
    document my_doc {
        field title type string {
            indexing: summary | index
            match: text
        }
    }
    fieldset default { fields: title }
    rank-profile default {
        first-phase { expression: nativeRank(title) }
    }
}
```

The outer `schema` name and inner `document` name must match.

## Field Types

### Primitive Types

| Type | Description | Typical indexing |
|---|---|---|
| `string` | UTF-8 text | `summary \| index` or `summary \| attribute` |
| `int` | 32-bit signed integer | `summary \| attribute` |
| `long` | 64-bit signed integer | `summary \| attribute` |
| `float` | 32-bit IEEE 754 | `summary \| attribute` |
| `double` | 64-bit IEEE 754 | `summary \| attribute` |
| `bool` | Single-bit boolean | `summary \| attribute` |
| `byte` | 8-bit signed integer | `summary \| attribute` |
| `position` | Lat/lon geo pair (microdegrees) | `summary \| attribute` |
| `uri` | URL with host/path tokenization | `summary \| index` |
| `predicate` | Boolean constraint expressions | `summary \| attribute` |
| `raw` | Opaque byte blob, not searchable | `summary` |

### Reference and Tensor Types

| Type | Description |
|---|---|
| `reference<schema_name>` | Foreign key for parent-child joins via `import field` |
| `tensor<float>(x[N], y{})` | Multi-dimensional tensor; indexed `[N]` and mapped `{}` dims |

### Collection Types

- **`array<T>`** -- Ordered list. Supports `index` and `attribute`.
- **`weightedset<T>`** -- Set with integer weights. T must be `string`, `int`, or `long`.
- **`map<K, V>`** -- Key-value map. K must be `string`, `int`, or `long`. Index sub-fields via `struct-field`.

```sd
field tags type array<string> {
    indexing: summary | index
}
field scores type weightedset<string> {
    indexing: summary | attribute
}
field properties type map<string, string> {
    indexing: summary
    struct-field key   { indexing: attribute   match: exact }
    struct-field value { indexing: attribute }
}
```

## Indexing Pipeline

A field's `indexing` statement is a `|`-separated pipeline of directives.

- **`index`** -- Disk-backed inverted index. Required for `match: text` and linguistic search. Supports stemming, normalization, proximity data.
- **`attribute`** -- In-memory column store. Required for sorting, grouping, filtering, and access in ranking expressions.
- **`summary`** -- Include in search result output. Without this, field values are not returned.

### Common Combinations

```sd
field title type string       { indexing: summary | index }              # text search + results
field category type string    { indexing: summary | attribute            # filter + results
                                match: exact   rank: filter }
field description type string { indexing: summary | index | attribute }  # search + filter + results
field quality type double     { indexing: attribute }                    # ranking only
field html type string        { indexing: summary }                     # retrieval only
```

### Attribute Modifiers

Pick by workload, not by default:

| Modifier | When to use |
|---|---|
| `fast-search` | Filter / range queries on this attribute, or attribute-only exact match (`=` query prefix). Adds a B-tree. Not supported on dense (indexed-only) tensors. |
| `fast-access` | Attribute is read on every query and you have memory headroom. Replicated to all nodes. Not supported on predicate, tensor, or reference attributes. |
| `paged` | **Opt-in only when memory is the binding constraint.** Backs the attribute by disk so it can be paged out, trading RAM for I/O. Costs: unpredictable query latency, ~2x disk usage, unreliable memory metrics, and high system CPU under load. **Strongly discouraged in combination with HNSW** (random access during feeding tanks throughput). Do not add by default — only when the user explicitly asks to reduce memory and accepts these trade-offs. See [Vespa docs](https://docs.vespa.ai/en/content/attributes.html#paged-attributes-disadvantages). |

### Input Expressions

Transform data inline: `lowercase`, `normalize`, `tokenize`, `to_int`, `to_long`, `to_string`, `to_array`, `set_language`.

```sd
field title_lower type string {
    indexing: input title | lowercase | summary | index
}
```

## Match Modes

| Mode | Behavior | Use case |
|---|---|---|
| `text` | Tokenized, stemmed, normalized (default) | Free-text search |
| `word` | Exact single-token, no stemming | Tags, labels, enums |
| `exact` | Entire value must match exactly | IDs, SKUs, emails |
| `prefix` | Prefix matching | Autocomplete |
| `substring` | Any substring (expensive) | Prefer `gram` instead |
| `gram` | Character n-gram index | CJK text, substring search |
| `cased` | Case-sensitive matching | Case-sensitive identifiers |

```sd
field body type string     { indexing: summary | index   match: text }
field sku type string      { indexing: summary | index   match: exact }
field suggest type string  { indexing: summary | index   match: prefix }
field cjk type string      { indexing: summary | index   match { gram   gram-size: 2 } }
```

Note: `match: word` and `match: exact` require `index`. For attribute-only exact matching, use `fast-search` and query with the `=` prefix operator.

## Tensor Fields and HNSW Configuration

Tensor type syntax: `tensor<value-type>(dimension-list)`. Indexed dims `x[N]`, mapped dims `x{}`, mixed `tensor<float>(cat{}, x[128])`. Configure HNSW under `index { hnsw { ... } }` on a tensor attribute field.

Default skeleton for an embedding field. Do **not** add `paged` here — it is strongly discouraged with HNSW (see Attribute Modifiers table above):

```sd
field embedding type tensor<float>(x[768]) {
    indexing: attribute | index
    attribute {
        distance-metric: prenormalized-angular   # for already-normalized vectors; use `angular` otherwise
    }
    index { hnsw { max-links-per-node: 16  neighbors-to-explore-at-insert: 200 } }
}
```

For the full distance-metric table, HNSW parameter guidance, and a complete tensor-field example, load `docs/tensors-and-hnsw.md`.

## Struct Types

Define composite types with `struct` inside `document`. Use `struct-field` to index inner fields.

```sd
struct address {
    field street type string {}
    field city type string {}
    field country type string {}
}
field warehouse type address {
    indexing: summary
    struct-field city    { indexing: attribute   match: exact }
    struct-field country { indexing: attribute   match: exact }
}
field locations type array<address> {
    indexing: summary
    struct-field city { indexing: attribute }
}
```

Structs can be used inside `array<>` and `map<>` collections.

## Fieldsets

Combine fields for unified search. Declared at `schema` level, outside `document`.

```sd
fieldset default {
    fields: title, body, description
}
```

All fields in a fieldset must be the same type (string) with compatible match/indexing modes.

## Rank Profiles

### Structure and Key Elements

```sd
rank-profile hybrid inherits default {
    inputs {
        query(query_embedding) tensor<float>(x[384])
        query(text_weight) double: 0.7
    }
    function text_score() {
        expression: bm25(title) * 2 + bm25(body)
    }
    function vector_score() {
        expression: closeness(field, embedding)
    }
    first-phase {
        expression: text_score
    }
    second-phase {
        expression: query(text_weight) * normalize_linear(text_score) + (1 - query(text_weight)) * normalize_linear(vector_score)
        rerank-count: 200
    }
    match-features {
        text_score
        vector_score
    }
}
```

| Element | Purpose |
|---|---|
| `inherits` | Inherit from another rank profile |
| `inputs` | Query-time inputs (tensors, scalars with defaults) |
| `first-phase` | Score all matching documents |
| `second-phase` | Re-score top N from first phase |
| `rerank-count` | N for second-phase (default 100) |
| `function` | Reusable sub-expression |
| `match-features` | Features returned in results for debugging |
| `summary-features` | Features in full document summaries |
| `constants` | Named numeric constants |
| `global-phase` | Cross-node re-ranking (Vespa 8+) |

Rank profiles support **inheritance** -- child profiles override or extend parent definitions via `inherits`.

## Schema Evolution Warnings

**Reserved field names** (cause conflicts): `documentid`, `relevance`, `sddocname`.

**Type changes:** Changing a field type (e.g., `string` to `int`) requires reindexing and `validation-overrides.xml`. Widening (`int` to `long`) is safe; narrowing is not.

**Removing fields:** First remove all references in rank profiles, fieldsets, and summaries, then remove the field. Stop feeding the field before removal.

**Adding fields:** Safe on a running system. Existing documents get empty/default values. Attribute fields consume memory even when empty.

For a comprehensive production example combining BM25, semantic search, structs, maps, weightedsets, and phased ranking (default/bm25_ranking/semantic/hybrid/personalized profiles), load `docs/example-ecommerce-schema.md`.

## Gotchas and Common Mistakes

**1. Forgetting `index: enable-bm25`.** The `bm25(field)` rank feature returns 0 without it.

```sd
# Wrong -- bm25(title) returns 0
field title type string { indexing: summary | index }
# Correct
field title type string { indexing: summary | index   index: enable-bm25 }
```

**2. `match: exact` without `index`.** The `match` directive controls how the *index* processes terms. On attribute-only fields it has no effect. Use `fast-search` + the `=` query prefix for attribute exact matching.

**3. Schema/document name mismatch.** Both names must be identical or deployment fails.

**4. Tensor dimension mismatch.** Query and document tensors must share exact dimension names and sizes (`x[384]` in both, not `d[384]` vs `x[384]`).

For gotchas 5–12 (memory/paging, type changes, reserved names, `raw` storage, weightedset type limits, references + `import field`, `fast-access`/`fast-search` restrictions), load `docs/gotchas-extended.md`.

## Validation Checks

Apply only the checks that match what you actually changed:

- **Wrote a new schema?** Confirm outer `schema` and inner `document` names match.
- **Added a field used in `bm25()`?** Confirm `index: enable-bm25` is set on that field.
- **Added or changed a tensor / a rank-profile `inputs` block?** Confirm document-side and query-side dimension names and sizes agree (`x[384]` on both, not `d[384]` vs `x[384]`).
- **Added a rank profile, fieldset, or summary that references field names?** Confirm those fields exist in the document.

For incremental edits to an existing schema, do **not** re-validate sections you did not touch. Trust the existing file. Re-reading or restating unchanged content adds turns without changing the output.
