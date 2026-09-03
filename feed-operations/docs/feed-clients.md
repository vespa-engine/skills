# Vespa Feed Clients Reference

Comparison of Vespa feed clients and performance tuning guidance.

## Client Hierarchy Overview

Choose the right client based on your requirements:

| Client | Best For | Throughput | Complexity |
|---|---|---|---|
| `vespa feed` CLI | Most use cases, scripts, CI/CD | High | Low |
| vespa-feed-client (Java) | Maximum throughput, custom pipelines | Highest | Medium |
| HTTP /document/v1 API | Programmatic access, any language | Moderate | Low |

**General recommendation:** Start with `vespa feed` CLI. Move to the Java client only if you need tighter integration or higher throughput. Use the REST API for single-document operations or when building custom clients in non-Java languages.

---

## vespa feed CLI

The `vespa feed` command is the recommended tool for feeding documents to Vespa. It uses the same optimized HTTP/2 client as the Java library under the hood.

### Basic Usage

```bash
# Feed a single file
vespa feed file.jsonl

# Feed multiple files
vespa feed *.jsonl

# Feed from stdin
cat documents.jsonl | vespa feed -

# Feed a gzipped file (automatic decompression)
vespa feed documents.jsonl.gz

# Feed with explicit target
vespa feed file.jsonl -t https://vespa-endpoint:443
```

### Key Options

```
--connections N         Number of HTTP/2 connections (default 8)
--max-streams-per-connection N
                        Max concurrent streams per connection (default 128)
--timeout DURATION      Feed operation timeout, e.g. "60s", "5m" (default 0, unlimited)
--route STRING          Vespa route, e.g. "default" or "indexing"
--trace N               Trace level (0-9) for debugging feed pipeline
--verbose               Print verbose output including successful operations
--speedtest             Run a speed test to estimate max throughput
--stdin-delay DURATION  Max delay waiting for more data on stdin before flushing
```

### Stdin Piping

Useful for generating documents on-the-fly and piping directly:

```bash
# Generate and feed
python generate_docs.py | vespa feed -

# Transform and feed
jq -c '.[] | {put: ("id:ns:doc::" + .id), fields: .}' data.json | vespa feed -

# Feed from a remote source
curl -s https://example.com/data.jsonl | vespa feed -
```

### Progress and Statistics

`vespa feed` prints a progress summary upon completion:

```
{
  "feeder.seconds": 10.123,
  "feeder.ok.count": 50000,
  "feeder.ok.rate": 4939.21,
  "feeder.error.count": 0,
  "feeder.inflight.count": 0,
  "http.request.count": 50000,
  "http.request.bytes": 104857600,
  "http.response.count": 50000,
  "http.response.bytes": 5242880,
  "http.response.latency.millis.min": 2,
  "http.response.latency.millis.avg": 12,
  "http.response.latency.millis.max": 134,
  "http.response.code.counts": { "200": 50000 }
}
```

---

## vespa-feed-client Java Library

For maximum throughput and tight application integration.

### Maven Dependency

```xml
<dependency>
  <groupId>com.yahoo.vespa</groupId>
  <artifactId>vespa-feed-client</artifactId>
  <version>[VESPA_VERSION]</version>
</dependency>
```

Replace `[VESPA_VERSION]` with your Vespa version, e.g. `8.350.30`.

### Basic Usage

```java
import ai.vespa.feed.client.FeedClient;
import ai.vespa.feed.client.FeedClientBuilder;
import ai.vespa.feed.client.DocumentId;
import ai.vespa.feed.client.OperationParameters;
import ai.vespa.feed.client.Result;

import java.net.URI;
import java.util.concurrent.CompletableFuture;

try (FeedClient client = FeedClientBuilder.create(
        URI.create("https://vespa-endpoint:443"))
    .build()) {

    DocumentId docId = DocumentId.of("mynamespace", "music", "doc-1");
    String json = "{\"fields\": {\"title\": \"Example Song\", \"year\": 2024}}";

    CompletableFuture<Result> promise = client.put(docId, json, OperationParameters.empty());

    Result result = promise.get();
    System.out.println(result.type()); // success, conditionNotMet, etc.
}
```

