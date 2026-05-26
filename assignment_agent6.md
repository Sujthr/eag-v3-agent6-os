# Assignment — Build `agent6.py` (Agentic Architecture)

## Objective

Build a production-grade agentic system implementing the Session 6 architecture from EAG V3.

The system must decompose a monolithic agent loop into four cognitive roles:

1. Memory
2. Perception
3. Decision
4. Action

The implementation must use:
- Python 3.11+
- Asyncio
- Pydantic v2
- MCP tools
- LLM Gateway V3
- Persistent memory
- Artifact storage
- Typed contracts between all layers

The final architecture must resemble a modern agent operating system rather than a single-loop chatbot.

---

# Core Architectural Principle

A loop becomes an architecture when:

- every role has:
  - one responsibility
  - typed input
  - typed output

The architecture must support:
- iterative reasoning
- goal decomposition
- memory persistence
- artifact attachment
- structured outputs
- tool orchestration

---

# Required File Structure

```txt
project/
│
├── agent6.py
├── schemas.py
├── memory.py
├── perception.py
├── decision.py
├── action.py
├── artifacts.py
├── gateway.py
├── mcp_client.py
├── prompts/
│   ├── perception.txt
│   ├── decision.txt
│   └── memory_classifier.txt
│
├── state/
│   ├── memory.json
│   └── artifacts/
│
├── utils/
│   ├── token_utils.py
│   ├── logging_utils.py
│   └── file_utils.py
│
├── tests/
│   ├── test_memory.py
│   ├── test_perception.py
│   ├── test_decision.py
│   ├── test_artifacts.py
│   └── test_end_to_end.py
│
├── requirements.txt
└── README.md
```

---

# Required Cognitive Roles

# 1. MEMORY ROLE

## Responsibility

Stores:
- facts
- preferences
- tool outcomes
- scratchpad notes

Memory must persist across runs.

## Required Features

### MemoryItem Schema

```python
class MemoryItem(BaseModel):
    id: str
    kind: Literal[
        "fact",
        "preference",
        "tool_outcome",
        "scratchpad"
    ]

    keywords: list[str]
    descriptor: str
    value: dict
    artifact_id: str | None
    source: str
    run_id: str
    goal_id: str | None
    confidence: float
    created_at: datetime
```

## Required Methods

### 1. read()

Must:
- use keyword overlap search
- use lowercase token matching
- support top-k retrieval
- NOT call LLM

```python
read(
    query: str,
    history: list[dict],
    kinds: list[str] | None = None,
    top_k: int = 8
)
```

### 2. remember()

Must:
- classify raw user text into structured memory
- use LLM classification
- generate:
  - kind
  - keywords
  - descriptor
  - structured value

### 3. record_outcome()

Must:
- persist MCP tool outcomes
- store artifact references
- avoid LLM usage

# Persistence Requirements

Memory must persist inside:

```txt
state/memory.json
```

---

# 2. ARTIFACT STORE

## Responsibility

Store large payloads separately from memory.

Examples:
- fetched webpages
- markdown pages
- large tool outputs
- reports
- raw bytes

## Required Schema

```python
class Artifact(BaseModel):
    id: str
    content_type: str
    size_bytes: int
    source: str
    descriptor: str
```

## Required Methods

```python
put(blob: bytes, ...)
get_bytes(artifact_id: str)
get_meta(artifact_id: str)
exists(artifact_id: str)
```

## Storage Requirements

Artifacts must use:
- SHA256 content addressing
- deduplication
- metadata JSON
- binary storage

Store under:

```txt
state/artifacts/
```

## Critical Architectural Rule

Memory stores ONLY artifact handles.

Decision receives raw bytes ONLY when explicitly attached by Perception.

---

# 3. PERCEPTION ROLE

## Responsibility

Perception is the orchestrator.

It must:
- decompose queries into goals
- track progress across iterations
- decide artifact attachment
- preserve stable goal identity

## Required Schema

```python
class Goal(BaseModel):
    id: str
    text: str
    done: bool
    attach_artifact_id: str | None
```

```python
class Observation(BaseModel):
    goals: list[Goal]
```

## Required Method

```python
observe(
    query: str,
    hits: list[MemoryItem],
    history: list[dict],
    prior_goals: list[Goal],
    run_id: str,
) -> Observation
```

## Required Rules

### Goal decomposition

On first iteration:
- split query into bounded goals

### Sticky done

Once a goal becomes done:
- it must remain done forever

### Goal order preservation

Perception MUST:
- preserve order
- never reorder
- never delete goals
- never insert into middle

### Artifact attachment

