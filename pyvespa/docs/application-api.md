# pyvespa Application & Deployment API Reference

Complete reference for `vespa.application`, `vespa.deployment`, `vespa.querybuilder`, and `vespa.io`.

## Vespa (Connection Class)

```python
from vespa.application import Vespa

app = Vespa(
    url: str,                                           # Endpoint URL
    port: Optional[int] = None,
    cert: Optional[str] = None,                         # Path to TLS client cert
    key: Optional[str] = None,                          # Path to TLS private key
    vespa_cloud_secret_token: Optional[str] = None,     # Token auth (also reads VESPA_CLOUD_SECRET_TOKEN env)
    application_package: Optional[ApplicationPackage] = None,
    additional_headers: Optional[Dict[str, str]] = None,
)
```

Usually you get a `Vespa` instance from deployment, not by constructing directly.

---

## Connection Context Managers

Always use context managers for production code:

```python
# Synchronous
with app.syncio(connections=8, compress="auto") as sess:
    response = sess.query(body={...})
    response = sess.feed_data_point(schema="s", data_id="1", fields={...})

# Asynchronous
async with app.asyncio(connections=1, timeout=30.0) as sess:
    response = await sess.query(body={...})

# Reusable session (avoids repeated TLS handshakes)
client = app.get_sync_session(connections=8)
try:
    with app.syncio(session=client) as sess:
        # Multiple operations sharing the same session
        ...
finally:
    client.close()
```

---

## Document CRUD

### Feed (Put)

```python
response = sess.feed_data_point(
    schema: str,
    data_id: str,
    fields: Dict,
    namespace: str = None,       # Defaults to schema name
    groupname: str = None,       # For grouped distribution
    **kwargs,                    # Additional /document/v1 params
) -> VespaResponse
```

### Get

```python
response = sess.get_data(
    schema: str,
    data_id: str,
    namespace: str = None,
    groupname: str = None,
    raise_on_not_found: bool = False,
    **kwargs,
) -> VespaResponse
```

### Update

```python
response = sess.update_data(
    schema: str,
    data_id: str,
    fields: Dict,                # Update operations: {"field": {"assign": value}}
    create: bool = False,        # Upsert: create doc if missing
    namespace: str = None,
    groupname: str = None,
    **kwargs,
) -> VespaResponse
```

**Update field format** — the `fields` dict uses Vespa update syntax:

```python
# Assign
fields = {"title": {"assign": "New Title"}}

# Increment
fields = {"count": {"increment": 1}}

# Add to array
fields = {"tags": {"add": ["new_tag"]}}

# Add to weighted set
fields = {"labels": {"add": {"important": 10}}}

# Remove from array
fields = {"tags": {"remove": ["old_tag"]}}

# Multiple operations
fields = {
    "title": {"assign": "Updated"},
    "count": {"increment": 1},
    "tags": {"add": ["new"]},
}
```

### Delete

```python
response = sess.delete_data(
    schema: str,
    data_id: str,
    namespace: str = None,
    groupname: str = None,
    **kwargs,
) -> VespaResponse
```

### Delete All

```python
app.delete_all_docs(
    content_cluster_name: str,
    schema: str,
    namespace: str = None,
    slices: int = 1,
) -> None
```

---

## Bulk Feed

### Synchronous (Thread Pool)

```python
app.feed_iterable(
    iter: Iterable[Dict],               # [{"id": "1", "fields": {...}}, ...]
    schema: Optional[str] = None,
    namespace: Optional[str] = None,
    callback: Optional[Callable] = None, # callback(response, doc_id)
    operation_type: str = "feed",        # "feed" | "update" | "delete"
    max_queue_size: int = 1000,
    max_workers: int = 8,
    max_connections: int = 16,
    compress: Union[str, bool] = "auto",
    **kwargs,
) -> None
```

### Asynchronous (HTTP/2)

