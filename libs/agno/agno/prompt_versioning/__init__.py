"""
Prompt Versioning Module - MLflow-backed prompt management system.

This module provides:
- PromptVersion: Data model for versioned prompts
- PromptTemplate: Template with variable substitution
- MLflowPromptStore: MLflow-backed storage for prompts
- PromptManager: High-level API for versioning, snapshots, editing, and forking
- SystemPromptEditor: Convenience layer for component-based system prompt editing
- SystemPromptComponent: Individual component of a system prompt
- PromptComponentType: Enum of component types (ROLE, INSTRUCTIONS, etc.)

Example - Basic prompt versioning:
    >>> from agno.prompt_versioning import PromptManager
    >>> manager = PromptManager(tracking_uri="mlruns")
    >>> prompt = manager.create("my_prompt", "Hello, {{name}}!")
    >>> prompt = manager.edit(prompt.id, content="Hi, {{name}}!")
    >>> forked = manager.fork(prompt.id, "my_prompt_v2")
    >>> snapshot = manager.snapshot(prompt.id, "production-ready")

Example - Component-based system prompts:
    >>> from agno.prompt_versioning import SystemPromptEditor, PromptComponentType
    >>> editor = SystemPromptEditor(tracking_uri="mlruns")
    >>> prompt = editor.create("my_agent", [
    ...     {"type": PromptComponentType.ROLE, "content": "You are a helpful assistant."},
    ...     {"type": PromptComponentType.INSTRUCTIONS, "content": "Be concise."},
    ... ])
    >>> editor.edit_component(prompt.id, PromptComponentType.ROLE, "You are an expert coder.")
"""

from agno.prompt_versioning.models import (
    PromptComponentType,
    PromptDiff,
    PromptLineage,
    PromptMetadata,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
    SystemPromptComponent,
)
from agno.prompt_versioning.mlflow_backend import MLflowPromptStore
from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.system_prompt_editor import SystemPromptEditor

__all__ = [
    # Core models
    "PromptComponentType",
    "PromptDiff",
    "PromptLineage",
    "PromptMetadata",
    "PromptStatus",
    "PromptTemplate",
    "PromptVersion",
    "SystemPromptComponent",
    # Storage
    "MLflowPromptStore",
    # High-level APIs
    "PromptManager",
    "SystemPromptEditor",
]