### FeedClientBuilder Configuration

```java
FeedClient client = FeedClientBuilder.create(endpoint)
    .setConnectionsPerEndpoint(16)       // default 8
    .setMaxStreamPerConnection(256)      // default 128
    .setRetryStrategy(retryStrategy)     // custom retry logic
    .setTimeout(Duration.ofSeconds(30))  // per-operation timeout
    .setCertificate(cert, privateKey)    // mTLS authentication
    .setDryrun(false)                    // set true for validation only
    .build();
```

### Async Feeding with CompletableFuture

```java
List<CompletableFuture<Result>> promises = new ArrayList<>();

for (Document doc : documents) {
    DocumentId docId = DocumentId.of("ns", "type", doc.getId());
    String json = doc.toFeedJson();

    CompletableFuture<Result> promise = client.put(docId, json, OperationParameters.empty());

    promise.whenComplete((result, error) -> {
        if (error != null) {
            log.error("Feed error for " + doc.getId(), error);
        } else if (result.type() != Result.Type.success) {
            log.warn("Non-success for {}: {} - {}",
                doc.getId(), result.type(), result.resultMessage());
        }
    });

    promises.add(promise);
}

// Wait for all operations to complete
CompletableFuture.allOf(promises.toArray(new CompletableFuture[0])).join();
```

### Error Handling and Retries

The Java client retries transient errors (HTTP 429, 503) automatically. Customize with:

```java
FeedClientBuilder.create(endpoint)
    .setRetryStrategy(new FeedClient.RetryStrategy() {
        @Override public boolean retry(FeedClient.OperationType type) { return true; }
        @Override public int retries() { return 10; }
    })
    .build();
```

---

## HTTP /document/v1 REST API

Direct HTTP access for single-document operations. Suitable for any programming language.

### Endpoints

| Operation | Method | Path |
|---|---|---|
| Put | POST | `/document/v1/{namespace}/{document-type}/docid/{key}` |
| Update | PUT | `/document/v1/{namespace}/{document-type}/docid/{key}` |
| Remove | DELETE | `/document/v1/{namespace}/{document-type}/docid/{key}` |
| Get | GET | `/document/v1/{namespace}/{document-type}/docid/{key}` |

### URL Formats

Standard document:

```
/document/v1/mynamespace/music/docid/doc-1
```

With group modifier:

```
/document/v1/mynamespace/music/group/user123/doc-1
```

With number modifier:

```
/document/v1/mynamespace/music/number/12345/doc-1
```

### Query Parameters

| Parameter | Description | Example |
|---|---|---|
| `timeout` | Operation timeout | `timeout=10s` |
| `route` | Vespa route | `route=default` |
| `condition` | Test-and-set condition (URL-encoded) | `condition=music.year%3D%3D2024` |
| `create` | Auto-create on update (upsert) | `create=true` |
| `fieldSet` | Fields to return on GET | `fieldSet=music:title,year` |
| `tracelevel` | Trace level (1-9) | `tracelevel=5` |

### Request and Response Examples

**Put:**

```bash
curl -X POST \
  "https://vespa-host:8080/document/v1/mynamespace/music/docid/doc-1" \
  -H "Content-Type: application/json" \
  -d '{"fields": {"title": "Example", "year": 2024}}'
```

**Update:**

```bash
curl -X PUT \
  "https://vespa-host:8080/document/v1/mynamespace/music/docid/doc-1?create=true" \
  -H "Content-Type: application/json" \
  -d '{"fields": {"play_count": {"increment": 1}}}'
```

**Remove:**

```bash
curl -X DELETE \
  "https://vespa-host:8080/document/v1/mynamespace/music/docid/doc-1"
```

**Get:**

```bash
curl "https://vespa-host:8080/document/v1/mynamespace/music/docid/doc-1?fieldSet=music:title,year"
```

