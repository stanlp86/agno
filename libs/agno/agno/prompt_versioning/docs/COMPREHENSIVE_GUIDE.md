# Prompt Versioning: Comprehensive Guide

> A production-grade prompt management system with MLflow-backed versioning, snapshots, and lineage tracking.

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Core Concepts](#core-concepts)
4. [Data Models](#data-models)
5. [PromptManager API](#promptmanager-api)
6. [CLI Reference](#cli-reference)
7. [Workflows](#workflows)
8. [Advanced Usage](#advanced-usage)
9. [Error Handling](#error-handling)
10. [Best Practices](#best-practices)

---

## Overview

### What is Prompt Versioning?

Prompt Versioning is a complete prompt lifecycle management system that treats prompts as first-class software artifacts. It provides:

| Capability | Description |
|------------|-------------|
| **Versioning** | Every edit creates a new immutable version with full history |
| **Snapshots** | Named releases for production deployment (e.g., `prod-v1`) |
| **Forking** | Branch prompts for experimentation without affecting originals |
| **Lineage** | Track parent-child relationships across versions and forks |
| **Templates** | Variable substitution with `{{variable}}` syntax |
| **Search** | Query prompts by name, tags, status, author |
| **Diff** | Compare any two versions to see changes |
| **Export** | Full JSON export for backup and migration |

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         User Interface                            │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐  │
│  │      Python API         │    │           CLI               │  │
│  │   PromptManager(...)    │    │    agno-prompts ...         │  │
│  └───────────┬─────────────┘    └──────────────┬──────────────┘  │
│              │                                  │                 │
│              └──────────────┬───────────────────┘                 │
│                             ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                     PromptManager                             ││
│  │  • create()  • edit()  • snapshot()  • fork()                ││
│  │  • render()  • search()  • compare()  • export_lineage()     ││
│  └──────────────────────────┬───────────────────────────────────┘│
│                             ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                   MLflowPromptStore                           ││
│  │  • save()  • load()  • search_runs()  • delete()             ││
│  └──────────────────────────┬───────────────────────────────────┘│
│                             ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                      MLflow Backend                           ││
│  │  Experiments → Prompts    Runs → Versions    Artifacts → JSON││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Storage                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │  Local Files   │  │    SQLite      │  │  MLflow Server     │  │
│  │   ./mlruns     │  │ sqlite:///db   │  │ http://server:5000 │  │
│  └────────────────┘  └────────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Installation

### Basic Installation

```bash
pip install agno[mlflow]
```

### Verify Installation

```python
from agno.prompt_versioning import PromptManager
manager = PromptManager()
print("Ready!")
```

### Storage Backend Options

| Backend | URI Format | Use Case |
|---------|-----------|----------|
| Local filesystem | `mlruns` or `./path` | Development, single user |
| SQLite | `sqlite:///prompts.db` | Small teams, local persistence |
| PostgreSQL | `postgresql://user:pass@host/db` | Production, multi-user |
| MLflow Server | `http://mlflow-server:5000` | Enterprise, centralized |

```python
# Local (default)
manager = PromptManager(tracking_uri="mlruns")

# SQLite
manager = PromptManager(tracking_uri="sqlite:///prompts.db")

# Remote MLflow server
manager = PromptManager(tracking_uri="http://mlflow.company.com:5000")
```

---

## Core Concepts

### Prompt Identity

Each prompt has a **name** (human-readable identifier) and each version has a unique **ID**.

```
Name: "customer_greeting"
├── prompt_a1b2c3... (v1) ← Original
├── prompt_d4e5f6... (v2) ← Edit of v1
├── prompt_g7h8i9... (v3) ← Snapshot "prod-v1"
└── prompt_j0k1l2... (v4) ← Latest
```

### Version Lifecycle

```
                                    ┌─────────────┐
                         ┌─────────►│  SNAPSHOT   │
                         │          │ (immutable) │
                         │          └─────────────┘
                         │ snapshot()
                         │
┌─────────┐   edit()   ┌─┴───────┐   activate()   ┌─────────┐
│  DRAFT  │◄──────────►│  DRAFT  │───────────────►│ ACTIVE  │
│  (v1)   │            │  (v2)   │                │  (v3)   │
└─────────┘            └─────────┘                └────┬────┘
     │                                                 │
     │                                                 │ archive()
     │                                                 ▼
     │                                           ┌──────────┐
     │                                           │ ARCHIVED │
     │                                           └──────────┘
     │
     │ fork()
     ▼
┌─────────────────────┐
│ NEW PROMPT (v1)     │
│ forked_from = orig  │
└─────────────────────┘
```

### Template Variables

Templates use `{{variable}}` syntax for substitution:

```python
template = "Hello {{name}}, welcome to {{company}}!"

# Variables automatically extracted: {'name', 'company'}

# Render with all variables
result = prompt.render(name="Alice", company="Acme")
# → "Hello Alice, welcome to Acme!"
```

### Lineage Tracking

Every version maintains references to its origins:

| Field | Purpose |
|-------|---------|
| `parent_id` | Previous version in edit chain |
| `forked_from` | Original prompt (for forks only) |
| `content_hash` | SHA256 fingerprint for integrity |

```
                    ┌─────────────────┐
                    │ greeting (v1)   │
                    │ id: prompt_aaa  │
                    └────────┬────────┘
                             │ edit()
                             ▼
                    ┌─────────────────┐
                    │ greeting (v2)   │
                    │ id: prompt_bbb  │
                    │ parent: aaa     │
                    └────────┬────────┘
              ┌──────────────┴──────────────┐
              │ snapshot("prod")            │ fork("greeting_v2")
              ▼                             ▼
     ┌─────────────────┐          ┌─────────────────────┐
     │ greeting (v3)   │          │ greeting_v2 (v1)    │
     │ SNAPSHOT        │          │ forked_from: bbb    │
     │ snap: "prod"    │          └─────────────────────┘
     └─────────────────┘
```

---

## Data Models

### PromptTemplate

The core template container with variable extraction.

```python
from agno.prompt_versioning import PromptTemplate

template = PromptTemplate(content="Summarize {{text}} in {{style}} style.")
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `content` | `str` | Raw template string |
| `variables` | `Set[str]` | Auto-extracted variable names |

| Method | Signature | Description |
|--------|-----------|-------------|
| `render` | `(**kwargs) → str` | Substitute all variables (raises if missing) |
| `partial_render` | `(**kwargs) → PromptTemplate` | Substitute some, keep placeholders |
| `validate_variables` | `(required: Set[str]) → bool` | Check if template has required vars |

```python
# Full render
template.render(text="article", style="concise")
# → "Summarize article in concise style."

# Partial render
partial = template.partial_render(style="concise")
# → PromptTemplate("Summarize {{text}} in concise style.")

# Validation
template.validate_variables({"text", "style"})  # True
template.validate_variables({"text", "style", "extra"})  # False
```

---

### PromptMetadata

Extensible metadata container.

```python
from agno.prompt_versioning import PromptMetadata

metadata = PromptMetadata(
    author="ml-team",
    description="Customer greeting for onboarding flow",
    tags=["greeting", "onboarding", "customer"],
    model_compatibility=["gpt-4", "claude-3"],
    use_case="New user welcome message",
    custom={"department": "marketing", "approved_by": "jane@company.com"}
)
```

| Field | Type | Description |
|-------|------|-------------|
| `author` | `str?` | Creator/owner |
| `description` | `str?` | Purpose description |
| `tags` | `List[str]` | Categorization labels |
| `model_compatibility` | `List[str]` | Compatible model IDs |
| `use_case` | `str?` | Intended usage |
| `custom` | `Dict[str, Any]` | Arbitrary key-value pairs |

| Method | Description |
|--------|-------------|
| `add_tag(tag)` | Add tag if not present |
| `remove_tag(tag)` | Remove tag if present |

---

### PromptVersion

Complete versioned prompt with full tracking.

```python
from agno.prompt_versioning import PromptVersion, PromptTemplate, PromptStatus

version = PromptVersion(
    id="prompt_abc123",
    name="greeting",
    version=1,
    template=PromptTemplate(content="Hello {{name}}!"),
    status=PromptStatus.DRAFT,
    metadata=PromptMetadata(author="team"),
    parent_id=None,
    forked_from=None,
    snapshot_name=None,
)
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique identifier (auto-generated) |
| `name` | `str` | Human-readable name |
| `version` | `int` | Version number (≥1) |
| `template` | `PromptTemplate` | The prompt content |
| `status` | `PromptStatus` | DRAFT, ACTIVE, ARCHIVED, SNAPSHOT |
| `metadata` | `PromptMetadata` | Associated metadata |
| `parent_id` | `str?` | ID of previous version |
| `forked_from` | `str?` | ID of fork source |
| `snapshot_name` | `str?` | Name if this is a snapshot |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |
| `content_hash` | `str` | SHA256[:16] of content |

| Property/Method | Returns | Description |
|-----------------|---------|-------------|
| `content` | `str` | Raw template content |
| `variables` | `Set[str]` | Template variables |
| `render(**kwargs)` | `str` | Render with substitution |
| `is_snapshot()` | `bool` | True if status is SNAPSHOT |
| `is_fork()` | `bool` | True if forked_from is set |
| `get_version_string()` | `str` | `"v1"`, `"v2"`, etc. |
| `get_full_name()` | `str` | `"name:v1"` format |

---

### PromptStatus

```python
from agno.prompt_versioning import PromptStatus

PromptStatus.DRAFT     # Work in progress
PromptStatus.ACTIVE    # Ready for production use
PromptStatus.ARCHIVED  # Deprecated, kept for history
PromptStatus.SNAPSHOT  # Immutable named release
```

---

### PromptDiff

Comparison between two versions.

```python
from agno.prompt_versioning import PromptDiff

diff = PromptDiff.compute(old_prompt, new_prompt)
```

| Field | Type | Description |
|-------|------|-------------|
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

Complete history of a prompt.

```python
lineage = manager.get_lineage("greeting")
```

| Field | Type | Description |
|-------|------|-------------|
| `root_id` | `str` | ID of original v1 |
| `name` | `str` | Prompt name |
| `versions` | `List[PromptVersion]` | All versions |
| `forks` | `List[str]` | IDs of forked prompts |
| `snapshots` | `Dict[str, str]` | `{name: version_id}` |

| Method | Returns | Description |
|--------|---------|-------------|
| `get_version(n)` | `PromptVersion?` | Get specific version |
| `get_latest()` | `PromptVersion?` | Get highest version |
| `get_snapshot(name)` | `PromptVersion?` | Get by snapshot name |
| `get_history()` | `List[Dict]` | Summary timeline |

---

## PromptManager API

### Constructor

```python
from agno.prompt_versioning import PromptManager

manager = PromptManager(
    tracking_uri: str = "mlruns",              # MLflow tracking URI
    experiment_prefix: str = "prompt_versioning"  # Experiment namespace
)
```

---

### Create Operations

#### create()

Create a new prompt (v1).

```python
prompt = manager.create(
    name: str,                              # Required: unique identifier
    content: str,                           # Required: template content
    description: str = None,                # Optional: description
    author: str = None,                     # Optional: author name
    tags: List[str] = None,                 # Optional: categorization
    model_compatibility: List[str] = None,  # Optional: compatible models
    use_case: str = None,                   # Optional: intended use
    custom_metadata: Dict[str, Any] = None  # Optional: custom fields
) → PromptVersion
```

```python
prompt = manager.create(
    name="customer_greeting",
    content="Hello {{customer_name}}, thank you for choosing {{company}}!",
    description="Welcome message for new customers",
    author="marketing-team",
    tags=["greeting", "customer", "onboarding"],
    model_compatibility=["gpt-4", "gpt-3.5-turbo"],
    use_case="Post-signup welcome email"
)
```

---

### Edit Operations

#### edit()

Create a new version with changes.

```python
new_version = manager.edit(
    prompt_id: str,                         # Required: ID to edit
    content: str = None,                    # New content (keeps existing if None)
    description: str = None,                # New description
    author: str = None,                     # New author
    tags: List[str] = None,                 # New tags (replaces existing)
    model_compatibility: List[str] = None,  # New compatibility
    use_case: str = None,                   # New use case
    custom_metadata: Dict[str, Any] = None, # Merged with existing
    status: PromptStatus = None             # New status
) → PromptVersion
```

```python
# Edit content
v2 = manager.edit(prompt.id, content="Hi {{customer_name}}! Welcome to {{company}}.")

# Edit metadata only
v3 = manager.edit(prompt.id, tags=["greeting", "vip", "priority"])

# Change status
v4 = manager.edit(prompt.id, status=PromptStatus.ACTIVE)
```

#### activate() / archive()

Convenience methods for status changes.

```python
manager.activate(prompt_id: str) → PromptVersion  # Sets ACTIVE
manager.archive(prompt_id: str) → PromptVersion   # Sets ARCHIVED
```

> **Note:** These create new versions. They don't modify in place.

---

### Snapshot Operations

#### snapshot()

Create an immutable named release.

```python
snap = manager.snapshot(
    prompt_id: str,           # Required: version to snapshot
    snapshot_name: str,       # Required: unique name (within this prompt)
    description: str = None   # Optional: release notes
) → PromptVersion
```

```python
snap = manager.snapshot(
    prompt.id,
    "prod-2024-01",
    description="January production release - approved by QA"
)
```

---

### Fork Operations

#### fork()

Create a new independent prompt from an existing one.

```python
forked = manager.fork(
    prompt_id: str,           # Required: source prompt
    new_name: str,            # Required: new prompt name
    description: str = None,  # Optional: fork description
    author: str = None        # Optional: fork author
) → PromptVersion  # v1 of new prompt, forked_from set
```

```python
# Create experimental variant
experimental = manager.fork(
    prompt.id,
    "customer_greeting_formal",
    description="More formal greeting for enterprise customers"
)
```

#### duplicate()

Convenience method for quick copying.

```python
copy = manager.duplicate(
    prompt_id: str,
    new_name: str = None  # Uses "{name}_copy" if not provided
) → PromptVersion
```

---

### Read Operations

#### get() / get_by_name() / get_snapshot()

```python
# By ID
prompt = manager.get(prompt_id: str) → PromptVersion?

# By name (latest version)
prompt = manager.get_by_name(name: str, version: int = None) → PromptVersion?

# By snapshot name
prompt = manager.get_snapshot(name: str, snapshot_name: str) → PromptVersion?
```

```python
# Get latest
latest = manager.get_by_name("greeting")

# Get specific version
v2 = manager.get_by_name("greeting", version=2)

# Get production snapshot
prod = manager.get_snapshot("greeting", "prod-v1")
```

---

### List Operations

```python
# All prompt names
names = manager.list_prompts() → List[str]

# All versions of a prompt
versions = manager.list_versions(name: str) → List[PromptVersion]

# All snapshots
snapshots = manager.list_snapshots(name: str) → List[Tuple[str, PromptVersion]]
```

---

### Search Operations

#### search()

Find prompts matching criteria.

```python
results = manager.search(
    name_pattern: str = None,      # Prefix match on name
    tags: List[str] = None,        # Must have ALL these tags
    status: PromptStatus = None,   # Status filter
    author: str = None,            # Author filter
    include_forks: bool = True     # Include forked prompts
) → List[PromptVersion]
```

```python
# Find all active greeting prompts
results = manager.search(
    name_pattern="greeting",
    status=PromptStatus.ACTIVE
)

# Find by tags
results = manager.search(tags=["customer", "onboarding"])

# Exclude forks
originals = manager.search(include_forks=False)
```

---

### Comparison Operations

#### compare()

Diff two versions.

```python
diff = manager.compare(
    prompt_id_1: str,
    prompt_id_2: str
) → PromptDiff
```

```python
diff = manager.compare(v1.id, v2.id)
if diff.content_changed:
    print(f"Old: {diff.old_content}")
    print(f"New: {diff.new_content}")
print(f"Variables added: {diff.variables_added}")
print(f"Variables removed: {diff.variables_removed}")
```

#### get_lineage()

Get complete history.

```python
lineage = manager.get_lineage(name: str) → PromptLineage
```

---

### Render Operations

#### render()

Substitute variables and return final string.

```python
result = manager.render(
    prompt_id: str = None,        # Direct ID lookup
    prompt_name: str = None,      # Name lookup
    version: int = None,          # Specific version (with prompt_name)
    snapshot_name: str = None,    # Snapshot (with prompt_name)
    **variables                   # Template variables
) → str
```

**Lookup Priority:** `prompt_id` > `prompt_name + snapshot_name` > `prompt_name + version` > `prompt_name` (latest)

```python
# Latest version
result = manager.render(prompt_name="greeting", customer_name="Alice", company="Acme")

# Specific version
result = manager.render(prompt_name="greeting", version=2, customer_name="Bob", company="Acme")

# Production snapshot
result = manager.render(prompt_name="greeting", snapshot_name="prod-v1", customer_name="Carol", company="Acme")

# By ID
result = manager.render(prompt_id="prompt_abc123", customer_name="Dave", company="Acme")
```

---

### Delete Operations

```python
deleted = manager.delete(prompt_id: str) → bool  # True if deleted
```

> **Note:** MLflow performs soft delete. Data persists but is hidden.

---

### Export Operations

#### export_lineage()

Export full history as dictionary.

```python
data = manager.export_lineage(name: str) → Dict[str, Any]
```

```python
data = manager.export_lineage("greeting")
# Returns:
{
    "name": "greeting",
    "root_id": "prompt_abc123",
    "versions": [
        {
            "id": "prompt_abc123",
            "version": 1,
            "content": "Hello {{name}}!",
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
    "forks": ["prompt_fork1"]
}
```

---

## CLI Reference

### Global Options

| Option | Default | Description |
|--------|---------|-------------|
| `-u, --tracking-uri` | `mlruns` | MLflow tracking URI |

### Command Summary

| Command | Description |
|---------|-------------|
| `create NAME CONTENT` | Create new prompt |
| `edit NAME` | Edit prompt (new version) |
| `snapshot NAME SNAP_NAME` | Create named snapshot |
| `fork SOURCE NEW_NAME` | Fork to new prompt |
| `list` | List all prompts |
| `versions NAME` | List all versions |
| `show NAME` | Show prompt details |
| `render NAME` | Render with variables |
| `compare NAME V1 V2` | Compare versions |
| `export NAME` | Export to JSON |
| `delete PROMPT_ID` | Delete version |

### Detailed Command Reference

#### create

```bash
agno-prompts create NAME CONTENT [OPTIONS]

Options:
  -d, --description TEXT  Description
  -a, --author TEXT       Author name
  -t, --tags TEXT         Comma-separated tags
  -u, --tracking-uri TEXT MLflow URI [default: mlruns]
```

```bash
agno-prompts create summarizer \
  "Summarize: {{text}}" \
  -d "Text summarization" \
  -a "ml-team" \
  -t "nlp,summarization"
```

#### edit

```bash
agno-prompts edit NAME [OPTIONS]

Options:
  -c, --content TEXT      New content
  -d, --description TEXT  New description
  -a, --author TEXT       New author
  -t, --tags TEXT         New tags (replaces)
  -v, --version INT       Version to edit [default: latest]
```

```bash
agno-prompts edit summarizer -c "Please summarize:\n{{text}}"
```

#### snapshot

```bash
agno-prompts snapshot NAME SNAPSHOT_NAME [OPTIONS]

Options:
  -d, --description TEXT  Snapshot description
  -v, --version INT       Version to snapshot [default: latest]
```

```bash
agno-prompts snapshot summarizer prod-v1 -d "Production release"
```

#### fork

```bash
agno-prompts fork SOURCE NEW_NAME [OPTIONS]

Options:
  -d, --description TEXT  Fork description
  -a, --author TEXT       Fork author
  -v, --version INT       Version to fork [default: latest]
```

```bash
agno-prompts fork summarizer summarizer_detailed
```

#### list

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

#### versions

```bash
agno-prompts versions NAME
```

Output:
```
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Version ┃ ID              ┃ Status ┃ Snapshot ┃ Created         ┃ Hash     ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ v1      │ prompt_abc1...  │ draft  │ -        │ 2024-01-15 10:30│ a1b2c3d4 │
│ v2      │ prompt_def2...  │ draft  │ -        │ 2024-01-15 11:00│ e5f6g7h8 │
│ v3      │ prompt_ghi3...  │ snap   │ prod-v1  │ 2024-01-15 12:00│ e5f6g7h8 │
└─────────┴─────────────────┴────────┴──────────┴─────────────────┴──────────┘
```

#### show

```bash
agno-prompts show NAME [OPTIONS]

Options:
  -v, --version INT       Specific version
  -s, --snapshot TEXT     Snapshot name
```

#### render

```bash
agno-prompts render NAME [OPTIONS]

Options:
  -V, --var TEXT          Variable (key=value), repeatable
  -v, --version INT       Specific version
  -s, --snapshot TEXT     Snapshot name
```

```bash
agno-prompts render greeting \
  -V name=Alice \
  -V company=Acme \
  -s prod-v1
```

#### compare

```bash
agno-prompts compare NAME V1 V2
```

```bash
agno-prompts compare summarizer 1 2
```

Output:
```
Comparing summarizer: v1 → v2

Content changed:
- Summarize: {{text}}
+ Please summarize:\n{{text}}

Variables added: (none)
Variables removed: (none)
```

#### export

```bash
agno-prompts export NAME [OPTIONS]

Options:
  -o, --output FILE       Output file (stdout if omitted)
```

```bash
agno-prompts export summarizer -o backup.json
```

#### delete

```bash
agno-prompts delete PROMPT_ID [OPTIONS]

Options:
  -f, --force             Skip confirmation
```

---

## Workflows

### Development Workflow

```
1. Create initial prompt
   └─► greeting (v1) [DRAFT]

2. Iterate with edits
   └─► greeting (v2) [DRAFT]
   └─► greeting (v3) [DRAFT]

3. Ready for testing → activate
   └─► greeting (v4) [ACTIVE]

4. Approved for production → snapshot
   └─► greeting (v5) [SNAPSHOT: prod-v1]

5. Continue development
   └─► greeting (v6) [DRAFT]
   └─► greeting (v7) [DRAFT]

6. New release
   └─► greeting (v8) [SNAPSHOT: prod-v2]
```

### Experimentation Workflow

```
Main prompt: greeting (v5) [prod-v1]
                │
                ├── fork() ──► greeting_formal (v1)
                │                    └─► (v2)
                │                    └─► (v3) ← success!
                │
                └── fork() ──► greeting_casual (v1)
                                     └─► (v2) ← not working, abandon

# Merge successful experiment back
greeting (v6) ← copy content from greeting_formal (v3)
```

### Team Collaboration Workflow

```
Day 1: Alice creates
  └─► summary-prompt (v1) [author: alice]

Day 2: Bob edits
  └─► summary-prompt (v2) [author: bob]

Day 3: Carol snapshots for QA
  └─► summary-prompt (v3) [SNAPSHOT: qa-review]

Day 4: QA approves, Carol snapshots for prod
  └─► summary-prompt (v4) [SNAPSHOT: prod-v1]

Day 5: Dave experiments with fork
  └─► summary-prompt-experiment (v1) [forked, author: dave]
```

---

## Advanced Usage

### Batch Operations

```python
# Create multiple related prompts
prompts = {}
for task in ["summarize", "translate", "analyze"]:
    prompts[task] = manager.create(
        name=f"text_{task}",
        content=f"{{{{instruction}}}}\n\nText: {{{{text}}}}",
        tags=["text-processing", task]
    )

# Snapshot all for release
for name, prompt in prompts.items():
    manager.snapshot(prompt.id, "release-1.0")
```

### Programmatic Search and Update

```python
# Find all drafts by specific author
drafts = manager.search(
    author="alice",
    status=PromptStatus.DRAFT
)

# Activate all that are ready
for prompt in drafts:
    if "ready" in prompt.metadata.tags:
        manager.activate(prompt.id)
```

### Content Hash Verification

```python
# Verify content integrity
prompt = manager.get_by_name("critical_prompt")
import hashlib
computed = hashlib.sha256(prompt.content.encode()).hexdigest()[:16]
assert computed == prompt.content_hash, "Content may have been corrupted!"
```

### Export/Import for Migration

```python
# Export from source
source = PromptManager(tracking_uri="old_mlruns")
data = source.export_lineage("important_prompt")

# Save to file
import json
with open("migration.json", "w") as f:
    json.dump(data, f)

# Import to destination (manual recreation)
dest = PromptManager(tracking_uri="new_mlruns")
for v in data["versions"]:
    if v["version"] == 1:
        dest.create(name=data["name"], content=v["content"], ...)
    else:
        latest = dest.get_by_name(data["name"])
        dest.edit(latest.id, content=v["content"], ...)
```

---

## Error Handling

### Exception Types

| Error | Cause | Solution |
|-------|-------|----------|
| `ValueError: Prompt not found` | Invalid ID/name | Verify ID/name exists |
| `ValueError: Missing required variables: {x}` | Incomplete render | Provide all template variables |
| `ValueError: Snapshot 'x' already exists` | Duplicate snapshot | Use unique snapshot name |
| `ValueError: Prompt with name 'x' already exists` | Fork name collision | Choose different name |
| `ImportError: MLflow is required` | MLflow not installed | `pip install mlflow` |

### Defensive Coding

```python
# Safe get with fallback
prompt = manager.get_by_name("greeting")
if prompt is None:
    prompt = manager.create("greeting", "Default: Hello {{name}}!")

# Safe render with validation
try:
    result = manager.render(prompt_name="greeting", **user_variables)
except ValueError as e:
    if "Missing required variables" in str(e):
        # Handle missing variables
        missing = extract_missing_vars(e)
        result = f"Error: Please provide: {missing}"
    else:
        raise
```

---

## Best Practices

### Naming Conventions

| Pattern | Example | Use Case |
|---------|---------|----------|
| `domain.task` | `customer.greeting` | Namespacing by domain |
| `task_variant` | `summarize_concise` | Task with variation |
| `v{N}` suffix | `greeting_v2` | Fork with version hint |

### Tagging Strategy

```python
# Hierarchical tags
tags=[
    "domain:customer",
    "task:greeting",
    "channel:email",
    "lang:en",
    "status:production"
]

# Searchable
manager.search(tags=["domain:customer", "channel:email"])
```

### Snapshot Naming

| Pattern | Example | Use Case |
|---------|---------|----------|
| `prod-vN` | `prod-v1` | Production releases |
| `YYYY-MM` | `2024-01` | Monthly releases |
| `release-X.Y` | `release-1.2` | Semantic versioning |
| `env-date` | `staging-2024-01-15` | Environment + date |

### Team Workflows

1. **Development**: Work in DRAFT status
2. **Review**: Create snapshot for review (`review-{date}`)
3. **Staging**: Activate and test
4. **Production**: Create production snapshot (`prod-vN`)
5. **Rollback**: Load previous snapshot if issues

### Performance Tips

- Use specific version/snapshot when possible (avoids search)
- Cache `PromptManager` instance (reuse connection)
- Use `prompt_id` for frequently accessed prompts
- Export lineage for offline analysis (reduces queries)

---

## Appendix: Complete API Reference

### PromptManager Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `create(...)` | `PromptVersion` | Create new prompt |
| `edit(...)` | `PromptVersion` | Edit (new version) |
| `snapshot(...)` | `PromptVersion` | Create snapshot |
| `fork(...)` | `PromptVersion` | Fork to new prompt |
| `duplicate(...)` | `PromptVersion` | Quick copy |
| `get(id)` | `PromptVersion?` | Get by ID |
| `get_by_name(name, version?)` | `PromptVersion?` | Get by name |
| `get_snapshot(name, snap)` | `PromptVersion?` | Get snapshot |
| `list_prompts()` | `List[str]` | All names |
| `list_versions(name)` | `List[PromptVersion]` | All versions |
| `list_snapshots(name)` | `List[Tuple]` | All snapshots |
| `search(...)` | `List[PromptVersion]` | Search prompts |
| `get_lineage(name)` | `PromptLineage` | Full history |
| `compare(id1, id2)` | `PromptDiff` | Diff versions |
| `render(...)` | `str` | Render template |
| `delete(id)` | `bool` | Delete version |
| `activate(id)` | `PromptVersion` | Set ACTIVE |
| `archive(id)` | `PromptVersion` | Set ARCHIVED |
| `export_lineage(name)` | `Dict` | Export JSON |
