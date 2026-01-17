# Prompt Versioning Reference

> MLflow-backed prompt management for versioning, snapshots, editing, and forking.

```
pip install agno[mlflow]
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PromptManager                                   │
│  High-level API for all operations                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                             MLflowPromptStore                                │
│  Storage backend using MLflow experiments/runs/artifacts                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  PromptVersion │ PromptTemplate │ PromptMetadata │ PromptDiff │ PromptLineage│
│  Data models (Pydantic)                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**MLflow Mapping:**
| Concept | MLflow Entity |
|---------|---------------|
| Prompt name | Experiment |
| Version | Run |
| Content | Artifact (JSON) |
| Metadata | Run parameters |
| Tags | Run tags |

---

## Quick Start

```python
from agno.prompt_versioning import PromptManager

manager = PromptManager(tracking_uri="mlruns")

# Create → Edit → Snapshot → Fork
prompt = manager.create("greeting", "Hello, {{name}}!")
prompt = manager.edit(prompt.id, content="Hi, {{name}}!")
snap = manager.snapshot(prompt.id, "prod-v1")
fork = manager.fork(prompt.id, "greeting_v2")

# Render
output = manager.render(prompt_name="greeting", name="Alice")
```

---

## Data Models

### PromptTemplate

```python
PromptTemplate(content: str)
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Template with `{{variable}}` placeholders |
| `variables` | `Set[str]` | Auto-extracted variable names |

| Method | Returns | Description |
|--------|---------|-------------|
| `render(**kwargs)` | `str` | Substitute all variables (raises if missing) |
| `partial_render(**kwargs)` | `PromptTemplate` | Substitute some, keep others as placeholders |
| `validate_variables(required)` | `bool` | Check if template has required vars |

```python
t = PromptTemplate(content="Hello, {{name}}! Welcome to {{app}}.")
t.variables                        # {'name', 'app'}
t.render(name="Alice", app="Agno") # "Hello, Alice! Welcome to Agno."
t.partial_render(name="Alice")     # PromptTemplate("Hello, Alice! Welcome to {{app}}.")
```

---

### PromptMetadata

```python
PromptMetadata(
    author: str = None,
    description: str = None,
    tags: List[str] = [],
    model_compatibility: List[str] = [],
    use_case: str = None,
    custom: Dict[str, Any] = {}
)
```

| Method | Description |
|--------|-------------|
| `add_tag(tag)` | Add tag if not present |
| `remove_tag(tag)` | Remove tag if present |

---

### PromptVersion

```python
PromptVersion(
    id: str,                          # Unique identifier
    name: str,                        # Prompt name (alphanumeric, _, -, .)
    version: int = 1,                 # Version number (≥1)
    template: PromptTemplate,         # The prompt content
    status: PromptStatus = DRAFT,     # DRAFT | ACTIVE | ARCHIVED | SNAPSHOT
    metadata: PromptMetadata = {},    # Associated metadata
    parent_id: str = None,            # Previous version (edit chain)
    forked_from: str = None,          # Original prompt (if forked)
    snapshot_name: str = None,        # Name if this is a snapshot
    created_at: datetime,             # Creation timestamp
    updated_at: datetime,             # Last update timestamp
    content_hash: str                 # SHA256[:16] of content
)
```

| Property/Method | Returns | Description |
|-----------------|---------|-------------|
| `content` | `str` | Raw template content |
| `variables` | `Set[str]` | Template variables |
| `render(**kwargs)` | `str` | Render template |
| `is_snapshot()` | `bool` | True if status is SNAPSHOT |
| `is_fork()` | `bool` | True if forked_from is set |
| `get_version_string()` | `str` | `"v1"`, `"v2"`, etc. |
| `get_full_name()` | `str` | `"name:v1"` |

**PromptStatus Enum:**
```
DRAFT    → Work in progress
ACTIVE   → Ready for use
ARCHIVED → Deprecated
SNAPSHOT → Immutable named version
```

---

### PromptDiff

