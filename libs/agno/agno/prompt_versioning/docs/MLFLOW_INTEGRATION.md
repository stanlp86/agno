# MLflow Integration: Technical Deep Dive

> How Prompt Versioning leverages MLflow's tracking infrastructure for persistent, versioned prompt storage.

---

## Table of Contents

1. [MLflow Overview](#mlflow-overview)
2. [Architectural Mapping](#architectural-mapping)
3. [Core API Usage](#core-api-usage)
4. [Data Flow](#data-flow)
5. [Storage Schema](#storage-schema)
6. [Query Patterns](#query-patterns)
7. [Configuration](#configuration)
8. [Lifecycle Management](#lifecycle-management)
9. [Performance Considerations](#performance-considerations)
10. [Limitations & Workarounds](#limitations--workarounds)

---

## MLflow Overview

### What is MLflow?

MLflow is an open-source platform for managing the ML lifecycle. We leverage its **Tracking** component:

| MLflow Component | Our Usage |
|------------------|-----------|
| **Experiments** | One per prompt name (namespace) |
| **Runs** | One per prompt version |
| **Parameters** | Prompt metadata (author, status, etc.) |
| **Metrics** | Numeric data (version number, content length) |
| **Tags** | Searchable labels |
| **Artifacts** | Full prompt JSON document |

### Why MLflow?

| Benefit | Description |
|---------|-------------|
| **Mature Infrastructure** | Production-tested at scale |
| **Multiple Backends** | Local files, SQLite, PostgreSQL, remote servers |
| **Built-in UI** | `mlflow ui` for visual exploration |
| **Search API** | SQL-like queries across runs |
| **Artifact Storage** | Handles large content efficiently |
| **No Schema Migrations** | Flexible parameter/tag model |

---

## Architectural Mapping

### Conceptual Mapping

```
┌─────────────────────────────────────────────────────────────────┐
│                    PROMPT VERSIONING                             │
├─────────────────────────────────────────────────────────────────┤
│  Prompt Name      │  Version       │  Content      │  Metadata  │
│  "greeting"       │  v1, v2, v3    │  "Hello..."   │  author... │
└─────────────────────────────────────────────────────────────────┘
                              ▼
                         MAPPING
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         MLFLOW                                   │
├─────────────────────────────────────────────────────────────────┤
│  Experiment       │  Run           │  Artifact     │  Params    │
│  "prompt_ver..."  │  run_abc123    │  prompt.json  │  author... │
│  "/greeting"      │                │               │            │
└─────────────────────────────────────────────────────────────────┘
```

### Detailed Entity Mapping

| Prompt Concept | MLflow Entity | Relationship |
|----------------|---------------|--------------|
| Prompt name | Experiment name | 1:1 |
| Prompt version | Run | 1:1 |
| Version number | Metric `version` | Stored as float |
| Status | Tag `status` + Param | Dual storage |
| Content | Artifact `prompt.json` | JSON file |
| Metadata fields | Parameters | Key-value |
| Searchable labels | Tags | Indexed |
| Content hash | Param + Tag | Dual storage |

### Namespace Convention

```
Experiment Name Format:
  {experiment_prefix}/{prompt_name}

Examples:
  prompt_versioning/greeting
  prompt_versioning/customer.onboarding
  prompt_versioning/summarize_v2

Default prefix: "prompt_versioning"
```

---

## Core API Usage

### Initialization

```python
# File: mlflow_backend.py

import mlflow
from mlflow.tracking import MlflowClient

class MLflowPromptStore:
    def __init__(self, tracking_uri: str = "mlruns", ...):
        # Set global tracking URI
        mlflow.set_tracking_uri(tracking_uri)

        # Create client for direct API access
        self.client = MlflowClient(tracking_uri)
```

**MLflow APIs Used:**
| API | Purpose |
|-----|---------|
| `mlflow.set_tracking_uri()` | Configure backend location |
| `MlflowClient()` | Low-level client for queries |

---

### Experiment Management

```python
def _get_or_create_experiment(self, prompt_name: str) -> str:
    exp_name = f"{self.config.experiment_prefix}/{prompt_name}"

    # Try to get existing
    experiment = self.client.get_experiment_by_name(exp_name)

    if experiment is None:
        # Create new experiment
        exp_id = self.client.create_experiment(exp_name)
    else:
        exp_id = experiment.experiment_id

    return exp_id
```

**MLflow APIs Used:**
| API | Purpose |
|-----|---------|
| `client.get_experiment_by_name()` | Lookup by name |
| `client.create_experiment()` | Create new experiment |
| `experiment.experiment_id` | Get internal ID |

---

### Saving Prompt Versions (Runs)

```python
def save(self, prompt: PromptVersion) -> str:
    exp_id = self._get_or_create_experiment(prompt.name)

    with mlflow.start_run(experiment_id=exp_id) as run:
        # === PARAMETERS (metadata) ===
        mlflow.log_param("prompt_id", prompt.id)
        mlflow.log_param("prompt_name", prompt.name)
        mlflow.log_param("status", prompt.status.value)
        mlflow.log_param("content_hash", prompt.content_hash)

        if prompt.parent_id:
            mlflow.log_param("parent_id", prompt.parent_id)
        if prompt.forked_from:
            mlflow.log_param("forked_from", prompt.forked_from)
        if prompt.snapshot_name:
            mlflow.log_param("snapshot_name", prompt.snapshot_name)
        if prompt.metadata.author:
            mlflow.log_param("author", prompt.metadata.author)
        if prompt.metadata.description:
            mlflow.log_param("description", prompt.metadata.description[:250])
        if prompt.metadata.tags:
            mlflow.log_param("tags", ",".join(prompt.metadata.tags))

        # === METRICS (numeric data) ===
        mlflow.log_metric("version", prompt.version)
        mlflow.log_metric("variable_count", len(prompt.variables))
        mlflow.log_metric("content_length", len(prompt.content))

        # === TAGS (searchable) ===
        mlflow.set_tag("prompt_id", prompt.id)
        mlflow.set_tag("prompt_name", prompt.name)
        mlflow.set_tag("version", str(prompt.version))
        mlflow.set_tag("status", prompt.status.value)
        if prompt.snapshot_name:
            mlflow.set_tag("snapshot", prompt.snapshot_name)
        if prompt.forked_from:
            mlflow.set_tag("is_fork", "true")
        for tag in prompt.metadata.tags:
            mlflow.set_tag(f"tag_{tag}", "true")

        # === ARTIFACTS (content) ===
        artifact_data = self._prompt_to_artifact(prompt)
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_file = os.path.join(tmpdir, "prompt.json")
            with open(artifact_file, "w") as f:
                json.dump(artifact_data, f, indent=2)
            mlflow.log_artifact(artifact_file, "prompts")

        return run.info.run_id
```

**MLflow APIs Used:**
| API | Purpose | Notes |
|-----|---------|-------|
| `mlflow.start_run()` | Create new run | Context manager |
| `mlflow.log_param()` | Store metadata | Max 500 chars |
| `mlflow.log_metric()` | Store numeric data | Must be float |
| `mlflow.set_tag()` | Store searchable labels | Indexed |
| `mlflow.log_artifact()` | Store files | Path + destination |
| `run.info.run_id` | Get run identifier | For later retrieval |

---

### Loading Prompt Versions

```python
def load(self, prompt_id: str) -> Optional[PromptVersion]:
    # Search for run with matching prompt_id tag
    runs = self.client.search_runs(
        experiment_ids=self._get_all_experiment_ids(),
        filter_string=f"tags.prompt_id = '{prompt_id}'",
        max_results=1,
    )

    if not runs:
        return None

    return self._load_from_run(runs[0])

def _load_from_run(self, run) -> PromptVersion:
    # Construct artifact path
    artifact_uri = f"{run.info.artifact_uri}/prompts/prompt.json"

    # Handle different URI formats
    if artifact_uri.startswith("file://"):
        artifact_path = artifact_uri[7:]
    elif artifact_uri.startswith("/"):
        artifact_path = artifact_uri
    else:
        # Remote: download artifact
        local_path = self.client.download_artifacts(
            run.info.run_id,
            "prompts/prompt.json",
        )
        artifact_path = local_path

    # Read and parse
    with open(artifact_path, "r") as f:
        data = json.load(f)

    return self._artifact_to_prompt(data)
```

**MLflow APIs Used:**
| API | Purpose | Notes |
|-----|---------|-------|
| `client.search_runs()` | Query runs | SQL-like filter |
| `run.info.artifact_uri` | Get artifact location | URI format |
| `client.download_artifacts()` | Fetch remote artifacts | Returns local path |

---

### Querying and Searching

```python
def load_by_name(self, name: str, version: int = None) -> Optional[PromptVersion]:
    exp_name = self._get_experiment_name(name)
    experiment = self.client.get_experiment_by_name(exp_name)

    if experiment is None:
        return None

    # Build filter
    filter_str = f"tags.version = '{version}'" if version else ""

    runs = self.client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=filter_str,
        order_by=["metrics.version DESC"],  # Latest first
        max_results=1,
    )

    if not runs:
        return None

    return self._load_from_run(runs[0])

def search(self, name_pattern=None, tags=None, status=None, author=None, ...):
    filter_parts = []

    if status:
        filter_parts.append(f"tags.status = '{status.value}'")
    if author:
        filter_parts.append(f"params.author = '{author}'")
    if tags:
        for tag in tags:
            filter_parts.append(f"tags.tag_{tag} = 'true'")

    filter_string = " AND ".join(filter_parts) if filter_parts else ""

    # Get relevant experiments
    if name_pattern:
        experiments = self.client.search_experiments(
            filter_string=f"name LIKE '{self.config.experiment_prefix}/{name_pattern}%'",
        )
        exp_ids = [exp.experiment_id for exp in experiments]
    else:
        exp_ids = self._get_all_experiment_ids()

    runs = self.client.search_runs(
        experiment_ids=exp_ids,
        filter_string=filter_string,
        order_by=["metrics.version DESC"],
    )

    return [self._load_from_run(run) for run in runs]
```

**MLflow Filter Syntax:**
| Pattern | Example | Notes |
|---------|---------|-------|
| Tag equals | `tags.key = 'value'` | Exact match |
| Param equals | `params.key = 'value'` | Exact match |
| Metric compare | `metrics.version > 1` | Numeric ops |
| Name pattern | `name LIKE 'prefix%'` | Experiments only |
| AND/OR | `tags.a = 'x' AND tags.b = 'y'` | Combine |

**MLflow APIs Used:**
| API | Purpose | Notes |
|-----|---------|-------|
| `client.search_runs()` | Query runs | Main search API |
| `client.search_experiments()` | Query experiments | For name patterns |
| `order_by` parameter | Sort results | `metrics.*`, `params.*` |
| `max_results` parameter | Limit results | Pagination |

---

### Deletion

```python
def delete(self, prompt_id: str) -> bool:
    runs = self.client.search_runs(
        experiment_ids=self._get_all_experiment_ids(),
        filter_string=f"tags.prompt_id = '{prompt_id}'",
        max_results=1,
    )

    if not runs:
        return False

    self.client.delete_run(runs[0].info.run_id)
    return True
```

**MLflow APIs Used:**
| API | Purpose | Notes |
|-----|---------|-------|
| `client.delete_run()` | Remove run | Soft delete |

> **Note:** MLflow performs soft delete. Data persists in `deleted` state.

---

## Data Flow

### Save Flow

```
PromptVersion
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                       save(prompt)                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Get/Create Experiment                                        │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ client.get_experiment_by_name("prompt_versioning/name") │ │
│     │         ↓ (if None)                                     │ │
│     │ client.create_experiment("prompt_versioning/name")      │ │
│     └─────────────────────────────────────────────────────────┘ │
│                           │                                      │
│                           ▼                                      │
│  2. Start Run                                                    │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ mlflow.start_run(experiment_id=exp_id)                  │ │
│     └─────────────────────────────────────────────────────────┘ │
│                           │                                      │
│           ┌───────────────┼───────────────┐                      │
│           ▼               ▼               ▼                      │
│  3a. Parameters    3b. Metrics     3c. Tags                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │ log_param   │  │ log_metric  │  │ set_tag     │               │
│  │ prompt_id   │  │ version     │  │ prompt_id   │               │
│  │ status      │  │ var_count   │  │ status      │               │
│  │ author      │  │ length      │  │ snapshot    │               │
│  │ ...         │  │             │  │ tag_*       │               │
│  └─────────────┘  └─────────────┘  └─────────────┘               │
│                           │                                      │
│                           ▼                                      │
│  4. Artifact                                                     │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ Create temp file: prompt.json                           │ │
│     │ Write: {"id": "...", "content": "...", ...}            │ │
│     │ mlflow.log_artifact(file, "prompts")                   │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
                      run_id
```

### Load Flow

```
prompt_id
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                       load(prompt_id)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Search for Run                                               │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ client.search_runs(                                     │ │
│     │     experiment_ids=[...all...],                         │ │
│     │     filter_string="tags.prompt_id = 'prompt_abc123'"    │ │
│     │ )                                                       │ │
│     └─────────────────────────────────────────────────────────┘ │
│                           │                                      │
│                           ▼                                      │
│  2. Get Artifact URI                                             │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ run.info.artifact_uri                                   │ │
│     │ → "file:///path/mlruns/exp/run/artifacts"               │ │
│     │ → "/path/mlruns/exp/run/artifacts"                      │ │
│     │ → "s3://bucket/path"                                    │ │
│     └─────────────────────────────────────────────────────────┘ │
│                           │                                      │
│              ┌────────────┴────────────┐                         │
│              ▼                         ▼                         │
│         Local Path              Remote URI                       │
│     ┌──────────────────┐   ┌──────────────────────┐              │
│     │ Open file        │   │ client.download_     │              │
│     │ directly         │   │ artifacts(run_id,    │              │
│     │                  │   │ "prompts/prompt.json"│              │
│     └────────┬─────────┘   └──────────┬───────────┘              │
│              │                        │                          │
│              └────────────┬───────────┘                          │
│                           ▼                                      │
│  3. Parse Artifact                                               │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ json.load(file) → data dict                             │ │
│     │ _artifact_to_prompt(data) → PromptVersion               │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
                    PromptVersion
```

---

## Storage Schema

### Experiment Structure

```
Experiment: "prompt_versioning/greeting"
├── experiment_id: "123456789"
├── name: "prompt_versioning/greeting"
├── artifact_location: "file:///path/mlruns/123456789"
├── lifecycle_stage: "active"
└── tags: {}
```

### Run Structure

```
Run: "abc123def456"
├── info:
│   ├── run_id: "abc123def456"
│   ├── experiment_id: "123456789"
│   ├── status: "FINISHED"
│   ├── start_time: 1705312200000
│   ├── end_time: 1705312201000
│   └── artifact_uri: "file:///path/mlruns/.../artifacts"
│
├── data:
│   ├── params:
│   │   ├── prompt_id: "prompt_a1b2c3d4e5f6"
│   │   ├── prompt_name: "greeting"
│   │   ├── status: "draft"
│   │   ├── content_hash: "abc123def456"
│   │   ├── author: "ml-team"
│   │   ├── description: "Customer greeting..."
│   │   ├── tags: "greeting,customer,onboarding"
│   │   ├── parent_id: "prompt_previous123"  (optional)
│   │   ├── forked_from: "prompt_original123" (optional)
│   │   └── snapshot_name: "prod-v1"  (optional)
│   │
│   ├── metrics:
│   │   ├── version: 2.0
│   │   ├── variable_count: 3.0
│   │   └── content_length: 156.0
│   │
│   └── tags:
│       ├── prompt_id: "prompt_a1b2c3d4e5f6"
│       ├── prompt_name: "greeting"
│       ├── version: "2"
│       ├── status: "draft"
│       ├── snapshot: "prod-v1"  (optional)
│       ├── is_fork: "true"  (optional)
│       ├── tag_greeting: "true"
│       ├── tag_customer: "true"
│       └── tag_onboarding: "true"
│
└── artifacts:
    └── prompts/
        └── prompt.json
```

### Artifact File Schema

```json
{
  "id": "prompt_a1b2c3d4e5f6",
  "name": "greeting",
  "version": 2,
  "content": "Hello {{customer_name}}, welcome to {{company}}!",
  "variables": ["customer_name", "company"],
  "status": "draft",
  "metadata": {
    "author": "ml-team",
    "description": "Customer greeting for onboarding",
    "tags": ["greeting", "customer", "onboarding"],
    "model_compatibility": ["gpt-4", "claude-3"],
    "use_case": "New customer welcome email",
    "custom": {
      "department": "marketing",
      "approved_by": "jane@company.com"
    }
  },
  "parent_id": "prompt_previous123",
  "forked_from": null,
  "created_at": "2024-01-15T10:30:00.000000",
  "updated_at": "2024-01-15T11:45:00.000000",
  "snapshot_name": null,
  "content_hash": "abc123def456"
}
```

### File System Layout

```
mlruns/
├── 0/                           # Default experiment (unused)
├── 123456789/                   # Experiment: prompt_versioning/greeting
│   ├── meta.yaml                # Experiment metadata
│   ├── abc123def456/            # Run: version 1
│   │   ├── meta.yaml            # Run metadata
│   │   ├── params/
│   │   │   ├── prompt_id
│   │   │   ├── prompt_name
│   │   │   ├── status
│   │   │   └── ...
│   │   ├── metrics/
│   │   │   ├── version
│   │   │   └── ...
│   │   ├── tags/
│   │   │   ├── prompt_id
│   │   │   ├── status
│   │   │   └── ...
│   │   └── artifacts/
│   │       └── prompts/
│   │           └── prompt.json
│   └── xyz789abc012/            # Run: version 2
│       └── ...
├── 987654321/                   # Experiment: prompt_versioning/summarizer
│   └── ...
└── ...
```

---

## Query Patterns

### Pattern 1: Get Latest Version

```python
# Find run with highest version metric
runs = client.search_runs(
    experiment_ids=[exp_id],
    order_by=["metrics.version DESC"],
    max_results=1
)
```

### Pattern 2: Get Specific Version

```python
# Find run with matching version tag
runs = client.search_runs(
    experiment_ids=[exp_id],
    filter_string="tags.version = '3'"
)
```

### Pattern 3: Get Snapshot

```python
# Find run with matching snapshot tag
runs = client.search_runs(
    experiment_ids=[exp_id],
    filter_string="tags.snapshot = 'prod-v1'"
)
```

### Pattern 4: Search by Tags

```python
# Find prompts with specific user-defined tags
runs = client.search_runs(
    experiment_ids=all_exp_ids,
    filter_string="tags.tag_customer = 'true' AND tags.tag_greeting = 'true'"
)
```

### Pattern 5: Search by Status

```python
# Find all active prompts
runs = client.search_runs(
    experiment_ids=all_exp_ids,
    filter_string="tags.status = 'active'"
)
```

### Pattern 6: Search by Author

```python
# Find all prompts by author
runs = client.search_runs(
    experiment_ids=all_exp_ids,
    filter_string="params.author = 'alice'"
)
```

### Pattern 7: Get All Snapshots

```python
# Find runs that have snapshot tag (non-empty)
# Note: MLflow filter for "not empty" is tricky
runs = client.search_runs(
    experiment_ids=[exp_id],
    filter_string="tags.status = 'snapshot'"
)
```

### Pattern 8: Find by Prompt ID

```python
# Direct lookup by prompt ID
runs = client.search_runs(
    experiment_ids=all_exp_ids,
    filter_string="tags.prompt_id = 'prompt_abc123'"
)
```

---

## Configuration

### MLflowConfig

```python
class MLflowConfig(BaseModel):
    tracking_uri: str = "mlruns"
    experiment_prefix: str = "prompt_versioning"
    artifact_path: str = "prompts"
```

### Tracking URI Options

| URI Type | Format | Use Case |
|----------|--------|----------|
| Local directory | `mlruns` or `./path` | Development |
| SQLite | `sqlite:///file.db` | Single-machine prod |
| PostgreSQL | `postgresql://user:pass@host:5432/db` | Production |
| MySQL | `mysql://user:pass@host:3306/db` | Production |
| MLflow Server | `http://host:5000` | Team/Enterprise |
| Databricks | `databricks` | Databricks platform |

### Environment Variables

MLflow respects these environment variables:

| Variable | Description |
|----------|-------------|
| `MLFLOW_TRACKING_URI` | Default tracking URI |
| `MLFLOW_TRACKING_USERNAME` | Auth username |
| `MLFLOW_TRACKING_PASSWORD` | Auth password |
| `MLFLOW_TRACKING_TOKEN` | Auth token |
| `MLFLOW_S3_ENDPOINT_URL` | S3-compatible endpoint |

---

## Lifecycle Management

### Run States

```
┌─────────┐     start_run()     ┌─────────┐
│         │ ──────────────────► │         │
│   N/A   │                     │ RUNNING │
│         │                     │         │
└─────────┘                     └────┬────┘
                                     │
                     ┌───────────────┼───────────────┐
                     ▼               ▼               ▼
               (context exit)   end_run()      (exception)
                     │               │               │
                     ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │ FINISHED │   │ FINISHED │   │ FAILED   │
              └──────────┘   └──────────┘   └──────────┘
```

### Experiment States

```
┌─────────┐   create_experiment()   ┌─────────┐
│         │ ──────────────────────► │         │
│   N/A   │                         │ ACTIVE  │
│         │                         │         │
└─────────┘                         └────┬────┘
                                         │
                           delete_experiment()
                                         │
                                         ▼
                                  ┌──────────┐
                                  │ DELETED  │
                                  │ (hidden) │
                                  └──────────┘
```

### Our Usage Pattern

```python
# We always use context manager for proper cleanup
with mlflow.start_run(experiment_id=exp_id) as run:
    # Log everything
    mlflow.log_param(...)
    mlflow.log_metric(...)
    mlflow.set_tag(...)
    mlflow.log_artifact(...)
    # Context exit → FINISHED

# For deletion, we use soft delete
client.delete_run(run_id)  # Marks as DELETED, not removed
```

---

## Performance Considerations

### Indexing

| Query Type | Indexed? | Performance |
|------------|----------|-------------|
| Tags | Yes | Fast O(log n) |
| Params | Partial | Medium |
| Metrics | Yes | Fast |
| Artifact content | No | Slow (file read) |

### Optimization Strategies

1. **Use Tags for Searchable Fields**
   - `prompt_id`, `status`, `version` are tags (indexed)
   - Search by tags is fast

2. **Use Metrics for Ordering**
   - `version` is a metric (can order by)
   - `order_by=["metrics.version DESC"]` is efficient

3. **Limit Result Sets**
   - Use `max_results` to avoid fetching all
   - Implement pagination for large result sets

4. **Cache Experiment IDs**
   - `_experiment_cache` avoids repeated lookups
   - Experiment name → ID mapping is stable

5. **Batch Operations**
   - Group multiple operations in same session
   - Avoid repeated `set_tracking_uri` calls

### Query Performance

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Get by prompt_id | O(1)* | Tag search, indexed |
| Get latest version | O(log n) | Metric sort + limit 1 |
| List all versions | O(n) | Full experiment scan |
| Search by tags | O(log n) | Tag index |
| Search by params | O(n) | Param scan |
| Load artifact | O(1) | Direct file read |

*Assuming indexed tag search

---

## Limitations & Workarounds

### Limitation 1: Parameter Value Length (500 chars)

**Issue:** MLflow limits param values to 500 characters.

**Our Handling:**
```python
# Truncate description
if prompt.metadata.description:
    mlflow.log_param("description", prompt.metadata.description[:250])
```

**Workaround:** Store full content in artifact, not params.

---

### Limitation 2: No Transactions

**Issue:** No atomic multi-run operations.

**Impact:** Race conditions possible:
- Two processes could get same version number
- Experiment creation has TOCTOU vulnerability

**Mitigation:** Application-level locking or optimistic concurrency.

---

### Limitation 3: Soft Delete Only

**Issue:** `delete_run()` marks as deleted, doesn't remove data.

**Impact:** Storage grows over time.

**Workaround:** Periodic cleanup via MLflow GC or manual deletion.

---

### Limitation 4: Filter Injection Risk

**Issue:** Filter strings are built via string interpolation.

**Risk:**
```python
# Dangerous if user_input is malicious
filter_string=f"tags.name = '{user_input}'"
```

**Mitigation:** Input validation/sanitization required.

---

### Limitation 5: No Native Pagination Tokens

**Issue:** No cursor-based pagination in search API.

**Impact:** Large result sets require offset-based pagination.

**Workaround:** Use `max_results` and track by version/timestamp.

---

### Limitation 6: Filesystem Backend Deprecation

**Warning:** MLflow plans to deprecate filesystem backend (Feb 2026).

**Migration Path:**
```python
# Old (will be deprecated)
PromptManager(tracking_uri="mlruns")

# New (recommended)
PromptManager(tracking_uri="sqlite:///prompts.db")
```

---

## API Reference Summary

### MLflow Functions Used

| Function | Module | Purpose |
|----------|--------|---------|
| `set_tracking_uri()` | `mlflow` | Configure backend |
| `start_run()` | `mlflow` | Create run context |
| `log_param()` | `mlflow` | Store metadata |
| `log_metric()` | `mlflow` | Store numeric data |
| `set_tag()` | `mlflow` | Store searchable labels |
| `log_artifact()` | `mlflow` | Store files |

### MlflowClient Methods Used

| Method | Purpose |
|--------|---------|
| `get_experiment_by_name()` | Lookup experiment |
| `create_experiment()` | Create experiment |
| `search_experiments()` | Query experiments |
| `search_runs()` | Query runs |
| `download_artifacts()` | Fetch remote artifacts |
| `delete_run()` | Soft delete run |

### Run Object Properties Used

| Property | Path | Type |
|----------|------|------|
| Run ID | `run.info.run_id` | `str` |
| Experiment ID | `run.info.experiment_id` | `str` |
| Artifact URI | `run.info.artifact_uri` | `str` |
| Parameters | `run.data.params` | `Dict` |
| Metrics | `run.data.metrics` | `Dict` |
| Tags | `run.data.tags` | `Dict` |

---

## Appendix: Complete MLflow Interaction Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PROMPT VERSIONING                                   │
│                                                                              │
│  PromptManager                                                               │
│       │                                                                      │
│       └──► MLflowPromptStore                                                 │
│                 │                                                            │
│                 ├──► mlflow.set_tracking_uri(uri)                           │
│                 │         └──► Configure backend location                    │
│                 │                                                            │
│                 ├──► MlflowClient(uri)                                       │
│                 │         └──► Create low-level client                       │
│                 │                                                            │
│                 ├──► client.get_experiment_by_name(name)                     │
│                 │         └──► Lookup experiment                             │
│                 │                                                            │
│                 ├──► client.create_experiment(name)                          │
│                 │         └──► Create new experiment                         │
│                 │                                                            │
│                 ├──► client.search_experiments(filter)                       │
│                 │         └──► Query experiments by pattern                  │
│                 │                                                            │
│                 ├──► mlflow.start_run(experiment_id)                         │
│                 │         │                                                  │
│                 │         ├──► mlflow.log_param(key, value)                  │
│                 │         │         └──► Store metadata                      │
│                 │         │                                                  │
│                 │         ├──► mlflow.log_metric(key, value)                 │
│                 │         │         └──► Store numeric data                  │
│                 │         │                                                  │
│                 │         ├──► mlflow.set_tag(key, value)                    │
│                 │         │         └──► Store searchable labels             │
│                 │         │                                                  │
│                 │         └──► mlflow.log_artifact(file, path)               │
│                 │                   └──► Store prompt.json                   │
│                 │                                                            │
│                 ├──► client.search_runs(exp_ids, filter, order_by)           │
│                 │         └──► Query runs (versions)                         │
│                 │                                                            │
│                 ├──► client.download_artifacts(run_id, path)                 │
│                 │         └──► Fetch remote artifact files                   │
│                 │                                                            │
│                 └──► client.delete_run(run_id)                               │
│                           └──► Soft delete run                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```
