# Agent6 OS — Agentic Architecture

A production-grade agentic system built on four cognitive roles with typed boundaries:

```
Memory → Perception → Decision → Action
```

Built for EAG V3 Session 6. Each role has one responsibility, typed input, and typed output.

---

## Quick Start

### 1. Prerequisites

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` in the **Resubmission root** (where the MCP server lives):
```bash
cp .env.example ../.env
# Fill in your API keys (GEMINI_API_KEY, TAVILY_API_KEY, etc.)
```

### 3. Start the LLM Gateway V3

```bash
cd ../5e4a8833-292d-4ce5-be97-749c7656bdbf/llm_gatewayV3
python main.py
# Gateway runs at http://localhost:8101
# Agent will auto-start it if not running
```

### 4. Run

**Console query runner (recommended for assignment queries):**
```bash
cd agent6_project
python run_query.py          # shows interactive menu — pick A / B / C1 / C2 / D
python run_query.py A        # run a specific query directly
```
Full iteration trace is appended to `README.md` after each run.

**Streamlit UI:**
```bash
streamlit run ui.py
```

**Direct CLI:**
```bash
python agent6.py "your query here"
```

**Tests:**
```bash
pytest tests/ -v
```

---

## Assignment Queries

| Key | Query |
|-----|-------|
| A | Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory. |
| B | Find 3 family-friendly things to do in Tokyo this weekend. Check Saturday's weather forecast there and tell me which one is most appropriate. |
| C1 | My mom's birthday is 15 May 2026. Remember that and give me a calendar reminder for two weeks before and on the day. |
| C2 | When is mom's birthday? |
| D | Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on. |

Query files live in `queries/`. Run `python run_query.py` to choose and execute one.

---

## Architecture

### Cognitive Roles

| Role | File | LLM | Responsibility |
|------|------|-----|----------------|
| Memory | `memory.py` | Only for `remember()` | Keyword retrieval, persistence, outcome recording |
| Perception | `perception.py` | Gemini (explicit) | Goal decomposition, progress tracking, artifact attachment |
| Decision | `decision.py` | Auto-routed (groq → github → nvidia → openrouter → gemini) | Choose answer or single tool call |
| Action | `action.py` | None | Pure MCP dispatch, artifact offload |

### Typed Contracts (`schemas.py`)

- `MemoryItem` — persisted facts / preferences / tool outcomes / scratchpad
- `Artifact` — SHA-256 addressed binary storage
- `Goal` — bounded sub-goal with sticky-done semantics
- `Observation` — Perception output (ordered list of Goals)
- `ToolCall` — single tool invocation request
- `DecisionOutput` — answer XOR tool_call (never both)
- `AgentUpdate` — event emitted to UI / console in real time

### MCP Tools (9)

| Tool | Description |
|------|-------------|
| `web_search` | Tavily primary, DuckDuckGo fallback. Hard-capped at 5 results |
| `fetch_url` | Clean markdown via crawl4ai headless Chromium. Timeout: 60s |
| `get_time` | Current time in any IANA timezone |
| `currency_convert` | Live rates via frankfurter.dev |
| `read_file` | Read from sandbox/ |
| `list_dir` | List sandbox/ |
| `create_file` | Create file in sandbox/ |
| `update_file` | Overwrite file in sandbox/ |
| `edit_file` | Partial edit of file in sandbox/ |

### File Layout

```
agent6_project/
├── agent6.py          # Main orchestration loop (Memory→Perception→Decision→Action)
├── schemas.py         # All Pydantic v2 contracts
├── memory.py          # Persistent keyword memory (state/memory.json)
├── perception.py      # Gemini-powered goal decomposition & tracking
├── decision.py        # Next-action selection (answer XOR tool call)
├── action.py          # MCP tool dispatch + large-output artifact offload
├── artifacts.py       # SHA-256 content-addressed binary store
├── gateway.py         # LLM Gateway V3 client wrapper
├── mcp_client.py      # MCP stdio subprocess client
├── ui.py              # Streamlit UI with live event trace
├── run_query.py       # Console runner: pick A/B/C1/C2/D, appends trace to README
├── queries/
│   ├── A.txt          # Claude Shannon Wikipedia fetch
│   ├── B.txt          # Tokyo weekend activities + weather
│   ├── C1.txt         # Store mom's birthday in memory
│   ├── C2.txt         # Recall mom's birthday
│   └── D.txt          # Python asyncio best practices synthesis
├── prompts/
│   ├── perception.txt        # Gemini system prompt for goal decomposition
│   ├── decision.txt          # Decision system prompt
│   └── memory_classifier.txt # Memory classification prompt
├── state/
│   ├── memory.json    # Persistent memory store (auto-created)
│   └── artifacts/     # Binary artifact files (auto-created)
├── utils/
│   ├── logging_utils.py  # Per-run log files + structured logging
│   ├── token_utils.py    # Token counting
│   └── file_utils.py     # File I/O helpers
└── tests/             # 27 pytest tests (all pass)
    ├── test_memory.py
    ├── test_perception.py
    ├── test_decision.py
    ├── test_artifacts.py
    └── test_end_to_end.py
