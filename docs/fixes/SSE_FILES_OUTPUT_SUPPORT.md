# SSE Files Output Support Fix

## Status: FIXED

**Branch:** `fix/sse-files-output-support`
**Base:** `fork/custom-v2.3.21`

### Commits

| Commit | Description |
|--------|-------------|
| `128fe9a77` | feat: Add files support to SSE streaming events |
| `91a14aeed` | feat: attach tool result media to last assistant message for persistence |

---

## Issue Summary

Files returned from tools via `ToolResult.files` were not serialized in SSE (Server-Sent Events) streaming responses, even though the data pipeline correctly propagated them through `ModelResponse` and `RunOutput`.

Additionally, media from tool results was not persisted to messages, causing it to be lost when reloading sessions (since `get_chat_history()` skips tool messages).

---

## Background

### File Class Usage

The `agno.media.File` class serves two purposes:

1. **INPUT**: Sending documents (PDFs, text files) to models
   - Documented: `files=[File(filepath=pdf_path)]`
   - Examples: `examples/models/anthropic/pdf_input_local`

2. **OUTPUT**: Tools generating files for users to download
   - Used by: `FileGenerationTools` returning `ToolResult(files=[...])`
   - **This use case was broken** - files didn't appear in SSE responses

### Evidence of Incomplete Feature (Before Fix)

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
RunOutput.files  ← Files existed here but never reached SSE (FIXED)
```

### Previously Broken Path (SSE Layer) - NOW FIXED

```
RunOutput.files
    ↓
    │ libs/agno/agno/utils/events.py (create_run_completed_event)
    │ NOW: files parameter passed ✓
    ↓
RunCompletedEvent  ← 'files' field now defined ✓
    ↓
    │ libs/agno/agno/run/base.py (BaseRunOutputEvent.to_dict)
    │ NOW: 'files' serialization added ✓
    ↓
SSE JSON output  ← Files now appear ✓
```

---

## Solution Implemented

### Commit 1: `128fe9a77` - Add files support to SSE streaming events

#### Files Changed

| File | Lines Added |
|------|-------------|
| `libs/agno/agno/run/agent.py` | +2 |
| `libs/agno/agno/run/team.py` | +2 |
| `libs/agno/agno/run/base.py` | +11 |
| `libs/agno/agno/utils/events.py` | +4 |

#### Diff: `libs/agno/agno/run/agent.py`

```diff
@@ -262,6 +262,7 @@ class RunCompletedEvent(BaseAgentRunEvent):
     images: Optional[List[Image]] = None  # Images attached to the response
     videos: Optional[List[Video]] = None  # Videos attached to the response
     audio: Optional[List[Audio]] = None  # Audio attached to the response
+    files: Optional[List[File]] = None  # Files attached to the response
     response_audio: Optional[Audio] = None  # Model audio response
     references: Optional[List[MessageReferences]] = None
     additional_input: Optional[List[Message]] = None
@@ -404,6 +405,7 @@ class ToolCallCompletedEvent(BaseAgentRunEvent):
     images: Optional[List[Image]] = None  # Images produced by the tool call
     videos: Optional[List[Video]] = None  # Videos produced by the tool call
     audio: Optional[List[Audio]] = None  # Audio produced by the tool call
+    files: Optional[List[File]] = None  # Files produced by the tool call
```

#### Diff: `libs/agno/agno/run/team.py`

```diff
@@ -256,6 +256,7 @@ class RunCompletedEvent(BaseTeamRunEvent):
     images: Optional[List[Image]] = None  # Images attached to the response
     videos: Optional[List[Video]] = None  # Videos attached to the response
     audio: Optional[List[Audio]] = None  # Audio attached to the response
+    files: Optional[List[File]] = None  # Files attached to the response
     response_audio: Optional[Audio] = None  # Model audio response
     references: Optional[List[MessageReferences]] = None
     additional_input: Optional[List[Message]] = None