### Response Format

Successful response:

```json
{
  "pathId": "/document/v1/mynamespace/music/docid/doc-1",
  "id": "id:mynamespace:music::doc-1"
}
```

Get response with fields:

```json
{
  "pathId": "/document/v1/mynamespace/music/docid/doc-1",
  "id": "id:mynamespace:music::doc-1",
  "fields": {
    "title": "Example",
    "year": 2024
  }
}
```

Error response:

```json
{
  "pathId": "/document/v1/mynamespace/music/docid/doc-1",
  "message": "Condition not met"
}
```

---

## Performance Tuning

### Connection Count

The default of 8 connections works well for moderate workloads. For high-throughput scenarios:

```bash
# CLI
vespa feed file.jsonl --connections 32

# Java
FeedClientBuilder.create(endpoint).setConnectionsPerEndpoint(32).build();
```

Rule of thumb: increase connections until throughput plateaus. Going beyond the content node count rarely helps.

### Max Streams per Connection

HTTP/2 multiplexes multiple requests over a single connection via streams. The default is 128.

```bash
vespa feed file.jsonl --max-streams-per-connection 256
```

Higher values increase concurrency but also memory use on both client and server.

### Document Batching Strategies

- **Prefer JSONL with `vespa feed`** over individual HTTP calls for bulk operations.
- **Order documents by bucket** (document ID hash) to improve content node cache locality.
- **Separate put and update operations** into different files if their throughput characteristics differ.
- **Use gzip compression** for large files to reduce network transfer time: `vespa feed data.jsonl.gz`.

### Monitoring

Check feed health via the metrics endpoint:

```bash
curl https://vespa-host:19092/metrics/v2/values
```

Key metrics to monitor:

- `content.proton.documentdb.feeding.rate` -- documents fed per second
- `content.proton.resource_usage.disk` -- disk utilization (should stay below 0.8)
- `content.proton.resource_usage.memory` -- memory utilization (should stay below 0.8)
- `vds.distributor.puts.latency` -- put operation latency

### Common Bottlenecks

| Bottleneck | Symptom | Fix |
|---|---|---|
| Network | Low CPU on both client and server, high latency | Increase connections, enable compression, co-locate client |
| Disk I/O | High disk utilization on content nodes | Use faster disks, increase node count, reduce document size |
| Document processing | High CPU on container nodes | Scale container cluster, simplify indexing pipeline |
| Memory | Resource usage warnings, 507 responses | Add content nodes, reduce redundancy temporarily, compact |
| Client-side | Low server load, client CPU or network saturated | Use more client instances, increase parallelism |

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|---|---|---|
| 200 | Success | Operation completed |
| 400 | Bad request | Fix the document JSON or request format |
| 404 | Document not found | Expected for get/update on missing docs |
| 412 | Condition not met | Test-and-set condition failed; read-modify-write or skip |
| 429 | Throttled | Client is sending too fast; back off and retry |
| 503 | Overloaded | Server is temporarily overloaded; retry with backoff |
| 507 | Insufficient storage | Disk or memory is above threshold; add capacity |

### Retry Strategies

**For 429 (throttled):**
The `vespa feed` CLI and Java client handle this automatically. For custom clients, implement exponential backoff starting at 500ms.

**For 503 (overloaded):**
Back off more aggressively than for 429. Start at 1-2 seconds and increase. Check `/metrics/v2` to understand the underlying cause.

**For 412 (condition not met):**
This is not a transient error. The document state did not match the condition. Re-read the document, re-evaluate the condition, and reissue if appropriate. Do not blindly retry.

**General retry pattern for custom clients:**

```python
import time
import requests


def feed_with_retry(url, doc_json, max_retries=5):
    for attempt in range(max_retries):
        resp = requests.post(url, json=doc_json)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 503):
            delay = min(0.5 * (2**attempt), 30)
            time.sleep(delay)
            continue
        resp.raise_for_status()
    raise Exception(f"Failed after {max_retries} retries")
```