```python
app.feed_async_iterable(
    iter: Iterable[Dict],
    schema: Optional[str] = None,
    namespace: Optional[str] = None,
    callback: Optional[Callable] = None,
    operation_type: str = "feed",
    max_queue_size: int = 1000,
    max_workers: int = 64,
    max_connections: int = 1,            # HTTP/2 multiplexes over 1 conn
    **kwargs,
) -> None
```

**When to use which:**
- `feed_async_iterable` — preferred for throughput, uses HTTP/2 multiplexing
- `feed_iterable` — when you need thread-based parallelism or sync context

**Feed data format:**

```python
# For "feed" (put) and "update"
{"id": "doc-1", "fields": {"title": "Hello", "count": 42}}

# For "delete"
{"id": "doc-1"}

# With group
{"id": "doc-1", "groupname": "user-123", "fields": {...}}
```

---

## Querying

### Single Query

```python
response = sess.query(
    body: Optional[Dict] = None,     # Full query body
    groupname: str = None,           # For streaming mode
    streaming: bool = False,         # SSE streaming
    profile: bool = False,           # Add profiling parameters
    **kwargs,                        # Merged into body
) -> VespaQueryResponse
```

**Query body** is a dict with Vespa query API parameters:

```python
body = {
    "yql": "select * from sources * where title contains 'vespa'",
    "ranking": "bm25",
    "hits": 10,
    "offset": 0,
    "timeout": "5s",
    "input.query(q)": [0.1, 0.2, ...],  # Tensor input
    "presentation.summary": "minimal",
}
```

### Batch Queries

```python
responses = app.query_many(
    queries: Iterable[Dict],
    num_connections: int = 1,
    max_concurrent: int = 100,
    adaptive: bool = True,           # Adaptive throttling on 429/503
    **query_kwargs,                  # Default params merged into each query
) -> List[VespaQueryResponse]

# Async version
responses = await app.query_many_async(queries, ...)
```

---

## Visit (Export Documents)

```python
for slice_ in app.visit(
    content_cluster_name: str,
    schema: str,
    namespace: str = None,
    slices: int = 1,                 # Parallel visiting
    selection: str = "true",         # Document selection expression
    wanted_document_count: int = 500,
    slice_id: Optional[int] = None,  # Visit a specific slice
    **kwargs,
):
    for response in slice_:
        for doc in response.documents:
            print(doc["id"], doc["fields"])
```

**Parallel visiting** — set `slices > 1` to split the visit across multiple parallel streams for faster export.

---

## Response Classes

### VespaResponse

```python
response.json  # Full response dict
response.status_code  # HTTP status code
response.url  # Request URL
response.operation_type  # "feed", "update", "delete", "get"
response.is_successful()  # True if status_code == 200
```

### VespaQueryResponse

Extends `VespaResponse` with:

```python
response.hits  # List[Dict] — hit objects from root.children
response.number_documents_retrieved  # int — totalCount
response.number_documents_indexed  # int — coverage documents
response.request_body  # Optional[Dict] — the request sent
```

### VespaVisitResponse

Extends `VespaResponse` with:

```python
response.documents  # List[Dict] — visited documents
response.number_documents_retrieved  # int — docs in this response
response.continuation  # Optional[str] — continuation token
response.path_id  # str — visit path identifier
```

---

## Deployment

### VespaDocker

```python
from vespa.deployment import VespaDocker

vespa_docker = VespaDocker(
    url: str = "http://localhost",
    port: int = 8080,
    container_memory: Union[str, int] = 0,   # 0=unlimited, min 4GB recommended
    container_image: str = "vespaengine/vespa",
    volumes: Optional[List[str]] = None,
    cfgsrv_port: int = 19071,
    debug_port: int = 5005,
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `deploy(app_package, max_wait_deployment=300)` | Deploy and return `Vespa` instance |
| `deploy_from_disk(name, root)` | Deploy from an on-disk application directory |
| `from_container_name_or_id(name)` | Class method — reconnect to existing container |
| `start_services()` | Start Vespa services in the container |
| `stop_services()` | Stop services |
| `restart_services()` | Restart services |

### VespaCloud

```python
from vespa.deployment import VespaCloud