@@ -377,6 +378,7 @@ class ToolCallCompletedEvent(BaseTeamRunEvent):
     images: Optional[List[Image]] = None  # Images produced by the tool call
     videos: Optional[List[Video]] = None  # Videos produced by the tool call
     audio: Optional[List[Audio]] = None  # Audio produced by the tool call
+    files: Optional[List[File]] = None  # Files produced by the tool call
```

#### Diff: `libs/agno/agno/run/base.py`

```diff
@@ -5,7 +5,7 @@ from typing import Any, Dict, List, Optional, Type, Union
 from pydantic import BaseModel

 from agno.filters import FilterExpr
-from agno.media import Audio, Image, Video
+from agno.media import Audio, File, Image, Video
 from agno.models.message import Citations, Message, MessageReferences
 from agno.models.metrics import Metrics
 from agno.reasoning.step import ReasoningStep
@@ -41,6 +41,7 @@ class BaseRunOutputEvent:
                 "images",
                 "videos",
                 "audio",
+                "files",
                 "response_audio",
                 "citations",
                 "member_responses",
@@ -97,6 +98,14 @@ class BaseRunOutputEvent:
                 else:
                     _dict["audio"].append(aud)

+        if hasattr(self, "files") and self.files is not None:
+            _dict["files"] = []
+            for f in self.files:
+                if isinstance(f, File):
+                    _dict["files"].append(f.to_dict())
+                else:
+                    _dict["files"].append(f)
+
         if hasattr(self, "response_audio") and self.response_audio is not None:
             if isinstance(self.response_audio, Audio):
                 _dict["response_audio"] = self.response_audio.to_dict()
```

#### Diff: `libs/agno/agno/utils/events.py`

```diff
@@ -103,6 +103,7 @@ def create_team_run_completed_event(from_run_response: TeamRunOutput) -> TeamRun
         images=from_run_response.images,  # type: ignore
         videos=from_run_response.videos,  # type: ignore
         audio=from_run_response.audio,  # type: ignore
+        files=from_run_response.files,  # type: ignore
         response_audio=from_run_response.response_audio,  # type: ignore
         references=from_run_response.references,  # type: ignore
         additional_input=from_run_response.additional_input,  # type: ignore
@@ -129,6 +130,7 @@ def create_run_completed_event(from_run_response: RunOutput) -> RunCompletedEven
         images=from_run_response.images,  # type: ignore
         videos=from_run_response.videos,  # type: ignore
         audio=from_run_response.audio,  # type: ignore
+        files=from_run_response.files,  # type: ignore
         response_audio=from_run_response.response_audio,  # type: ignore
         references=from_run_response.references,  # type: ignore
         additional_input=from_run_response.additional_input,  # type: ignore
@@ -544,6 +546,7 @@ def create_tool_call_completed_event(
         images=from_run_response.images,
         videos=from_run_response.videos,
         audio=from_run_response.audio,
+        files=from_run_response.files,
     )


@@ -560,6 +563,7 @@ def create_team_tool_call_completed_event(
         images=from_run_response.images,
         videos=from_run_response.videos,
         audio=from_run_response.audio,
+        files=from_run_response.files,
     )
```

---

### Commit 2: `91a14aeed` - Attach tool result media to last assistant message for persistence

#### Problem

Files/images/videos/audio from tool results were stored on `run_response` but not persisted to messages. Since `get_chat_history()` skips tool messages (`role="tool"`), this media was lost when reloading sessions.

#### Solution

Add `_attach_media_to_last_assistant_message()` method that attaches run_response media to the final assistant message before storage.

#### Files Changed

| File | Lines Added |
|------|-------------|
| `libs/agno/agno/agent/agent.py` | +37 |
| `libs/agno/agno/team/team.py` | +37 |

#### Diff: `libs/agno/agno/agent/agent.py`

```diff
@@ -11180,10 +11180,47 @@ class Agent:
         # Save session to memory
         await self.asave_session(session=session)

