# Agno Knowledge Pipeline Architecture Review

> **Document Version**: 1.0
> **Date**: 2025-11-30
> **Reviewer**: Architecture Review
> **Scope**: `agno/knowledge/*` - Content Management Pipeline

---

## Executive Summary

This document provides a comprehensive architecture review of the **agno knowledge pipeline** (`libs/agno/agno/knowledge/`) and compares it to your current multi-tenant file ingestion system. The review focuses on:

1. **Concurrency behavior** under multiple simultaneous document submissions
2. **Idempotency** at each pipeline stage
3. **State management** patterns
4. **Race condition handling**
5. **Recommendations** for building a clean file ingestion pipeline

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Deep Dive](#2-component-deep-dive)
3. [Concurrency Analysis](#3-concurrency-analysis)
4. [Idempotency Analysis](#4-idempotency-analysis)
5. [Comparison with Your System](#5-comparison-with-your-system)
6. [Race Conditions & Edge Cases](#6-race-conditions--edge-cases)
7. [Performance Under Load](#7-performance-under-load)
8. [Recommendations](#8-recommendations)

---

## 1. Architecture Overview

### 1.1 High-Level Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                          AGNO KNOWLEDGE PIPELINE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌──────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────────────┐   │
│   │ Content      │    │   Reader    │    │  Chunking   │    │  Embedding           │   │
│   │ Sources      │───►│  Selection  │───►│  Strategy   │───►│  Generation          │   │
│   │              │    │             │    │             │    │                      │   │
│   │ - Path       │    │ - PDF       │    │ - Fixed     │    │ - OpenAI             │   │
│   │ - URL        │    │ - DOCX      │    │ - Recursive │    │ - Sentence Trans.    │   │
│   │ - S3/GCS     │    │ - CSV       │    │ - Semantic  │    │ - Cohere, etc.       │   │
│   │ - FileData   │    │ - Text      │    │ - Agentic   │    │                      │   │
│   │ - Topics     │    │ - Website   │    │ - Markdown  │    │                      │   │
│   └──────────────┘    └─────────────┘    └─────────────┘    └──────────────────────┘   │
│          │                   │                  │                      │               │
│          │                   │                  │                      │               │
│          ▼                   ▼                  ▼                      ▼               │
│   ┌──────────────────────────────────────────────────────────────────────────────┐    │
│   │                        Vector Database Insertion                              │    │
│   │                                                                               │    │
│   │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐   │    │
│   │   │PgVector │  │ Qdrant  │  │Pinecone │  │ Milvus  │  │ 15+ more VDBs   │   │    │
│   │   └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘   │    │
│   │                                                                               │    │
│   └──────────────────────────────────────────────────────────────────────────────┘    │
│          │                                                                             │
│          ▼                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────────────┐    │
│   │                     Contents Database (Metadata)                              │    │
│   │            KnowledgeRow: id, name, status, content_hash, etc.                │    │
│   └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Key Files Reference

| Component | File Path | Lines |
|-----------|-----------|-------|
| **Main Orchestrator** | `libs/agno/agno/knowledge/knowledge.py` | 1-1968 |
| **Content Model** | `libs/agno/agno/knowledge/content.py` | 1-75 |
| **Document Model** | `libs/agno/agno/knowledge/document/base.py` | 1-59 |
| **Reader Base** | `libs/agno/agno/knowledge/reader/base.py` | 1-92 |
| **Embedder Base** | `libs/agno/agno/knowledge/embedder/base.py` | 1-23 |
| **VectorDB Interface** | `libs/agno/agno/vectordb/base.py` | 1-130 |
| **PgVector Implementation** | `libs/agno/agno/vectordb/pgvector/pgvector.py` | 1-1405 |

---

## 2. Component Deep Dive

### 2.1 Content Object (`content.py:30-74`)

```python
@dataclass
class Content:
    id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[ContentStatus] = None  # PROCESSING | COMPLETED | FAILED
    content_hash: Optional[str] = None       # SHA256 for deduplication
    external_id: Optional[str] = None        # For external system linking
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    # ... additional fields
```

**State Machine:**
```
          ┌─────────────┐
          │   INITIAL   │  (status = None)
          └──────┬──────┘
                 │ add_content_async() called
                 ▼
          ┌─────────────┐
          │ PROCESSING  │  (set at _add_to_contents_db)
          └──────┬──────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
 ┌─────────────┐   ┌─────────────┐
 │  COMPLETED  │   │   FAILED    │
 └─────────────┘   └─────────────┘
```

### 2.2 Content Hash Generation (`knowledge.py:1018-1044`)

The content hash is generated deterministically based on the content source:

```python
def _build_content_hash(self, content: Content) -> str:
    if content.path:
        return hashlib.sha256(str(content.path).encode()).hexdigest()
    elif content.url:
        return hashlib.sha256(content.url.encode()).hexdigest()
    elif content.file_data and content.file_data.content:
        name = content.name or "content"
        return hashlib.sha256(name.encode()).hexdigest()
    elif content.topics:
        topic = content.topics[0]
        reader = type(content.reader).__name__
        return hashlib.sha256(f"{topic}-{reader}".encode()).hexdigest()
    else:
        # Fallback with random suffix (NOT IDEMPOTENT)
        fallback = content.name or content.id or ("unknown_content" + random_suffix)
        return hashlib.sha256(fallback.encode()).hexdigest()
```

**Critical Issue:** The fallback case uses random data, breaking idempotency.

### 2.3 Skip Logic (`knowledge.py:369-387`)

```python
def _should_skip(self, content_hash: str, skip_if_exists: bool) -> bool:
    if self.vector_db and self.vector_db.content_hash_exists(content_hash) and skip_if_exists:
        log_debug(f"Content already exists: {content_hash}, skipping...")
        return True
    return False
```

**Key Insight:** Skip logic checks vector DB, not contents DB. This is a single synchronous check without locking.

### 2.4 Document Model (`document/base.py:7-58`)

```python
@dataclass
class Document:
    content: str
    id: Optional[str] = None
    name: Optional[str] = None
    meta_data: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    usage: Optional[Dict[str, Any]] = None
    content_id: Optional[str] = None  # Links back to Content
```

The `Document` is the unit that flows through chunking and embedding. Each `Content` produces multiple `Document` objects after chunking.

### 2.5 Reader System (`reader/base.py`)

```python
@dataclass
class Reader:
    chunk: bool = True
    chunk_size: int = 5000
    chunking_strategy: Optional[ChunkingStrategy] = None

    def read(self, obj: Any, name: Optional[str] = None) -> List[Document]:
        raise NotImplementedError

    async def async_read(self, obj: Any, name: Optional[str] = None) -> List[Document]:
        raise NotImplementedError

    async def chunk_documents_async(self, documents: List[Document]) -> List[Document]:
        # Parallel chunking using asyncio.gather
        chunked_lists = await asyncio.gather(*[_chunk_document_async(doc) for doc in documents])
        return [chunk for sublist in chunked_lists for chunk in sublist]
```

### 2.6 Chunking Strategies (`chunking/`)

| Strategy | File | Key Behavior |
|----------|------|--------------|
| **FixedSizeChunking** | `fixed.py` | Character-based splitting, avoids word breaks |
| **RecursiveChunking** | `recursive.py` | Finds natural break points (`\n`, `.`) |
| **SemanticChunking** | `semantic.py` | Uses embeddings for semantic boundaries |
| **AgenticChunking** | `agentic.py` | LLM-determined break points |
| **MarkdownChunking** | `markdown.py` | Header-aware splitting |

### 2.7 Embedding Generation (`embedder/openai.py:143-195`)

```python
async def async_get_embeddings_batch_and_usage(
    self, texts: List[str]
) -> Tuple[List[List[float]], List[Optional[Dict]]]:
    for i in range(0, len(texts), self.batch_size):
        batch_texts = texts[i : i + self.batch_size]
        req = {"input": batch_texts, "model": self.id, ...}

        try:
            response = await self.aclient.embeddings.create(**req)
            batch_embeddings = [data.embedding for data in response.data]
            all_embeddings.extend(batch_embeddings)
        except Exception as e:
            # Fallback to individual calls
            for text in batch_texts:
                embedding, usage = await self.async_get_embedding_and_usage(text)
```

**Key Feature:** Batch embedding with automatic fallback to individual calls on failure.

### 2.8 Vector DB Insert/Upsert (`pgvector/pgvector.py:406-424`)

```python
def upsert(self, content_hash: str, documents: List[Document], ...) -> None:
    """
    Upsert by content hash.
    First delete all documents with the same content hash.
    Then upsert the new documents.
    """
    if self.content_hash_exists(content_hash):
        self._delete_by_content_hash(content_hash)  # DELETE then INSERT
    self._upsert(content_hash, documents, filters, batch_size)
```

**Critical Pattern:** Upsert is implemented as DELETE + INSERT, not atomic UPSERT.

---

## 3. Concurrency Analysis

### 3.1 Async Execution Model

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          ASYNC EXECUTION FLOW                                        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   User A                          User B                         User C             │
│      │                               │                              │               │
│      ▼                               ▼                              ▼               │
│  add_content_async()            add_content_async()           add_content_async()   │
│      │                               │                              │               │
│      │                               │                              │               │
│      │◄──────────────────────────────┴──────────────────────────────►              │
│      │                                                                              │
│      │              Shared Event Loop (asyncio)                                     │
│      │                                                                              │
│      ▼                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           CONTENTION POINTS                                  │   │
│  │                                                                              │   │
│  │  1. content_hash_exists() check    ← Check-then-act race condition          │   │
│  │  2. Vector DB session/connection   ← Connection pool contention             │   │
│  │  3. OpenAI API rate limits         ← Shared rate limit across all users     │   │
│  │  4. Contents DB upsert             ← Potential duplicate key errors         │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Race Condition: Duplicate Content Check (`knowledge.py:369-387`)

```
Time   User A                              User B
─────────────────────────────────────────────────────────────────
T1     _should_skip() → False
T2                                         _should_skip() → False
T3     Processing document...
T4                                         Processing same document...
T5     Vector DB insert (success)
T6                                         Vector DB insert (duplicate!)
```

**Problem:** The `content_hash_exists()` check is not atomic with the insert operation. Two concurrent requests with the same content hash will both pass the check.

**Agno's Mitigation:** Uses DELETE + INSERT pattern in upsert, which handles duplicates but may cause data loss/inconsistency during concurrent updates.

### 3.3 Race Condition: Upsert Pattern (`pgvector.py:406-424`)

```python
async def async_upsert(self, content_hash, documents, ...):
    if self.content_hash_exists(content_hash):   # T1: Check
        self._delete_by_content_hash(content_hash)  # T2: Delete
    await self._async_upsert(...)                # T3: Insert
```

**Race Scenario:**
```
Time   Process A                           Process B
─────────────────────────────────────────────────────────────────
T1     content_hash_exists() → True
T2     delete_by_content_hash()
T3                                         content_hash_exists() → False
T4     _async_upsert() (inserting...)
T5                                         _async_upsert() (inserting...)
T6     Commit
T7                                         Commit → Duplicate key error!
```

### 3.4 Connection Pool Behavior (`pgvector.py:149`)

```python
self.Session: scoped_session = scoped_session(sessionmaker(bind=self.db_engine))
```

**Analysis:**
- Uses SQLAlchemy's `scoped_session` which provides thread-local sessions
- In async context with `asyncio.to_thread()`, each thread gets its own session
- Connection pool size determines max concurrent DB operations
- Default pool size is typically 5-10 connections

### 3.5 Embedding API Contention

```python
# pgvector.py:510-554
async def _async_embed_documents(self, batch_docs: List[Document]) -> None:
    if self.embedder.enable_batch:
        embeddings, usages = await self.embedder.async_get_embeddings_batch_and_usage(doc_contents)
    else:
        embed_tasks = [doc.async_embed(embedder=self.embedder) for doc in batch_docs]
        await asyncio.gather(*embed_tasks, return_exceptions=True)
```

**Concurrent Load Impact:**
- Multiple users → Multiple concurrent embedding API calls
- OpenAI rate limits are shared across all concurrent operations
- Rate limit errors (429) will cause cascading failures
- Batch embedding helps but doesn't eliminate rate limit risk

---

## 4. Idempotency Analysis

### 4.1 Stage-by-Stage Idempotency Assessment

| Stage | Idempotent? | Explanation |
|-------|-------------|-------------|
| **Content Hash Generation** | Mostly | Deterministic for path/URL, but fallback uses random data |
| **Content Creation** | No | Always creates new record if not found |
| **Reader (File Read)** | Yes | Same input → Same output |
| **Chunking** | Yes | Deterministic chunking strategies |
| **Embedding Generation** | Mostly | OpenAI returns consistent embeddings for same input |
| **Vector DB Insert** | No | May create duplicates without `skip_if_exists` |
| **Vector DB Upsert** | Partial | DELETE + INSERT pattern has race conditions |
| **Contents DB Update** | Yes | Uses upsert pattern |

### 4.2 Idempotency Problems

#### Problem 1: Non-Deterministic Content Hash Fallback

```python
# knowledge.py:1036-1044
else:
    fallback = (
        content.name
        or content.id
        or ("unknown_content" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6)))
    )
    return hashlib.sha256(fallback.encode()).hexdigest()
```

**Impact:** Content without path/URL/topics will get different hashes on each submission.

#### Problem 2: Check-Then-Act Without Locking

```python
# knowledge.py:369-387
def _should_skip(self, content_hash: str, skip_if_exists: bool) -> bool:
    if self.vector_db.content_hash_exists(content_hash) and skip_if_exists:
        return True
    return False
```

**Impact:** Race window between check and insert allows duplicates.

#### Problem 3: Document ID Generation

```python
# pgvector.py:600-601 (async_upsert)
record_id = md5(cleaned_content.encode()).hexdigest()
```

**Analysis:** Uses MD5 of content for ID, which IS idempotent. Same content → same ID.

However:

```python
# pgvector.py:362-363 (async_insert)
record_id = doc.id or content_hash
```

**Issue:** Insert path uses document ID or content_hash, not content MD5.

---

## 5. Comparison with Your System

### 5.1 Architecture Comparison

| Aspect | Your System | Agno Pipeline |
|--------|-------------|---------------|
| **State Management** | Two separate tables (`file.status`, `source.embedding_status`) | Single status field on `Content` |
| **Processing Model** | Celery workers (distributed) | In-process async (single event loop) |
| **File Storage** | S3 + database reference | In-memory or temporary files |
| **Deduplication** | SHA256 file hash | SHA256 path/URL hash |
| **Queue** | Redis/Celery task queue | No queue (synchronous pipeline) |
| **Frontend Integration** | Two-step API (upload → create source) | Single API call |
| **Worker Isolation** | Separate processes | Shared process |

### 5.2 State Model Comparison

**Your System:**
```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          YOUR SYSTEM: TWO STATE MACHINES                             │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   FILE TABLE                              SOURCE TABLE                               │
│   ──────────                              ────────────                               │
│   status: enum                            embedding_status: enum                     │
│   - pending                               - NULL (no embeddings needed)              │
│   - processing                            - pending                                  │
│   - completed                             - processing                               │
│   - failed                                - completed                                │
│                                           - failed                                   │
│                                                                                      │
│   Tracks: S3 storage, download,           Tracks: chunking, vectorization,          │
│           text extraction                          DB insertion                      │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Agno System:**
```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          AGNO: SINGLE STATE MACHINE                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   CONTENT TABLE (KnowledgeRow)                                                       │
│   ────────────────────────────                                                       │
│   status: ContentStatus                                                              │
│   - PROCESSING  (entire pipeline running)                                           │
│   - COMPLETED   (all stages done)                                                   │
│   - FAILED      (any stage failed)                                                  │
│                                                                                      │
│   Tracks: Everything (read, chunk, embed, insert)                                   │
│                                                                                      │
│   Problem: No granular visibility into which stage failed                           │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Advantages of Your System

1. **Granular Status Tracking**: Separate `file.status` and `embedding_status` allows:
   - Retry embeddings without re-downloading files
   - Clear visibility into failure points
   - Independent status progression

2. **Distributed Processing**: Celery workers enable:
   - Horizontal scaling
   - Process isolation (one failure doesn't affect others)
   - Rate limit handling per worker

3. **Persistent Storage**: S3-based storage provides:
   - Durability
   - Resume capability
   - Audit trail

### 5.4 Advantages of Agno System

1. **Simplicity**: Single async call handles everything
2. **Pluggable Components**: Easy to swap readers, embedders, vector DBs
3. **Multiple Chunking Strategies**: Semantic, agentic, recursive, etc.
4. **In-Memory Processing**: Faster for small documents
5. **Batch Embedding**: Built-in batch API support

---

## 6. Race Conditions & Edge Cases

### 6.1 Identified Race Conditions

#### RC-1: Duplicate Content Submission

**Scenario:** Two users submit identical documents simultaneously.

```
Time   User A                              User B
─────────────────────────────────────────────────────────────────
T1     content_hash = SHA256(path)
T2                                         content_hash = SHA256(path) [same]
T3     _should_skip() → False
T4                                         _should_skip() → False
T5     Processing...
T6                                         Processing...
T7     Vector DB insert
T8                                         Vector DB insert
T9     Status = COMPLETED
T10                                        Status = COMPLETED (duplicate data!)
```

**Impact:** Duplicate embeddings in vector DB unless using upsert with `skip_if_exists=True`.

#### RC-2: Partial Failure Recovery

**Scenario:** Embedding succeeds but DB insert fails.

```python
# knowledge.py:952-988
async def _handle_vector_db_insert(self, content, read_documents, upsert):
    try:
        await self.vector_db.async_upsert(...)  # Success
    except Exception as e:
        content.status = ContentStatus.FAILED
        await self._aupdate_content(content)
        return  # Embeddings generated but not persisted
```

**Impact:** Wasted embedding API calls. No rollback mechanism.

#### RC-3: Status Update Race

**Scenario:** Contents DB update during concurrent processing.

```python
# knowledge.py:1217-1220
if isinstance(self.contents_db, AsyncBaseDb):
    await self.contents_db.upsert_knowledge_content(knowledge_row=content_row)
else:
    self.contents_db.upsert_knowledge_content(knowledge_row=content_row)
```

**Issue:** No optimistic locking. Concurrent updates may overwrite each other.

### 6.2 Edge Cases

| Edge Case | Agno Behavior | Recommendation |
|-----------|---------------|----------------|
| Empty document | Proceeds with empty content | Add validation |
| Very large document (>100MB) | Memory issues | Stream processing |
| Binary file without text | Empty embedding | Detect and skip |
| Network timeout during embedding | Cascading failure | Retry with backoff |
| Rate limit (429) | Exception propagates | Circuit breaker |
| Invalid file extension | Uses text reader | Better detection |

---

## 7. Performance Under Load

### 7.1 Concurrent User Simulation

**Scenario:** 10 users simultaneously submitting 5 documents each (50 documents total).

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    CONCURRENT LOAD ANALYSIS (50 DOCUMENTS)                           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   BOTTLENECK ANALYSIS:                                                               │
│                                                                                      │
│   1. EMBEDDING API (Primary Bottleneck)                                             │
│      - OpenAI rate limit: 3,500 RPM (text-embedding-3-small)                        │
│      - 50 docs × 10 chunks avg × 1 API call = 500 calls                            │
│      - With batch (100 texts/call): 5 API calls                                     │
│      - Concurrent users may hit rate limits                                         │
│                                                                                      │
│   2. DATABASE CONNECTIONS                                                            │
│      - Default pool: 5-10 connections                                               │
│      - 50 concurrent upserts may queue                                              │
│      - scoped_session prevents connection sharing                                   │
│                                                                                      │
│   3. MEMORY                                                                          │
│      - 50 documents in memory simultaneously                                        │
│      - 10 chunks × 1536 dims × 4 bytes = 60KB per document                         │
│      - Total: ~3MB for embeddings alone                                             │
│      - Document content adds more                                                   │
│                                                                                      │
│   4. CPU (Chunking)                                                                  │
│      - asyncio.gather() parallelizes chunking                                       │
│      - asyncio.to_thread() uses thread pool (default: min(32, CPU+4))              │
│      - Generally not a bottleneck                                                   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Estimated Throughput

| Component | Single User | 10 Concurrent Users | Limiting Factor |
|-----------|-------------|---------------------|-----------------|
| File Reading | 100 MB/s | 100 MB/s | Disk I/O |
| Chunking | 10 docs/s | 50 docs/s | CPU (parallelized) |
| Embedding | 3 docs/s | 3 docs/s* | API rate limit |
| Vector DB Insert | 100 docs/s | 50 docs/s | Connection pool |

*Embedding throughput doesn't scale linearly due to shared API rate limits.

### 7.3 Failure Modes Under Load

1. **Rate Limit Cascade**
   ```python
   # pgvector.py:536-545
   is_rate_limit = any(phrase in error_str for phrase in ["rate limit", "429"])
   if is_rate_limit:
       raise e  # Propagates failure, no retry
   ```

2. **Connection Pool Exhaustion**
   - SQLAlchemy will queue requests when pool exhausted
   - Requests may timeout waiting for connection

3. **Memory Pressure**
   - Large documents load entirely into memory
   - No streaming for document reading

---

## 8. Recommendations

### 8.1 For Building an Idempotent Pipeline

#### Recommendation 1: Content-Based Hashing

Replace path-based hashing with content-based hashing:

```python
def _build_content_hash(self, content: Content) -> str:
    """Generate deterministic hash from actual content."""
    if content.file_data and content.file_data.content:
        if isinstance(content.file_data.content, bytes):
            return hashlib.sha256(content.file_data.content).hexdigest()
        return hashlib.sha256(content.file_data.content.encode()).hexdigest()
    # ... rest unchanged
```

#### Recommendation 2: Atomic Upsert

Use database-level atomic upsert instead of DELETE + INSERT:

```python
# PostgreSQL example with ON CONFLICT
insert_stmt = postgresql.insert(self.table).values(batch_records)
upsert_stmt = insert_stmt.on_conflict_do_update(
    index_elements=["content_hash"],  # Use content_hash as unique constraint
    set_={...}
)
```

#### Recommendation 3: Distributed Locking for Critical Sections

```python
async def add_content_async(self, ...):
    content_hash = self._build_content_hash(content)

    # Acquire distributed lock (Redis/PostgreSQL advisory lock)
    async with self._acquire_lock(f"content:{content_hash}"):
        if await self._should_skip_async(content_hash, skip_if_exists):
            return
        # Process content...
```

#### Recommendation 4: Stage-Based Status Tracking (Like Your System)

```python
class ContentStatus(str, Enum):
    PENDING = "pending"
    READING = "reading"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INSERTING = "inserting"
    COMPLETED = "completed"
    FAILED = "failed"

class Content:
    status: ContentStatus
    stage_error: Optional[str]  # Which stage failed
    retry_count: int = 0
```

#### Recommendation 5: Retry with Exponential Backoff

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=60))
async def _embed_with_retry(self, documents: List[Document]):
    return await self.embedder.async_get_embeddings_batch_and_usage(...)
```

### 8.2 Hybrid Architecture Recommendation

Combine the best of both systems:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    RECOMMENDED HYBRID ARCHITECTURE                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   YOUR SYSTEM'S STRENGTHS:              AGNO'S STRENGTHS:                           │
│   ─────────────────────────             ────────────────────                        │
│   ✓ Celery for distribution             ✓ Pluggable readers                         │
│   ✓ S3 for persistence                  ✓ Multiple chunking strategies             │
│   ✓ Two-stage status tracking           ✓ Batch embedding                          │
│   ✓ Race condition handling             ✓ Multiple vector DB support               │
│                                                                                      │
│   RECOMMENDED:                                                                       │
│   ────────────                                                                       │
│                                                                                      │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│   │ API Layer   │    │ Task Queue  │    │ Workers     │    │ Storage     │         │
│   │ (FastAPI)   │───►│ (Celery)    │───►│ (Agno KB)   │───►│ (S3+PgVec)  │         │
│   └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                                      │                                     │
│         │                                      ▼                                     │
│         │                              ┌─────────────┐                              │
│         │                              │ Status DB   │                              │
│         └─────────────────────────────►│ (Two-stage) │                              │
│                                        └─────────────┘                              │
│                                                                                      │
│   Stage 1: File Processing (Your pattern)                                           │
│   ─────────────────────────────────────────                                         │
│   - S3 upload                                                                        │
│   - Text extraction (via Agno readers)                                              │
│   - Status: file.status                                                             │
│                                                                                      │
│   Stage 2: Embedding Generation (Agno pattern)                                      │
│   ───────────────────────────────────────────                                       │
│   - Chunking (Agno strategies)                                                      │
│   - Embedding (Agno embedders)                                                      │
│   - Vector DB insert (Agno VectorDB)                                                │
│   - Status: source.embedding_status                                                 │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Integration Pattern

```python
# Example: Using Agno as a library within your Celery worker

from agno.knowledge import Knowledge
from agno.knowledge.reader import ReaderFactory
from agno.vectordb.pgvector import PgVector

@celery_app.task(bind=True, max_retries=3)
def process_file_embeddings(self, file_id: str):
    """Stage 2: Generate embeddings using Agno."""
    try:
        # 1. Get file from your DB
        file_record = get_file_record(file_id)
        update_embedding_status(file_id, "processing")

        # 2. Download from S3
        content = download_from_s3(file_record.s3_key)

        # 3. Use Agno for reading + chunking + embedding
        knowledge = Knowledge(
            vector_db=PgVector(table_name="embeddings", db_url=DB_URL),
            readers={
                ".pdf": ReaderFactory.get_reader_for_extension(".pdf"),
                ".docx": ReaderFactory.get_reader_for_extension(".docx"),
            }
        )

        # 4. Add content (handles chunking + embedding + insert)
        await knowledge.add_content_async(
            path=temp_file_path,
            metadata={"file_id": file_id, "tenant_id": file_record.tenant_id},
            skip_if_exists=True,  # Idempotent
            upsert=True,
        )

        # 5. Update status
        update_embedding_status(file_id, "completed")

    except Exception as e:
        update_embedding_status(file_id, "failed", error=str(e))
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
```

---

## Summary

### Agno Knowledge Pipeline Strengths

1. **Comprehensive reader support** (15+ document types)
2. **Multiple chunking strategies** including semantic and agentic
3. **Pluggable vector database** support (18+ backends)
4. **Batch embedding** for efficiency
5. **Async-first design** for concurrent processing

### Agno Knowledge Pipeline Weaknesses

1. **No distributed processing** - single event loop
2. **Race conditions** in skip/upsert logic
3. **No granular status tracking** - single status field
4. **No persistent queue** - failures require restart
5. **Memory-bound** for large documents

### Your System Strengths to Preserve

1. **Two-stage status tracking** (file vs embedding)
2. **Celery for distributed processing**
3. **S3 for durable storage**
4. **Race condition handling** via source lookup

### Recommended Approach

1. **Use Agno as a library** within your existing Celery workers
2. **Keep your two-stage status model** for observability
3. **Leverage Agno's readers and embedders** for document processing
4. **Add distributed locking** for idempotent upserts
5. **Implement content-based hashing** instead of path-based

---

## References

- `libs/agno/agno/knowledge/knowledge.py` - Main orchestrator
- `libs/agno/agno/vectordb/pgvector/pgvector.py` - PgVector implementation
- `libs/agno/agno/knowledge/embedder/openai.py` - OpenAI embedder
- `libs/agno/agno/knowledge/reader/base.py` - Reader base class
- `libs/agno/agno/knowledge/chunking/` - Chunking strategies