```python
PromptDiff.compute(from_prompt, to_prompt) → PromptDiff
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `from_version` | `str` | Source version ID |
| `to_version` | `str` | Target version ID |
| `content_changed` | `bool` | Whether content differs |
| `old_content` | `str?` | Previous content (if changed) |
| `new_content` | `str?` | New content (if changed) |
| `metadata_changes` | `Dict` | Changed metadata fields |
| `variables_added` | `Set[str]` | New variables |
| `variables_removed` | `Set[str]` | Removed variables |

---

### PromptLineage

```python
PromptLineage(
    root_id: str,                    # Original prompt ID
    name: str,                       # Prompt name
    versions: List[PromptVersion],   # All versions
    forks: List[str],                # IDs of forks
    snapshots: Dict[str, str]        # {snapshot_name: version_id}
)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get_version(n)` | `PromptVersion?` | Get specific version |
| `get_latest()` | `PromptVersion?` | Get highest version |
| `get_snapshot(name)` | `PromptVersion?` | Get by snapshot name |
| `get_history()` | `List[Dict]` | Summary of all versions |

---

## PromptManager API

### Constructor

```python
PromptManager(
    tracking_uri: str = "mlruns",           # MLflow tracking URI
    experiment_prefix: str = "prompt_versioning"  # Experiment name prefix
)
```

**Tracking URI Examples:**
```python
PromptManager("mlruns")                    # Local directory
PromptManager("sqlite:///prompts.db")      # SQLite database
PromptManager("http://mlflow-server:5000") # Remote server
```

---

### CRUD Operations

#### create

```python
manager.create(
    name: str,                              # Required: unique name
    content: str,                           # Required: template content
    description: str = None,
    author: str = None,
    tags: List[str] = None,
    model_compatibility: List[str] = None,
    use_case: str = None,
    custom_metadata: Dict[str, Any] = None
) → PromptVersion
```

```python
prompt = manager.create(
    name="summarizer",
    content="Summarize this text:\n{{text}}\n\nBe {{style}}.",
    description="Text summarization prompt",
    author="team-ml",
    tags=["summarization", "nlp"],
    model_compatibility=["gpt-4", "claude-3"]
)
```

#### edit

```python
manager.edit(
    prompt_id: str,                         # Required: ID to edit
    content: str = None,                    # New content (keeps existing if None)
    description: str = None,
    author: str = None,
    tags: List[str] = None,                 # Replaces existing tags
    model_compatibility: List[str] = None,
    use_case: str = None,
    custom_metadata: Dict[str, Any] = None, # Merged with existing
    status: PromptStatus = None
) → PromptVersion  # New version with incremented version number
```

```python
v2 = manager.edit(prompt.id, content="Please summarize:\n{{text}}")
# v2.version == 2, v2.parent_id == prompt.id
```

#### get / get_by_name / get_snapshot

```python
manager.get(prompt_id: str) → PromptVersion?
manager.get_by_name(name: str, version: int = None) → PromptVersion?  # latest if no version
manager.get_snapshot(name: str, snapshot_name: str) → PromptVersion?
```

#### delete

```python
manager.delete(prompt_id: str) → bool  # True if deleted
```

---

### Versioning Operations

#### snapshot

Create an immutable named version (e.g., for production releases).

```python
manager.snapshot(
    prompt_id: str,                         # Required: version to snapshot
    snapshot_name: str,                     # Required: unique name within prompt
    description: str = None
) → PromptVersion  # status=SNAPSHOT, snapshot_name set
```

```python
snap = manager.snapshot(prompt.id, "prod-v1", "Approved for production")
# snap.is_snapshot() == True
# snap.snapshot_name == "prod-v1"
```

#### fork

Create a new independent prompt from an existing one.

```python
manager.fork(
    prompt_id: str,                         # Required: source prompt
    new_name: str,                          # Required: new prompt name
    description: str = None,
    author: str = None
) → PromptVersion  # version=1, forked_from set, adds "forked" tag
```

```python
fork = manager.fork(prompt.id, "summarizer_concise")
# fork.version == 1
# fork.forked_from == prompt.id
# fork.is_fork() == True
```

#### activate / archive

```python
manager.activate(prompt_id: str) → PromptVersion  # Sets status=ACTIVE
manager.archive(prompt_id: str) → PromptVersion   # Sets status=ARCHIVED
```

---

### Query Operations

#### list_prompts / list_versions / list_snapshots

```python
manager.list_prompts() → List[str]                           # All prompt names
manager.list_versions(name: str) → List[PromptVersion]       # All versions (sorted)
manager.list_snapshots(name: str) → List[(str, PromptVersion)]  # (snapshot_name, version)
```

#### search

```python
manager.search(
    name_pattern: str = None,               # Prefix match on name
    tags: List[str] = None,                 # Must have all these tags
    status: PromptStatus = None,
    author: str = None,
    include_forks: bool = True
) → List[PromptVersion]
```

```python
results = manager.search(tags=["nlp"], status=PromptStatus.ACTIVE)
```

#### get_lineage

```python
manager.get_lineage(name: str) → PromptLineage
```

#### compare

```python
manager.compare(prompt_id_1: str, prompt_id_2: str) → PromptDiff
```

---

### Rendering

```python
manager.render(
    prompt_id: str = None,                  # Direct ID lookup
    prompt_name: str = None,                # Name lookup
    version: int = None,                    # Specific version (with prompt_name)
    snapshot_name: str = None,              # Snapshot (with prompt_name)
    **variables                             # Template variables
) → str
```

**Lookup priority:** `prompt_id` > `prompt_name + snapshot_name` > `prompt_name + version` > `prompt_name` (latest)

```python
# By name (latest version)
manager.render(prompt_name="greeting", name="Alice")