vespa_cloud = VespaCloud(
    tenant: str,
    application: str,
    application_package: Optional[ApplicationPackage] = None,
    key_location: Optional[str] = None,       # API key file path
    key_content: Optional[str] = None,        # API key string
    auth_client_token_id: Optional[str] = None,  # For token-based data plane auth
    application_root: Optional[str] = None,   # On-disk app instead of in-memory
    cluster: Optional[str] = None,
    instance: str = "default",
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `deploy(instance="default", environment="dev")` | Deploy to dev/perf, return `Vespa` |
| `get_application(instance, environment, endpoint_type)` | Connect to existing deployment |
| `deploy_to_prod(instance)` | Submit production deployment |
| `check_production_build_status(build_no)` | Check prod deploy status |
| `wait_for_prod_deployment(build_no, max_wait)` | Wait for prod convergence |
| `get_all_endpoints(instance, environment)` | List all endpoints |
| `get_schemas(instance, environment)` | List deployed schemas |
| `download_app_package_content(instance, environment)` | Download deployed app |

**Authentication:**
- **Control plane**: API key via `key_location` or `key_content`
- **Data plane (mTLS)**: cert auto-generated, or set `cert`/`key` on the `Vespa` instance
- **Data plane (token)**: set `auth_client_token_id` in `VespaCloud` and `VESPA_CLOUD_SECRET_TOKEN` env var

---

## Query Builder DSL

```python
import vespa.querybuilder as qb
```

### QueryField

```python
f = qb.QueryField("title")

f.contains("word")  # title contains "word"
f.contains("word", annotations={...})  # With annotations
f.matches("regex")  # title matches "regex"
f.in_("a", "b", "c")  # title in ("a", "b", "c")
f.in_range(10, 100)  # range(title, 10, 100)
f == "value"  # title = "value"
f != "value"  # title != "value"
f > 10  # title > 10
f >= 10  # title >= 10
f < 10  # title < 10
f <= 10  # title <= 10
f.annotate({"weight": 200})  # Field annotation
```

### Condition Combinators

```python
cond1 & cond2  # AND
cond1 | cond2  # OR
~cond  # NOT
qb.all(c1, c2, c3)  # AND multiple
qb.any(c1, c2, c3)  # OR multiple
```

### Query Construction

```python
q = qb.select("*").from_("schema")
q = qb.select(["title", "body"]).from_("s1", "s2")
q = q.where(condition)
q = q.order_by("field", ascending=True)
q = q.set_limit(10)
q = q.set_offset(20)
q = q.set_timeout(500)  # ms
q = q.param("ranking", "hybrid")  # Add query parameter
q = q.groupby(grouping_expr)

yql_string = str(q)  # Build YQL
```

### Special Operators

```python
qb.nearestNeighbor("embedding", "q", annotations={"targetHits": 100})
qb.weakAnd(c1, c2, annotations={"targetHits": 200})
qb.wand("field", {"term1": 1, "term2": 2})
qb.dotProduct("field", {"term1": 1, "term2": 2})
qb.weightedSet("field", {"term1": 1, "term2": 2})
qb.rank(recall_cond, ranking_cond1, ranking_cond2)
qb.phrase("new", "york")
qb.nonEmpty(condition)
qb.userQuery(value="")
qb.userInput("@param")
```

### Grouping

```python
from vespa.querybuilder import Grouping as G

G.all(...)              G.each(...)
G.group("field")        G.output(...)
G.count()               G.sum("field")
G.avg("field")          G.min("field")
G.max("field")          G.stddev("field")
G.xor("field")          G.summary("class")
G.order(...)            G.max(N)
G.precision(N)
```

Example:

```python
grouping = G.all(G.group("category"), G.max(10), G.each(G.output(G.count(), G.avg("price"))))
q = qb.select("*").from_("products").where(qb.userQuery()).groupby(str(grouping)).param("query", "laptop")
```

---

## Utility Methods

```python
app.wait_for_application_up(max_wait=300)  # Block until healthy
app.get_application_status()  # Returns requests.Response or None
```