+    def _attach_media_to_last_assistant_message(self, run_response: RunOutput) -> None:
+        """
+        Attach files/images/videos/audio from run_response to the last assistant message.
+        This ensures media from tool results is persisted with the message for later retrieval.
+        Tool messages (role="tool") are skipped by get_chat_history(), so we attach to assistant.
+        """
+        if not run_response.messages:
+            return
+
+        has_media = run_response.files or run_response.images or run_response.videos or run_response.audio
+        if not has_media:
+            return
+
+        # Find the last assistant message and attach media
+        for msg in reversed(run_response.messages):
+            if msg.role == "assistant":
+                if run_response.files:
+                    if msg.files is None:
+                        msg.files = []
+                    msg.files.extend(run_response.files)
+                if run_response.images:
+                    if msg.images is None:
+                        msg.images = []
+                    msg.images.extend(run_response.images)
+                if run_response.videos:
+                    if msg.videos is None:
+                        msg.videos = []
+                    msg.videos.extend(run_response.videos)
+                if run_response.audio:
+                    if msg.audio is None:
+                        msg.audio = []
+                    msg.audio.extend(run_response.audio)
+                break
+
     def _scrub_run_output_for_storage(self, run_response: RunOutput) -> None:
         """
         Scrub run output based on storage flags before persisting to database.
         """
+        # First attach media to messages so it can be persisted (or scrubbed if store_media=False)
+        self._attach_media_to_last_assistant_message(run_response)
+
         if not self.store_media:
             scrub_media_from_run_output(run_response)
```

#### Diff: `libs/agno/agno/team/team.py`

```diff
@@ -4715,11 +4715,48 @@ class Team:
                     return member.name or entity_id
         return entity_id

+    def _attach_media_to_last_assistant_message(self, run_response: TeamRunOutput) -> None:
+        """
+        Attach files/images/videos/audio from run_response to the last assistant message.
+        This ensures media from tool results is persisted with the message for later retrieval.
+        Tool messages (role="tool") are skipped by get_chat_history(), so we attach to assistant.
+        """
+        if not run_response.messages:
+            return
+
+        has_media = run_response.files or run_response.images or run_response.videos or run_response.audio
+        if not has_media:
+            return
+
+        # Find the last assistant message and attach media
+        for msg in reversed(run_response.messages):
+            if msg.role == "assistant":
+                if run_response.files:
+                    if msg.files is None:
+                        msg.files = []
+                    msg.files.extend(run_response.files)
+                if run_response.images:
+                    if msg.images is None:
+                        msg.images = []
+                    msg.images.extend(run_response.images)
+                if run_response.videos:
+                    if msg.videos is None:
+                        msg.videos = []
+                    msg.videos.extend(run_response.videos)
+                if run_response.audio:
+                    if msg.audio is None:
+                        msg.audio = []
+                    msg.audio.extend(run_response.audio)
+                break
+
     def _scrub_run_output_for_storage(self, run_response: TeamRunOutput) -> bool:
         """
         Scrub run output based on storage flags before persisting to database.
         Returns True if any scrubbing was done, False otherwise.
         """
+        # First attach media to messages so it can be persisted (or scrubbed if store_media=False)
+        self._attach_media_to_last_assistant_message(run_response)
+
         scrubbed = False

         if not self.store_media:
```

---

## Testing

After fix, SSE events include files:

```json
{
  "event": "ToolCallCompleted",
  "tool": {
    "tool_call_id": "call_xxx",
    "tool_name": "generate_pdf"
  },
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

And files persist across session reloads via `get_chat_history()`.

---

## Reference: Working Data Layer

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

## Related Documentation

- [PDF Input - Anthropic](https://docs.agno.com/examples/models/anthropic/pdf_input_local)
- [Tools Overview](https://docs.agno.com/basics/tools/overview)
- [Agno v2.0 Changelog](https://docs.agno.com/how-to/v2-changelog)
