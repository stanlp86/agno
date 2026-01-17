"""
Shared fixtures for prompt versioning tests.

Fixture Hierarchy:
==================

temp_dir (function)
    └── tracking_uri (function)
        └── mlflow_store (function)
            └── manager (function)

sample_prompts (module)
    ├── simple_prompt
    ├── complex_prompt
    └── multi_var_prompt
"""

import os
import tempfile
from typing import Dict, Generator

import pytest

from agno.prompt_versioning.models import (
    PromptMetadata,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
)
from agno.prompt_versioning.mlflow_backend import (
    MLflowPromptStore,
    generate_prompt_id,
)
from agno.prompt_versioning.manager import PromptManager


# =============================================================================
# DIRECTORY FIXTURES
# =============================================================================


@pytest.fixture(scope="function")
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory(prefix="prompt_test_") as tmpdir:
        yield tmpdir


@pytest.fixture(scope="function")
def tracking_uri(temp_dir: str) -> str:
    """Create MLflow tracking URI in temp directory."""
    return os.path.join(temp_dir, "mlruns")


# =============================================================================
# STORE AND MANAGER FIXTURES
# =============================================================================


@pytest.fixture(scope="function")
def mlflow_store(tracking_uri: str) -> MLflowPromptStore:
    """Create MLflowPromptStore with temp tracking URI."""
    return MLflowPromptStore(tracking_uri=tracking_uri)


@pytest.fixture(scope="function")
def manager(tracking_uri: str) -> PromptManager:
    """Create PromptManager with temp tracking URI."""
    return PromptManager(tracking_uri=tracking_uri)


# =============================================================================
# TEMPLATE FIXTURES
# =============================================================================


@pytest.fixture
def simple_template() -> PromptTemplate:
    """Simple template with one variable."""
    return PromptTemplate(content="Hello, {{name}}!")


@pytest.fixture
def complex_template() -> PromptTemplate:
    """Complex template with multiple variables."""
    return PromptTemplate(
        content="Dear {{title}} {{name}},\n\n"
        "Thank you for contacting {{company}}. "
        "Your request regarding {{topic}} has been received.\n\n"
        "Best regards,\n{{sender}}"
    )


@pytest.fixture
def no_var_template() -> PromptTemplate:
    """Template with no variables."""
    return PromptTemplate(content="This is a static prompt with no variables.")


# =============================================================================
# METADATA FIXTURES
# =============================================================================


@pytest.fixture
def basic_metadata() -> PromptMetadata:
    """Basic metadata for testing."""
    return PromptMetadata(
        author="test-author",
        description="Test prompt description",
        tags=["test", "unit"],
    )


@pytest.fixture
def full_metadata() -> PromptMetadata:
    """Complete metadata with all fields."""
    return PromptMetadata(
        author="ml-team",
        description="Production prompt for customer interactions",
        tags=["production", "customer", "greeting"],
        model_compatibility=["gpt-4", "claude-3", "llama-2"],
        use_case="Customer onboarding emails",
        custom={
            "department": "marketing",
            "approved_by": "jane@company.com",
            "version_notes": "Added personalization",
        },
    )


# =============================================================================
# PROMPT VERSION FIXTURES
# =============================================================================


@pytest.fixture
def sample_prompt_v1(simple_template: PromptTemplate, basic_metadata: PromptMetadata) -> PromptVersion:
    """Sample prompt version 1."""
    return PromptVersion(
        id=generate_prompt_id(),
        name="test_prompt",
        version=1,
        template=simple_template,
        status=PromptStatus.DRAFT,
        metadata=basic_metadata,
    )


@pytest.fixture
def sample_prompt_v2(sample_prompt_v1: PromptVersion) -> PromptVersion:
    """Sample prompt version 2 (edit of v1)."""
    return PromptVersion(
        id=generate_prompt_id(),
        name=sample_prompt_v1.name,
        version=2,
        template=PromptTemplate(content="Hi {{name}}, welcome!"),
        status=PromptStatus.DRAFT,
        metadata=sample_prompt_v1.metadata,
        parent_id=sample_prompt_v1.id,
    )


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_prompts() -> Dict[str, Dict]:
    """Collection of sample prompt data for testing."""
    return {
        "greeting": {
            "name": "greeting",
            "content": "Hello {{name}}, welcome to {{company}}!",
            "description": "Customer greeting prompt",
            "tags": ["greeting", "customer"],
        },
        "summarizer": {
            "name": "summarizer",
            "content": "Summarize the following text:\n{{text}}\n\nStyle: {{style}}",
            "description": "Text summarization prompt",
            "tags": ["nlp", "summarization"],
        },
        "translator": {
            "name": "translator",
            "content": "Translate to {{language}}:\n{{text}}",
            "description": "Translation prompt",
            "tags": ["nlp", "translation"],
        },
        "analyzer": {
            "name": "analyzer",
            "content": "Analyze the sentiment of:\n{{text}}\n\nProvide: {{output_format}}",
            "description": "Sentiment analysis prompt",
            "tags": ["nlp", "analysis", "sentiment"],
        },
    }


# =============================================================================
# HELPER FIXTURES
# =============================================================================


@pytest.fixture
def create_prompt(manager: PromptManager):
    """Factory fixture for creating prompts."""

    def _create(
        name: str = "test_prompt",
        content: str = "Test {{var}}",
        **kwargs,
    ) -> PromptVersion:
        return manager.create(name=name, content=content, **kwargs)

    return _create


@pytest.fixture
def create_prompt_chain(manager: PromptManager):
    """Factory fixture for creating prompt edit chains."""

    def _create(name: str, versions: int = 3) -> list[PromptVersion]:
        chain = []
        prompt = manager.create(name=name, content=f"{name} v1: {{{{var}}}}")
        chain.append(prompt)

        for i in range(2, versions + 1):
            prompt = manager.edit(prompt.id, content=f"{name} v{i}: {{{{var}}}}")
            chain.append(prompt)

        return chain

    return _create


# =============================================================================
# ASSERTION HELPERS
# =============================================================================


class PromptAssertions:
    """Helper class for common prompt assertions."""

    @staticmethod
    def assert_valid_id(prompt: PromptVersion):
        """Assert prompt has valid ID format."""
        assert prompt.id is not None
        assert prompt.id.startswith("prompt_")
        assert len(prompt.id) == 19  # "prompt_" + 12 hex chars

    @staticmethod
    def assert_valid_hash(prompt: PromptVersion):
        """Assert content hash is valid."""
        import hashlib

        expected = hashlib.sha256(prompt.content.encode()).hexdigest()[:16]
        assert prompt.content_hash == expected

    @staticmethod
    def assert_is_snapshot(prompt: PromptVersion, name: str):
        """Assert prompt is a valid snapshot."""
        assert prompt.status == PromptStatus.SNAPSHOT
        assert prompt.snapshot_name == name
        assert prompt.is_snapshot()

    @staticmethod
    def assert_is_fork(prompt: PromptVersion, source_id: str):
        """Assert prompt is a valid fork."""
        assert prompt.forked_from == source_id
        assert prompt.version == 1
        assert prompt.is_fork()
        assert "forked" in prompt.metadata.tags

    @staticmethod
    def assert_lineage_chain(prompts: list[PromptVersion]):
        """Assert prompts form valid parent chain."""
        for i in range(1, len(prompts)):
            assert prompts[i].parent_id == prompts[i - 1].id
            assert prompts[i].version == prompts[i - 1].version + 1


@pytest.fixture
def assertions() -> PromptAssertions:
    """Provide assertion helper."""
    return PromptAssertions()