```

---

## Key Design Decisions

### Memory is keyword-only retrieval
`memory.read()` uses token overlap — no LLM, no embeddings. Fast and deterministic. LLM is used only in `remember()` to classify raw text into structured `MemoryItem`.

### Perception uses Gemini explicitly
Smaller models hallucinate unstable goal IDs across iterations. Gemini is forced via `provider="gemini"` with a fallback to auto-route if Gemini fails.

### Artifacts are separate from Memory
Memory stores only `artifact_id` handles. Raw bytes are never in `memory.json`. Decision receives bytes only when Perception explicitly sets `attach_artifact_id` on a Goal.

### Action rejects `art:` handles
Tool arguments containing `art:*` are rejected before dispatch — prevents hallucinated artifact IDs from leaking into tool calls.

### Large outputs auto-archived
Tool outputs > 4 KB are stored as binary artifacts (SHA-256 addressed). Only the descriptor enters history, keeping LLM context small.

### Decision uses direct provider routing
Decision bypasses the LLM Gateway's auto-router and tries providers directly in order: groq → github → nvidia → openrouter → gemini. This avoids routing classification overhead on every iteration.

---

## Fixes & Improvements

### Tool timeout protection
- **Problem:** `fetch_url` uses headless Chromium (crawl4ai) which could hang indefinitely on large pages like Wikipedia.
- **Fix:** `asyncio.wait_for(crawler.arun(url=url), timeout=60)` added inside `_crawl4ai_fetch()` in the MCP server.
- **Safety net:** `action.py` wraps every `session.call_tool()` in `asyncio.wait_for()` — 90s for `fetch_url`, 30s for all other tools. Timeout raises a `TimeoutError` caught by the agent loop.

### UI tool call display truncation
- **Problem:** Tool arguments in the Streamlit trace were truncated at 35 characters, making URLs like `https://en.wikipedia.org/wiki/Claude_Shannon` appear as `https://en.wikipedia.org/wiki/Claud`.
- **Fix:** Increased display limit to 120 characters in `ui.py`.

### Live progress logging
- **Problem:** Agent appeared frozen during long operations (gateway startup, Perception LLM call, Decision LLM call, tool execution) with no UI feedback.
- **Fix:** Added `emit("log", ...)` events at each silent stage:
  - Gateway: `✅ LLM Gateway already running.` or `⏳ Starting gateway…`
  - Perception: `🔍 Perception: decomposing goals via Gemini…`
  - Decision: `🧠 Decision: choosing next action for → <goal>`
  - Tool: `⏳ fetch_url: launching headless browser — this can take 30-90s…`
  - Missing artifact: surfaces as a yellow warning card in the UI

---

## Observability

Every event is emitted at `INFO` level to both the per-run log file (`logs/<timestamp>_<run_id>.log`) and the UI/console:

| Event | What it shows |
|-------|---------------|
| `iteration` | Iteration number |
| `mcp_ready` | Tool list |
| `memory_hits` | Retrieved memory items |
| `goals` | Goal list with ✅/○ status |
| `log` | Gateway status, Perception/Decision phase, tool wait hints |
| `tool_call` | Tool name + full arguments |
| `tool_result` | Descriptor + artifact ID if stored |
| `artifact_attached` | Artifact ID + size |
| `goal_answer` | Which goal was answered |
| `error` / `warning` | Layer + message in red/yellow |
| `final_answer` | Complete answer + log file path |

