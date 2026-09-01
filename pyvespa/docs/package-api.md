# pyvespa Configuration API Reference

Complete reference for `vespa.package` — the classes used to define Vespa application packages programmatically.

## ApplicationPackage

```python
ApplicationPackage(
    name: str,                                          # Lowercase [a-z0-9], letter-start, max 20 chars
    schema: Optional[List[Schema]] = None,
    query_profile: Optional[QueryProfile] = None,
    query_profile_type: Optional[QueryProfileType] = None,
    stateless_model_evaluation: bool = False,
    create_schema_by_default: bool = True,
    create_query_profile_by_default: bool = True,
    configurations: Optional[List[ApplicationConfiguration]] = None,
    validations: Optional[List[Validation]] = None,
    components: Optional[List[Component]] = None,
    auth_clients: Optional[List[AuthClient]] = None,
    clusters: Optional[List[Cluster]] = None,
    deployment_config: Optional[DeploymentConfiguration] = None,
    services_config: Optional[ServicesConfiguration] = None,
)
```

**Properties and methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `.schema` | `Schema` | The single schema (asserts exactly one) |
| `.schemas` | `List[Schema]` | All schemas |
| `.get_schema(name)` | `Schema` | Get schema by name |
| `.add_schema(*schemas)` | `None` | Add one or more schemas |
| `.add_query_profile(item)` | `None` | Add query profile field(s) |
| `.get_model(model_id)` | `OnnxModel` | Retrieve ONNX model by ID |
| `.to_files(root)` | `None` | Write to directory tree on disk |
| `.to_zipfile(path)` | `None` | Write deployable zip to file |
| `.to_zip()` | `BytesIO` | Serialize to deployable zip in memory |
| `.schema_to_text` | `str` | Render schema as Vespa SDL text |

---

## Schema

```python
Schema(
    name: str,
    document: Document,
    fieldsets: Optional[List[FieldSet]] = None,
    rank_profiles: Optional[List[RankProfile]] = None,
    models: Optional[List[OnnxModel]] = None,
    global_document: bool = False,
    imported_fields: Optional[List[ImportedField]] = None,
    document_summaries: Optional[List[DocumentSummary]] = None,
    mode: Optional[str] = "index",           # "index" | "streaming" | "store-only"
    inherits: Optional[str] = None,
    stemming: Optional[str] = None,
)
```

**Methods:** `add_fields(*fields)`, `add_field_set(fs)`, `add_rank_profile(rp)`, `add_model(model)`, `add_imported_field(f)`, `add_document_summary(ds)`.

**`mode` options:**
- `"index"` — default, full indexing and search
- `"streaming"` — per-group streaming search, no index maintenance cost
- `"store-only"` — raw storage, GET by ID only

---

## Document

```python
Document(
    fields: Optional[List[Field]] = None,
    inherits: Optional[str] = None,
    structs: Optional[List[Struct]] = None,
)
```

**Methods:** `add_fields(*fields)`, `add_structs(*structs)`.

---

## Field

```python
Field(
    name: str,
    type: str,
    indexing: Optional[Union[List[str], Tuple[str,...], str]] = None,
    index: Optional[Union[str, Dict, List[Union[str, Dict]]]] = None,
    attribute: Optional[List[str]] = None,
    ann: Optional[HNSW] = None,
    match: Optional[List[Union[str, Tuple[str, str]]]] = None,
    weight: Optional[int] = None,
    bolding: Optional[Literal[True]] = None,
    summary: Optional[Summary] = None,
    is_document_field: Optional[bool] = True,
    stemming: Optional[str] = None,
    rank: Optional[str] = None,
    query_command: Optional[List[str]] = None,
    struct_fields: Optional[List[StructField]] = None,
    alias: Optional[List[str]] = None,
)
```

### Indexing Directive Formats

| Python | Rendered .sd |
|--------|-------------|
| `["index", "summary"]` | `indexing: index \| summary` |
| `["attribute", "summary"]` | `indexing: attribute \| summary` |
| `("input title \| embed e5 \| index \| attribute",)` | Multiline `indexing { ... }` block |
| `"summary"` | `indexing: summary` |

### Index Parameter Formats

| Python | Rendered .sd |
|--------|-------------|
| `"enable-bm25"` | `index: enable-bm25` |
| `{"arity": 2}` | `index { arity: 2 }` |
| `["enable-bm25", {"arity": 2}]` | Both settings |

### Type Strings

| Type | String |
|------|--------|
| String | `"string"` |
| Integer (32-bit) | `"int"` |
| Long (64-bit) | `"long"` |
| Float (32-bit) | `"float"` |
| Double (64-bit) | `"double"` |
| Boolean | `"bool"` |
| Byte | `"byte"` |
| Position | `"position"` |
| URI | `"uri"` |
| Predicate | `"predicate"` |
| Raw bytes | `"raw"` |
| Reference | `"reference<parent_schema>"` |
| Indexed tensor | `"tensor<float>(x[384])"` |
| Mapped tensor | `"tensor<float>(label{})"` |
| Mixed tensor | `"tensor<float>(label{},x[128])"` |
| Array | `"array<string>"` |
| Weighted set | `"weightedset<string>"` |
| Map | `"map<string,string>"` |

Tensor value types: `float` (default), `double`, `int8`, `bfloat16`.

---

## HNSW

```python
HNSW(
    distance_metric: str = "euclidean",
    max_links_per_node: int = 16,
    neighbors_to_explore_at_insert: int = 200,
)
```

**Distance metrics:** `euclidean`, `angular`, `dotproduct`, `prenormalized-angular`, `hamming`, `geodegrees`.

- Use `angular` for cosine similarity (auto-normalizes)
- Use `prenormalized-angular` if vectors are already unit-normalized
- Use `dotproduct` for maximum inner product search

