"""
Prompt Versioning Test Suite

Test Organization:
==================

tests/
├── conftest.py                 # Shared fixtures
├── unit/                       # Isolated component tests
│   ├── test_template.py        # PromptTemplate logic
│   ├── test_models.py          # Pydantic models
│   └── test_diff.py            # Diff computation
├── integration/                # Component interaction tests
│   ├── test_mlflow_backend.py  # MLflow storage operations
│   └── test_manager.py         # PromptManager workflows
└── e2e/                        # Full scenario tests
    ├── test_workflows.py       # Complete user workflows
    └── test_cli.py             # CLI command tests

Test Levels:
============

1. UNIT TESTS (test_unit_*.py)
   - No external dependencies
   - Test single functions/methods in isolation
   - Mock all I/O
   - Fast execution

2. INTEGRATION TESTS (test_integration_*.py)
   - Test component interactions
   - Use real MLflow with temp directories
   - Test data persistence and retrieval
   - Medium execution time

3. END-TO-END TESTS (test_e2e_*.py)
   - Test complete user scenarios
   - No mocking
   - Verify full workflows
   - Slower execution

Core Interactions (Atomic):
===========================
- Template variable extraction
- Template rendering (full/partial)
- Content hash computation
- Model serialization/deserialization
- MLflow experiment CRUD
- MLflow run CRUD
- Artifact read/write

Core Patterns (Composite):
==========================
- Create → Edit chain
- Create → Snapshot
- Create → Fork → Edit
- Search by tags/status/author
- Lineage traversal
- Version comparison

Core Logic (Business Rules):
============================
- Version numbers increment monotonically
- Snapshots are immutable (status=SNAPSHOT)
- Forks start at v1 with forked_from set
- Parent IDs form valid chains
- Content hash matches content
- Names follow validation rules
- Duplicate snapshot names rejected
- Duplicate prompt names rejected (for fork)

Run Tests:
==========
    pytest tests/ -v                    # All tests
    pytest tests/unit/ -v               # Unit only
    pytest tests/integration/ -v        # Integration only
    pytest tests/e2e/ -v                # E2E only
    pytest tests/ -v -k "template"      # By keyword
    pytest tests/ -v --cov              # With coverage
"""