---

## Tests

```bash
pytest tests/ -v
# 27 passed
```

Covers: memory read/write/recall, artifact store, perception goal decomposition, decision output validation, end-to-end agent loop with mocked MCP.

---

## Run Results

---

### Query A — Artifact Attachment (Claude Shannon Wikipedia)

| | |
|---|---|
| **Run date** | 2026-05-26 21:53:38 |
| **Elapsed** | 205.0s |

**Query:** `Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory.`

#### Iteration 1 / 20
- Memory: 0 hits
- _🔍 Perception: decomposing goals via Gemini…_
- Goals: ○ Fetch Wikipedia page for Claude Shannon | ○ Extract birth date, death date, three key contributions
- _🧠 Decision: choosing next action → Fetch Wikipedia page_
- Tool call: `fetch_url(url=https://en.wikipedia.org/wiki/Claude_Shannon)`
- _⏳ fetch_url: launching headless browser…_
- ❌ **[action]** fetch_url timed out after 90s

#### Iteration 2 / 20
- Memory: 1 hit (prior failed outcome)
- _🔍 Perception: decomposing goals via Gemini…_
- Goals: ○ Fetch Wikipedia page | ○ Extract info
- Tool call: `fetch_url(url=https://en.wikipedia.org/wiki/Claude_Shannon)`
- Tool result: stored 262,224B → `art:81382a36db75…`

#### Iteration 3 / 20
- Memory: 2 hits
- Goals: ✅ Fetch Wikipedia page _(artifact attached)_ | ○ Extract birth date _(artifact attached)_
- Artifact attached: `81382a36db75…` (262,224 bytes)
- Answered: **Claude Shannon was born on April 30, 1916.**

#### Iteration 4 / 20
- Goals: ✅ Fetch | ✅ Birth date | ○ Death date _(artifact attached)_
- Answered: **Claude Shannon died on February 24, 2001.**

#### Iteration 5 / 20
- Goals: ✅ Fetch | ✅ Birth date | ✅ Death date | ○ Three key contributions _(artifact attached)_
- Answered: **1) Information entropy. 2) Mathematical theory of communication. 3) Introduction of the binary digit (bit).**

#### Iteration 6 / 20
- All goals ✅ — run complete.

**Final Answer:**

- **Birth date:** April 30, 1916
- **Death date:** February 24, 2001
- **Three key contributions:**
  1. Founded information theory — formulated entropy as a measure of uncertainty in a message.
  2. Developed the mathematical theory of communication — established fundamental limits on signal processing and data compression.
  3. Introduced the binary digit (bit) as the basic unit of information — laid the groundwork for digital circuit design and modern computing.

---

### Query B — Weather-aware Planning (Tokyo weekend activities)

| | |
|---|---|
| **Run date** | 2026-05-26 21:55:53 |
| **Elapsed** | 85.3s |

**Query:** `Find 3 family-friendly things to do in Tokyo this weekend. Check Saturday's weather forecast there and tell me which one is most appropriate.`

#### Iteration 1 / 20
- Memory: 0 hits
- Goals: ○ Find 3 family-friendly things to do in Tokyo | ○ Check Saturday weather | ○ Recommend most appropriate
- Tool call: `web_search(query=family-friendly activities Tokyo weekend, max_results=5)`
- Tool result: stored 10,647B → `art:369c08e69520…`

#### Iteration 2 / 20
- Goals: ✅ Find activities _(artifact attached)_ | ○ Check Saturday weather | ○ Recommend
- Tool call: `web_search(query=Tokyo weather Saturday, max_results=5)`
- Tool result: stored 10,210B → `art:d68f7235c149…`

#### Iteration 3 / 20
- Goals: ✅ Find activities | ✅ Check Saturday weather _(artifact attached)_ | ○ Recommend _(artifact attached)_
- Artifact attached: `369c08e69520…` (10,647 bytes)
- Answered: **Based on mild, partly cloudy Saturday weather (~22°C) → Ueno Park is most appropriate.**

#### Iteration 4 / 20
- All goals ✅ — run complete.

**Final Answer:**