---

## FieldSet

```python
FieldSet(name: str, fields: List[str])
```

Example: `FieldSet(name="default", fields=["title", "body"])` — allows querying both fields with `userQuery()`.

---

## RankProfile

```python
RankProfile(
    name: str,
    first_phase: Optional[Union[str, FirstPhaseRanking]] = None,
    second_phase: Optional[SecondPhaseRanking] = None,
    global_phase: Optional[GlobalPhaseRanking] = None,
    inherits: Optional[str] = None,
    inputs: Optional[List[Union[Tuple[str,str], Tuple[str,str,str]]]] = None,
    functions: Optional[List[Function]] = None,
    constants: Optional[Dict] = None,
    summary_features: Optional[List] = None,
    match_features: Optional[List] = None,
    match_phase: Optional[MatchPhaseRanking] = None,
    num_threads_per_search: Optional[int] = None,
    diversity: Optional[Diversity] = None,
    weight: Optional[List[Tuple[str, int]]] = None,
    rank_type: Optional[List[Tuple[str, str]]] = None,
    rank_properties: Optional[List[Tuple[str, str]]] = None,
    mutate: Optional[Mutate] = None,
)
```

### Inputs Format

```python
# (query_name, tensor_type)
inputs = [("query(q)", "tensor<float>(x[384])")]

# (query_name, tensor_type, default_value)
inputs = [("query(threshold)", "double", "0.5")]
```

### Ranking Phase Classes

```python
FirstPhaseRanking(expression: str, keep_rank_count: int = None, rank_score_drop_limit: float = None)
SecondPhaseRanking(expression: str, rerank_count: int = None, rank_score_drop_limit: float = None)
GlobalPhaseRanking(expression: str, rerank_count: int = None)
MatchPhaseRanking(attribute: str, order: str, max_hits: int)  # order: "ascending"|"descending"
```

### Function

```python
Function(name: str, expression: str, args: Optional[List[str]] = None)
```

### Diversity

```python
Diversity(attribute: str, min_groups: int)
```

---

## Struct and StructField

```python
Struct(name: str, fields: Optional[List[Field]] = None)

StructField(
    name: str,
    indexing=None,
    attribute=None,
    match=None,
    query_command=None,
    summary=None,
    rank=None,
)
```

Example:

```python
address_struct = Struct(
    name="address",
    fields=[
        Field(name="street", type="string"),
        Field(name="city", type="string"),
    ],
)
schema.document.add_structs(address_struct)
schema.add_fields(
    Field(
        name="address",
        type="address",
        struct_fields=[
            StructField(name="city", indexing=["attribute"], attribute=["fast-search"]),
        ],
    ),
)
```

---

## ImportedField

For parent-child document relationships with global documents.

```python
ImportedField(name: str, reference_field: str, field_to_import: str)
```

Example:

```python
# In child schema
Field(name="brand_ref", type="reference<brand>", indexing=["attribute"])
ImportedField(name="brand_name", reference_field="brand_ref", field_to_import="name")
```

---

## Summary and DocumentSummary

```python
Summary(name: str = None, type: str = None, fields: list = None, select_elements_by: str = None)

DocumentSummary(
    name: str,
    inherits: str = None,
    summary_fields: List[Summary] = None,
    from_disk: Literal[True] = None,
    omit_summary_features: Literal[True] = None,
)
```

---

## OnnxModel

```python
OnnxModel(
    model_name: str,
    model_file_path: str,      # Relative to app package root
    inputs: Dict[str, str],     # {onnx_input_name: vespa_source}
    outputs: Dict[str, str],    # {onnx_output_name: vespa_name}
)
```

---

## Component and Parameter

For embedders and custom components in services.xml.

```python
Component(
    id: str,
    cls: str = None,          # Java class name
    bundle: str = None,
    type: str = None,         # e.g. "hugging-face-embedder"
    parameters: List[Parameter] = None,
)

Parameter(
    name: str,
    args: Dict[str, str] = None,    # XML attributes
    children: Union[str, List[Parameter]] = None,  # Text content or nested params
)
```

Example — HuggingFace embedder:

```python
Component(
    id="e5",
    type="hugging-face-embedder",
    parameters=[
        Parameter(
            "transformer-model", args={"url": "https://huggingface.co/intfloat/e5-small-v2/resolve/main/model.onnx"}
        ),
        Parameter(
            "tokenizer-model", args={"url": "https://huggingface.co/intfloat/e5-small-v2/resolve/main/tokenizer.json"}
        ),
    ],
)
```

---

## AuthClient

For Vespa Cloud authentication.

```python
AuthClient(
    id: str,
    permissions: List[str],          # ["read", "write"]
    parameters: List[Parameter] = None,
)
```

---

## Query Profile Types

```python
QueryTypeField(name: str, type: str)
QueryProfileType(fields: List[QueryTypeField] = None)
```

Example:

```python
QueryProfileType(
    fields=[
        QueryTypeField(name="ranking.features.query(q)", type="tensor<float>(x[384])"),
    ]
)
```

---

## DeploymentConfiguration

```python
DeploymentConfiguration(environment: str, regions: List[str])
```

Example: `DeploymentConfiguration(environment="prod", regions=["aws-us-east-1c", "aws-eu-west-1a"])`

---

## Validation

Suppress specific validation warnings during deployment.

```python
from vespa.package import Validation, ValidationID

Validation(id=ValidationID.fieldTypeChange, until="2025-06-01")
```

`ValidationID` values: `indexingChange`, `indexModeChange`, `fieldTypeChange`, `tensorTypeChange`, `resourcesReduction`, `contentTypeRemoval`, `contentClusterRemoval`, `deploymentRemoval`, `globalDocumentChange`, etc.