Perception decides:
- which goal requires artifact bytes
- which artifact to attach

Decision must NEVER directly request artifacts.

## Provider Requirement

Perception must:
- use Gemini explicitly
- bypass auto router

Reason:
small models fail to preserve stable goal identity.

---

# 4. DECISION ROLE

## Responsibility

Choose the next action.

Returns either:
- final answer
OR
- single tool call

Never both.

## Required Schemas

```python
class ToolCall(BaseModel):
    name: str
    arguments: dict
```

```python
class DecisionOutput(BaseModel):
    answer: str | None
    tool_call: ToolCall | None
```

## Required Method

```python
next_step(
    goal,
    hits,
    attached,
    history,
    mcp_tools,
)
```

## Required Constraints

Decision must:
- choose exactly one action
- never emit multiple tool calls
- never narrate chain-of-thought
- avoid meta responses

## Artifact Rules

Decision must:
- treat `art:*` as internal handles
- NEVER pass artifact ids to tools
- use attached bytes from prompt context only

## Tool Selection

Use MCP tool calling.

Supported tools:

- web_search
- fetch_url
- get_time
- currency_convert
- read_file
- list_dir
- create_file
- update_file
- edit_file

---

# 5. ACTION ROLE

## Responsibility

Pure dispatch layer.

No LLM calls allowed.

## Required Method

```python
execute(
    session,
    tool_call
)
```

Returns:

```python
(descriptor, artifact_id_or_none)
```

## Required Behaviors

### Large outputs

If output > 4KB:
- store in artifact store
- return short descriptor

### Artifact safety

Reject:
- path values beginning with `art:`

Return clear error message.

### MCP dispatch

Must:
- await tool execution
- flatten content blocks
- support async execution

---

# AGENT LOOP REQUIREMENTS

Implement iterative orchestration loop.

Pseudo-flow:

```python
while not all_done:

    hits = memory.read(...)

    obs = perception.observe(...)

    goal = obs.next_unfinished()

    attached = artifact bytes if required

    out = decision.next_step(...)

    if answer:
        append history
        continue

    result = action.execute(...)

    memory.record_outcome(...)

    append history
```

---

# HARD REQUIREMENTS

## MUST USE

- Asyncio
- Pydantic v2
- MCP
- structured outputs
- typed boundaries
- persistent memory
- artifact storage

## MUST NOT

- use a monolithic agent loop
- merge roles together
- bypass schemas
- store large bytes inside memory
- let Decision directly access artifact store

---

# REQUIRED TEST QUERIES

## QUERY 1 — Artifact Attachment

```txt
Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me:
- birth date
- death date
- three key contributions
```

Must:
- fetch webpage
- store artifact
- attach artifact
- extract information

## QUERY 2 — Planning

```txt
Plan a weekend trip to Goa.
Use weather as a constraint.
```

Must:
- decompose goals
- use external tools
- synthesize result

## QUERY 3 — Persistent Memory

Run 1:

```txt
I prefer vegetarian restaurants.
```

Run 2:

```txt
Suggest dinner places nearby.
```

Must:
- remember preference
- reuse across runs

## QUERY 4 — Multi-source Synthesis

```txt
Compare Claude, GPT, and Gemini for coding tasks.
```

Must:
- gather multiple sources
- synthesize findings
- generate structured answer

---

# OBSERVABILITY REQUIREMENTS

System must log:

- iteration number
- memory hits
- goals
- selected tool
- artifact attachment
- router decision
- final answer

---

# ENGINEERING REQUIREMENTS

## Code Quality

Must include:
- type hints
- docstrings
- modularity
- separation of concerns

## Error Handling

Must handle:
- malformed tool outputs
- missing artifacts
- invalid tool calls
- LLM schema failures
- gateway timeouts

---

# PERFORMANCE REQUIREMENTS

- avoid unnecessary LLM calls
- use keyword memory retrieval
- attach artifacts only when required
- keep contexts small

---

# BONUS FEATURES (Optional)

- vector memory retrieval
- streaming responses
- parallel action execution
- DAG orchestration
- retry policies
- tracing dashboard
- telemetry
- caching

---

# DELIVERABLES

Claude must generate:

1. Full source code
2. requirements.txt
3. .env.example
4. README.md
5. runnable architecture
6. tests
7. example execution traces

---

# FINAL EXPECTATION

This is NOT a chatbot.

This is an agent operating system with:
- cognitive decomposition
- memory persistence
- typed orchestration
- tool execution
- iterative reasoning
- artifact-aware context management

The architecture quality matters more than superficial feature count.
