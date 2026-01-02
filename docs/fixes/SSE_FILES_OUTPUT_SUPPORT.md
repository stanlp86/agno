# SSE Files Output Support Fix

## Issue Summary

Files returned from tools via `ToolResult.files` are not serialized in SSE (Server-Sent Events) streaming responses, even though the data pipeline correctly propagates them through `ModelResponse` and `RunOutput`.

**Status**: Incomplete feature - the output capability was added to the data layer but never completed in the SSE event layer.

---

## Background

### File Class Usage

The `agno.media.File` class serves two purposes:

1. **INPUT**: Sending documents (PDFs, text files) to models
   - Documented: `files=[File(filepath=pdf_path)]`
   - Examples: `examples/models/anthropic/pdf_input_local`

2. **OUTPUT**: Tools generating files for users to download
   - Used by: `FileGenerationTools` returning `ToolResult(files=[...])`
   - **This use case is broken** - files don't appear in SSE responses

### Evidence of Incomplete Feature

| Media Type | ToolResult | ModelResponse | RunOutput | SSE Events |
|------------|------------|---------------|-----------|------------|
| images     | ✓          | ✓             | ✓         | ✓          |
| videos     | ✓          | ✓             | ✓         | ✓          |
| audio      | ✓          | ✓             | ✓         | ✓          |
| **files**  | ✓          | ✓             | ✓         | **✗**      |

---

## Data Flow Analysis

### Working Path (Data Layer)

```
ToolResult.files
    ↓
    │ libs/agno/agno/models/base.py:659-662
    │ function_call_response.files → model_response.files
    ↓
ModelResponse.files
    ↓
    │ libs/agno/agno/utils/agent.py:320-324 (store_media_util)
    │ model_response.files → run_response.files
    ↓
RunOutput.files  ← Files exist here but never reach SSE
```

### Broken Path (SSE Layer)

```
RunOutput.files
    ↓
    │ libs/agno/agno/utils/events.py:118-140 (create_run_completed_event)
    │ MISSING: files parameter not passed
    ↓
RunCompletedEvent  ← No 'files' field defined
    ↓
    │ libs/agno/agno/run/base.py:30-56 (BaseRunOutputEvent.to_dict)
    │ MISSING: No serialization for 'files'
    ↓
SSE JSON output  ← Files never appear
```

---

## Affected Files

### 1. Event Class Definitions - Missing `files` field

**File**: `libs/agno/agno/run/agent.py`

| Event Class | Line | Has images | Has videos | Has audio | Has files |
|-------------|------|------------|------------|-----------|-----------|
| `RunContentEvent` | 222-240 | ✗ (only `image` singular) | ✗ | ✗ | **✗** |
| `RunCompletedEvent` | 255-273 | ✓ (line 262) | ✓ (line 263) | ✓ (line 264) | **✗** |
| `ToolCallCompletedEvent` | 400-407 | ✓ (line 404) | ✓ (line 405) | ✓ (line 406) | **✗** |

### 2. Event Serialization - Missing `files` handler

**File**: `libs/agno/agno/run/base.py`

Lines 76-98 have serialization for:
- `images` (lines 76-82)
- `videos` (lines 84-90)
- `audio` (lines 92-98)
- **Missing**: `files` serialization

### 3. Event Creation Functions - Missing `files` parameter

**File**: `libs/agno/agno/utils/events.py`

| Function | Line | Passes images | Passes videos | Passes audio | Passes files |
|----------|------|---------------|---------------|--------------|--------------|
| `create_run_completed_event` | 118-140 | ✓ | ✓ | ✓ | **✗** |
| `create_tool_call_completed_event` | 534-547 | ✓ | ✓ | ✓ | **✗** |

---

## Working Data Layer (Reference)

### ToolResult Definition
**File**: `libs/agno/agno/tools/function.py:1196-1203`
```python
class ToolResult(BaseModel):
    content: str
    images: Optional[List[Image]] = None
    videos: Optional[List[Video]] = None
    audios: Optional[List[Audio]] = None
    files: Optional[List[File]] = None  # ← Properly defined
```

### ModelResponse Definition
**File**: `libs/agno/agno/models/response.py:88-103`
```python
@dataclass
class ModelResponse:
    images: Optional[List[Image]] = None
    videos: Optional[List[Video]] = None
    audios: Optional[List[Audio]] = None
    files: Optional[List[File]] = None  # ← Properly defined with to_dict()
```

### RunOutput Definition
**File**: `libs/agno/agno/run/agent.py:550-556`
```python
@dataclass
class RunOutput:
    images: Optional[List[Image]] = None
    videos: Optional[List[Video]] = None
    audio: Optional[List[Audio]] = None
    files: Optional[List[File]] = None  # ← Properly defined
```

### Files Extraction from Tool Results
**File**: `libs/agno/agno/models/base.py:659-662`
```python
if function_call_response.files is not None:
    if model_response.files is None:
        model_response.files = []
    model_response.files.extend(function_call_response.files)
```

### Files Storage in RunOutput
**File**: `libs/agno/agno/utils/agent.py:320-324`
```python
if model_response.files is not None:
    for file in model_response.files:
        if run_response.files is None:
            run_response.files = []
        run_response.files.append(file)
```

---

## Fix Required

### 1. Add `files` field to event classes

**File**: `libs/agno/agno/run/agent.py`

```python
# RunCompletedEvent (after line 264)
files: Optional[List[File]] = None  # Files attached to the response

# ToolCallCompletedEvent (after line 406)
files: Optional[List[File]] = None  # Files produced by the tool call
```

### 2. Add `files` serialization to `to_dict()`

**File**: `libs/agno/agno/run/base.py` (after line 98)

```python
if hasattr(self, "files") and self.files is not None:
    _dict["files"] = []
    for f in self.files:
        if isinstance(f, File):
            _dict["files"].append(f.to_dict())
        else:
            _dict["files"].append(f)
```

### 3. Update event creation functions

**File**: `libs/agno/agno/utils/events.py`

```python
# create_run_completed_event (add parameter)
files=from_run_response.files,

# create_tool_call_completed_event (add parameter)
files=from_run_response.files,
```

---

## Testing

After fix, SSE events should include files:

```json
{
  "event": "RunCompleted",
  "files": [
    {
      "id": "file:xxx",
      "url": "/api/files/file:xxx/download",
      "filename": "report.pdf",
      "mime_type": "application/pdf",
      "size": 12345
    }
  ]
}
```

---

## Related Documentation

- [PDF Input - Anthropic](https://docs.agno.com/examples/models/anthropic/pdf_input_local)
- [Tools Overview](https://docs.agno.com/basics/tools/overview)
- [Agno v2.0 Changelog](https://docs.agno.com/how-to/v2-changelog)