# By specific version
manager.render(prompt_name="greeting", version=2, name="Alice")

# By snapshot
manager.render(prompt_name="greeting", snapshot_name="prod-v1", name="Alice")

# By ID
manager.render(prompt_id="prompt_abc123", name="Alice")
```

---

### Export

```python
manager.export_lineage(name: str) → Dict[str, Any]
```

Returns:
```python
{
    "name": "greeting",
    "root_id": "prompt_abc123",
    "versions": [
        {
            "id": "...",
            "version": 1,
            "content": "...",
            "variables": ["name"],
            "status": "draft",
            "metadata": {...},
            "parent_id": null,
            "forked_from": null,
            "snapshot_name": null,
            "created_at": "2024-01-15T10:30:00",
            "content_hash": "abc123..."
        },
        ...
    ],
    "snapshots": {"prod-v1": "prompt_xyz789"},
    "forks": ["prompt_fork1", "prompt_fork2"]
}
```

---

## CLI Reference

```
agno-prompts [OPTIONS] COMMAND [ARGS]
```

**Global Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `-u, --tracking-uri` | `mlruns` | MLflow tracking URI |

### Commands

| Command | Description |
|---------|-------------|
| `create` | Create a new prompt |
| `edit` | Edit prompt (creates new version) |
| `snapshot` | Create named snapshot |
| `fork` | Fork to new prompt |
| `list` | List all prompts |
| `versions` | List versions of a prompt |
| `show` | Show prompt details |
| `render` | Render with variables |
| `compare` | Compare two versions |
| `export` | Export lineage to JSON |
| `delete` | Delete a version |

---

### create

```bash
agno-prompts create NAME CONTENT [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-d, --description` | Description |
| `-a, --author` | Author name |
| `-t, --tags` | Comma-separated tags |

```bash
agno-prompts create summarizer "Summarize: {{text}}" \
    -d "Text summarization" \
    -a "team-ml" \
    -t "nlp,summarization"
```

### edit

```bash
agno-prompts edit NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-c, --content` | New content |
| `-d, --description` | New description |
| `-a, --author` | New author |
| `-t, --tags` | New tags (replaces) |
| `-v, --version` | Version to edit (latest if omitted) |

```bash
agno-prompts edit summarizer -c "Please summarize:\n{{text}}"
```

### snapshot

```bash
agno-prompts snapshot NAME SNAPSHOT_NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-d, --description` | Snapshot description |
| `-v, --version` | Version to snapshot |

```bash
agno-prompts snapshot summarizer prod-v1 -d "Production ready"
```

### fork

```bash
agno-prompts fork SOURCE_NAME NEW_NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-d, --description` | Fork description |
| `-a, --author` | Fork author |
| `-v, --version` | Version to fork |

```bash
agno-prompts fork summarizer summarizer_concise -d "Shorter summaries"
```

### list

```bash
agno-prompts list
```

Output:
```
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┓
┃ Name       ┃ Latest Version ┃ Status ┃ Snapshots ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━┩
│ summarizer │ v3             │ active │ prod-v1   │
│ greeting   │ v2             │ draft  │ -         │
└────────────┴────────────────┴────────┴───────────┘
```

### versions

```bash
agno-prompts versions NAME
```

### show

```bash
agno-prompts show NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-v, --version` | Specific version |
| `-s, --snapshot` | Snapshot name |

### render

```bash
agno-prompts render NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-V, --var` | Variable (key=value), repeatable |
| `-v, --version` | Specific version |
| `-s, --snapshot` | Snapshot name |

```bash
agno-prompts render greeting -V name=Alice -V app=Agno -s prod-v1
```

### compare

```bash
agno-prompts compare NAME V1 V2
```

```bash
agno-prompts compare summarizer 1 3
```

### export

```bash
agno-prompts export NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-o, --output` | Output file (stdout if omitted) |

### delete

```bash
agno-prompts delete PROMPT_ID [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-f, --force` | Skip confirmation |

---

## Version Lifecycle

```
                    ┌─────────────┐
                    │   create()  │
                    └──────┬──────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────┐
    │                     DRAFT                         │
    │  Working version, can be edited                  │
    └───────────┬───────────────────────┬──────────────┘
                │                       │
         edit() │                       │ activate()
                │                       │
                ▼                       ▼
    ┌───────────────────┐   ┌───────────────────────────┐
    │   DRAFT (new v)   │   │         ACTIVE            │
    │   parent_id set   │   │   Ready for production    │
    └───────────────────┘   └─────────────┬─────────────┘
                                          │
                                          │ archive()
                                          ▼
                            ┌───────────────────────────┐
                            │        ARCHIVED           │
                            │      Deprecated           │
                            └───────────────────────────┘

    ─────────────────────────────────────────────────────
                        snapshot()
    ─────────────────────────────────────────────────────

    Any version ───────────────► SNAPSHOT
                                 (immutable, named)

    ─────────────────────────────────────────────────────
                          fork()
    ─────────────────────────────────────────────────────

    Any version ───────────────► New prompt (DRAFT, v1)
                                 forked_from set
```

---

## Lineage Tracking

```
Original                          Fork
────────                          ────

greeting v1 ◄─────────────────────┐
    │                             │
    │ edit()                      │ fork()
    ▼                             │
greeting v2 ──────────────────────┴──► greeting_formal v1
    │                                        │
    │ snapshot("prod-v1")                    │ edit()
    ▼                                        ▼
greeting v3 [SNAPSHOT]              greeting_formal v2
    │
    │ edit()
    ▼
greeting v4
```

**Relationships:**
- `parent_id`: Points to previous version in edit chain
- `forked_from`: Points to source prompt (only for forks)

---

## Template Syntax

Variables use `{{name}}` syntax:

```
Hello, {{name}}!

You are a {{role}} assistant.
Please {{action}} the following {{content_type}}:

{{content}}

Respond in {{language}} with a {{tone}} tone.
```

**Rules:**
- Variable names: `[a-zA-Z_][a-zA-Z0-9_]*`
- Missing variables in `render()` raise `ValueError`
- Use `partial_render()` to fill some variables

---

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `ValueError: Prompt not found` | Invalid ID or name | Check ID/name exists |
| `ValueError: Missing required variables` | Incomplete render | Provide all `{{vars}}` |
| `ValueError: Snapshot already exists` | Duplicate snapshot name | Use unique name |
| `ValueError: Prompt with name exists` | Fork name collision | Choose different name |
| `ImportError: MLflow required` | MLflow not installed | `pip install mlflow` |

---

## Best Practices

1. **Naming**: Use descriptive, hierarchical names: `chat.greeting`, `summarize.article`
2. **Snapshots**: Create before deploying: `prod-v1`, `release-2024-01`
3. **Tags**: Consistent taxonomy: `["domain:finance", "task:summarization"]`
4. **Forking**: Fork for experiments, merge learnings back via new versions
5. **Variables**: Use semantic names: `{{user_name}}` not `{{x}}`

---

## Storage Structure

```
mlruns/
└── prompt_versioning/
    └── greeting/                    # Experiment per prompt
        ├── run_abc123/              # Run per version
        │   ├── params/
        │   │   ├── prompt_id
        │   │   ├── prompt_name
        │   │   ├── status
        │   │   └── ...
        │   ├── metrics/
        │   │   ├── version
        │   │   ├── variable_count
        │   │   └── content_length
        │   ├── tags/
        │   │   ├── prompt_id
        │   │   ├── version
        │   │   ├── snapshot (if applicable)
        │   │   └── tag_* (custom tags)
        │   └── artifacts/
        │       └── prompts/
        │           └── prompt.json  # Full prompt data
        └── run_def456/
            └── ...
```
