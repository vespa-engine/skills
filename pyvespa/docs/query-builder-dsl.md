# pyvespa Query Builder DSL

Load this reference when building YQL queries programmatically with `vespa.querybuilder` instead of hand-constructing YQL strings.

```python
import vespa.querybuilder as qb

title = qb.QueryField("title")
body = qb.QueryField("body")

# Text search
q = qb.select("*").from_("myschema").where(title.contains("vespa"))

# Boolean conditions
q = qb.select("*").from_("myschema").where(qb.all(title.contains("vespa"), body.contains("search")))

# Nearest neighbor
q = qb.select("*").from_("myschema").where(qb.nearestNeighbor("embedding", "q", annotations={"targetHits": 100}))

# Hybrid: text + vector with rank()
q = (
    qb.select("*")
    .from_("myschema")
    .where(
        qb.rank(
            qb.any(title.contains("vespa"), qb.nearestNeighbor("embedding", "q", annotations={"targetHits": 100})),
            title.contains("vespa"),
        )
    )
)

# weakAnd
q = (
    qb.select("*")
    .from_("myschema")
    .where(qb.weakAnd(title.contains("big"), title.contains("data"), annotations={"targetHits": 200}))
)

# Pagination and ordering
q = q.set_limit(10).set_offset(20).order_by("price", ascending=True)

# Add query parameters
q = q.param("ranking", "hybrid").param("input.query(q)", [0.1] * 384)

# Build YQL string
yql = str(q)
```

## Grouping

```python
from vespa.querybuilder import Grouping as G

grouping = G.all(G.group("category"), G.each(G.output(G.count(), G.avg("price"))))
q = qb.select("*").from_("myschema").where(title.contains("vespa")).groupby(str(grouping))
```

## Batch Queries

```python
queries = [
    {"yql": "select * from sources * where title contains 'vespa'", "hits": 5},
    {"yql": "select * from sources * where title contains 'search'", "hits": 5},
]
responses = app.query_many(queries, num_connections=4, max_concurrent=100)
```

## Visit (Export All Documents)

```python
for slice_ in app.visit(schema="myschema", content_cluster_name="content", slices=4):
    for response in slice_:
        for doc in response.documents:
            print(doc["id"], doc["fields"])
```
