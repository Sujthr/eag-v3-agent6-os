# Agent6 OS — Agentic Architecture

A production-grade agentic system built on four cognitive roles with typed boundaries:

```
Memory → Perception → Decision → Action
```

## Quick Start

### 1. Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# Start the LLM Gateway V3 (from its directory)
cd ../5e4a8833-292d-4ce5-be97-749c7656bdbf/llm_gatewayV3
python main.py
# Gateway runs at http://localhost:8101
```

### 2. Configure environment

Copy `.env.example` to `.env` in the **Resubmission root** (where the MCP server script lives):
```bash
cp .env.example ../.env
# Fill in your API keys
```

### 3. Run

**Streamlit UI (recommended):**
```bash
streamlit run ui.py
```

**CLI:**
```bash
python agent6.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date"
python agent6.py "Plan a weekend trip to Goa"
python agent6.py "What time is it in Tokyo?"
```

**Tests:**
```bash
pytest tests/ -v
```

---

## Architecture

### Cognitive Roles

| Role | File | LLM | Responsibility |
|------|------|-----|----------------|
| Memory | `memory.py` | Only for `remember()` | Keyword retrieval, persistence, outcome recording |
| Perception | `perception.py` | Gemini (explicit) | Goal decomposition, progress tracking, artifact attachment |
| Decision | `decision.py` | Auto-routed | Choose answer or single tool call |
| Action | `action.py` | None | Pure MCP dispatch, artifact offload |

### Typed Contracts (`schemas.py`)

- `MemoryItem` — persisted facts/preferences/outcomes
- `Artifact` — SHA-256 addressed binary storage
- `Goal` — bounded sub-goal with sticky-done semantics
- `Observation` — perception output (list of Goals)
- `ToolCall` — single tool invocation request
- `DecisionOutput` — answer XOR tool_call
- `AgentUpdate` — event emitted to UI

### File Layout

```
agent6_project/
├── agent6.py          # Main orchestration loop
├── schemas.py         # All Pydantic v2 contracts
├── memory.py          # Persistent memory (state/memory.json)
├── perception.py      # Gemini-powered goal orchestration
├── decision.py        # Next-action selection
├── action.py          # MCP tool dispatch + artifact offload
├── artifacts.py       # SHA-256 content-addressed store
├── gateway.py         # LLM Gateway V3 wrapper
├── mcp_client.py      # MCP stdio client
├── ui.py              # Streamlit UI
├── prompts/           # System prompts for each role
├── state/
│   ├── memory.json    # Persistent memory store
│   └── artifacts/     # Binary artifact files
├── utils/             # Logging, token counting, file I/O
└── tests/             # pytest test suite
```

---

## Key Design Decisions

### Memory is keyword-only retrieval
`memory.read()` uses token overlap — no LLM, no embeddings. Fast and deterministic.

### Perception uses Gemini explicitly
Smaller models hallucinate unstable goal IDs across iterations. Gemini preserves identity reliably.

### Artifacts are separate from Memory
Memory stores only `artifact_id` handles. Raw bytes are never in the memory JSON.
Decision receives bytes only when Perception explicitly attaches them via `attach_artifact_id`.

### Action rejects `art:` handles
Tool arguments containing `art:*` are rejected before dispatch — prevents hallucinated artifact IDs from leaking into tool calls.

### Large outputs auto-archived
Tool outputs > 4KB are stored as binary artifacts. Only the descriptor goes into history, keeping contexts small.

---

## Example Traces

### Query 1: Artifact Attachment
```
Query: Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me birth date, death date, and key contributions

Iteration 1:
  Memory: 0 hits
  Goals: [fetch Wikipedia page] [extract birth/death/contributions]
  Tool: fetch_url(url=https://en.wikipedia.org/wiki/Claude_Shannon)
  Result: [stored 85,432B as art:3f9a2c...]

Iteration 2:
  Goals: [fetch page ✓] [extract info — art:3f9a2c attached]
  Decision → answer (using artifact content)
  Answer: Born April 30, 1916 / Died February 24, 2001 / Contributions: information theory...
```

### Query 3: Persistent Memory
```
Run 1: "I prefer vegetarian restaurants"
  → Stored [preference]: user prefers vegetarian restaurants

Run 2: "Suggest dinner places nearby"
  Memory: 1 hit → [preference] user prefers vegetarian restaurants
  Decision: suggests vegetarian options
```

---

## Observability

Every event is logged at `INFO` level:
- Iteration number
- Memory hit count
- Goal list with status
- Tool name + arguments
- Artifact IDs
- Router decision (from gateway)
- Final answer

The Streamlit UI renders all events with color-coded cards in real time.