Three family-friendly options in Tokyo this weekend:
1. **Ueno Park** — free, spacious outdoor park with zoo and museums
2. **teamLab Planets** — immersive indoor digital art museum
3. **Odaiba** — waterfront shopping and kid-friendly attractions

**Most appropriate for Saturday** (mild, partly cloudy, ~22°C): **Ueno Park** — outdoor conditions are ideal.

---

### Query C1 — Persistent Memory: Store mom's birthday (Run 1)

| | |
|---|---|
| **Run date** | 2026-05-26 21:57:39 |
| **Elapsed** | 76.0s |

**Query:** `My mom's birthday is 15 May 2026. Remember that and give me a calendar reminder for two weeks before and on the day.`

#### Iteration 1 / 20
- Proactive memory triggered — preference stored: `[preference]` Mom's birthday is May 15, 2026.
- Memory: 1 hit (just stored)
- Goals: ○ Create reminder for 2026-05-01 (two weeks before) | ○ Create reminder for 2026-05-15 (on the day)
- Tool call: `create_file(path=mom_birthday_reminder_2026-05-01.txt, content=Reminder: Mom's birthday on 2026-05-15. Alert: 2026-05-01.)`
- Tool result: `{"ok": true, "path": "mom_birthday_reminder_2026-05-01.txt"}`

#### Iteration 2 / 20
- Goals: ✅ Reminder for 2026-05-01 | ○ Reminder for 2026-05-15
- Tool call: `create_file(path=mom_birthday_reminder_2026-05-15.txt, content=Reminder: Today is Mom's birthday! May 15, 2026.)`
- Tool result: `{"ok": true, "path": "mom_birthday_reminder_2026-05-15.txt"}`

#### Iteration 3 / 20
- All goals ✅ — run complete.

**Final Answer:**

Mom's birthday (May 15, 2026) stored in persistent memory.

Calendar reminders created:
- `mom_birthday_reminder_2026-05-01.txt` — alert on **May 1, 2026** (two weeks before)
- `mom_birthday_reminder_2026-05-15.txt` — alert on **May 15, 2026** (the day)

---

### Query C2 — Persistent Memory: Recall mom's birthday (Run 2)

| | |
|---|---|
| **Run date** | 2026-05-26 21:58:23 |
| **Elapsed** | 28.9s |

**Query:** `When is mom's birthday?`

#### Iteration 1 / 20
- Memory: 2 hits — `[preference]` mom's birthday is May 15, 2026 (stored in C1)
- Goals: ○ Answer when mom's birthday is from memory
- _🧠 Decision: answer directly from memory — no tool call needed_
- Answered: **May 15, 2026**

#### Iteration 2 / 20
- All goals ✅ — run complete.

**Final Answer:**

Mom's birthday is **May 15, 2026**.

_(Retrieved from persistent memory — zero tool calls needed.)_

---

### Query D — Multi-source Synthesis (Python asyncio best practices)

| | |
|---|---|
| **Run date** | 2026-05-26 21:59:15 |
| **Elapsed** | 39.3s |

**Query:** `Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on.`

#### Iteration 1 / 20
- Memory: 0 hits
- Goals: ○ Search and retrieve top 3 results | ○ Synthesize agreed advice
- Tool call: `web_search(query=Python asyncio best practices, max_results=3)`
- Tool result: stored 10,487B → `art:3ea78480993c…`

#### Iteration 2 / 20
- Goals: ✅ Search results _(artifact attached)_ | ○ Synthesize _(artifact attached)_
- Artifact attached: `3ea78480993c…` (10,487 bytes)
- Answered: synthesized agreed advice from top 3 results.

#### Iteration 3 / 20
- All goals ✅ — run complete.

**Final Answer:**

Advice agreed on across the top 3 results for Python asyncio best practices:

1. Use `asyncio.sleep()` instead of `time.sleep()` — never block the event loop inside async functions.
2. Use `asyncio.create_task()` to run independent coroutines concurrently instead of awaiting them sequentially.
3. Use `asyncio.run()` as the single entry point to start asyncio programs.
4. Run blocking code in a thread pool via `loop.run_in_executor()` to avoid stalling the event loop.
5. Handle `asyncio.CancelledError` gracefully — clean up resources before re-raising.
6. Always await coroutines — an unawaited coroutine silently does nothing.

