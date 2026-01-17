"""
Prompt Versioning Module - MLflow-backed prompt management system.

This module provides:
- PromptVersion: Data model for versioned prompts
- PromptTemplate: Template with variable substitution
- MLflowPromptStore: MLflow-backed storage for prompts
- PromptManager: High-level API for versioning, snapshots, editing, and forking

Example:
    >>> from agno.prompt_versioning import PromptManager
    >>> manager = PromptManager(tracking_uri="mlruns")
    >>> prompt = manager.create("my_prompt", "Hello, {{name}}!")
    >>> prompt = manager.edit(prompt.id, content="Hi, {{name}}!")
    >>> forked = manager.fork(prompt.id, "my_prompt_v2")
    >>> snapshot = manager.snapshot(prompt.id, "production-ready")
"""

from agno.prompt_versioning.models import (
    PromptMetadata,
    PromptTemplate,
    PromptVersion,
    PromptDiff,
    PromptLineage,
)
from agno.prompt_versioning.mlflow_backend import MLflowPromptStore
from agno.prompt_versioning.manager import PromptManager

__all__ = [
    "PromptMetadata",
    "PromptTemplate",
    "PromptVersion",
    "PromptDiff",
    "PromptLineage",
    "MLflowPromptStore",
    "PromptManager",
]
