"""
Agent6 OS — Streamlit UI
Includes: live agent trace · memory browser · artifact viewer · state cleaner · log viewer
"""
from __future__ import annotations

import asyncio
import queue
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

# ── Page configuration ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agent6 OS",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Agent6 OS — EAG V3 Agentic Architecture"},
)

# ── CSS theme ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.event-card {
    border-radius: 8px; padding: 10px 14px; margin: 4px 0;
    font-size: 14px; border-left: 4px solid;
}
.ev-iteration  { border-color: #6366f1; background: #f5f3ff; color: #4338ca; }
.ev-memory     { border-color: #3b82f6; background: #eff6ff; color: #1d4ed8; }
.ev-goals      { border-color: #10b981; background: #f0fdf4; color: #065f46; }
.ev-tool-call  { border-color: #f59e0b; background: #fffbeb; color: #92400e; }
.ev-tool-result{ border-color: #8b5cf6; background: #faf5ff; color: #5b21b6; }
.ev-answer     { border-color: #14b8a6; background: #f0fdfa; color: #0f766e; }
.ev-error      { border-color: #ef4444; background: #fef2f2; color: #991b1b; }
.ev-log        { border-color: #94a3b8; background: #f8fafc; color: #475569; }

.final-answer {
    background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
    border: 2px solid #10b981; border-radius: 12px;
    padding: 20px 24px; font-size: 15px; line-height: 1.7;
}
.mem-item {
    border-radius: 6px; padding: 8px 12px; margin: 3px 0;
    font-size: 13px; background: #f8fafc; border-left: 3px solid #3b82f6;
}
.stat-box {
    text-align: center; padding: 10px; background: #f8fafc;
    border-radius: 8px; border: 1px solid #e2e8f0;
}
.stat-num { font-size: 22px; font-weight: 700; color: #1e293b; }
.stat-lbl { font-size: 11px; color: #64748b; margin-top: 2px; }
.danger-zone {
    background: #fef2f2; border: 1px solid #fca5a5;
    border-radius: 8px; padding: 12px; margin: 8px 0;
}
.log-entry { font-family: monospace; font-size: 12px; color: #374151; }
</style>
""", unsafe_allow_html=True)

_PROJECT_DIR = Path(__file__).parent
_STATE_DIR   = _PROJECT_DIR / "state"
_LOGS_DIR    = _PROJECT_DIR / "logs"
_LOGS_DIR.mkdir(exist_ok=True)

MAX_ITERS = 20


# ── Session state defaults ───────────────────────────────────────────────────
def _init_state():
    for k, v in {
        "history": [], "runs": [], "running": False,
        "current_updates": [], "current_answer": "",
        "current_log_file": "", "run_count": 0,
        "confirm_clean": False,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Lazy module loader ───────────────────────────────────────────────────────
@st.cache_resource
def _load_modules():
    import gateway  # triggers .env load + sys.path setup
    import memory as mem_module
    import artifacts as art_module
    import agent6
    return agent6, mem_module, art_module


# ── State management helpers ─────────────────────────────────────────────────
def _clean_state(mem_module):
    """Delete all state: memory + artifacts. Keeps logs."""
    mem_module.clear()
    art_dir = _STATE_DIR / "artifacts"
    if art_dir.exists():
        for f in art_dir.iterdir():
            try:
                f.unlink()
            except Exception:
                pass
    (_STATE_DIR / "memory.json").write_text("[]", encoding="utf-8")


def _count_artifacts() -> int:
    art_dir = _STATE_DIR / "artifacts"
    return len(list(art_dir.glob("*.bin"))) if art_dir.exists() else 0


def _list_log_files() -> list[Path]:
    return sorted(_LOGS_DIR.glob("*.log"), reverse=True)


def _clean_logs():
    for f in _LOGS_DIR.glob("*.log"):
        try:
            f.unlink()
        except Exception:
            pass


# ── Sidebar ─────────────────────────────────────────────────────────────────
def _render_sidebar(mem_module, art_module):
    with st.sidebar:
        st.markdown("## 🧠 Agent6 OS")
        st.caption("EAG V3 · Session 6 · Agentic Architecture")
        st.divider()

        # Quick stats row
        all_mem  = mem_module.get_all()
        n_art    = _count_artifacts()
        n_logs   = len(_list_log_files())

        c1, c2, c3 = st.columns(3)
        for col, num, lbl in [(c1, len(all_mem), "Memories"),
                              (c2, n_art, "Artifacts"),
                              (c3, n_logs, "Logs")]:
            with col:
                st.markdown(
                    f'<div class="stat-box"><div class="stat-num">{num}</div>'
                    f'<div class="stat-lbl">{lbl}</div></div>',
                    unsafe_allow_html=True,
                )

        st.divider()

        # ── Memory browser ────────────────────────────────────────────────
        with st.expander("📚 Memory Browser", expanded=False):
            if not all_mem:
                st.caption("No memories stored yet.")
            else:
                kind_filter = st.selectbox(
                    "Filter", ["all", "fact", "preference", "tool_outcome", "scratchpad"],
                    key="mem_filter",
                )
                shown = all_mem if kind_filter == "all" else [m for m in all_mem if m.kind == kind_filter]
                for item in shown[:20]:
                    badge = {"fact": "🔵", "preference": "🟣",
                             "tool_outcome": "🟡", "scratchpad": "⚪"}.get(item.kind, "⚪")
                    st.markdown(
                        f'<div class="mem-item">{badge} <b>{item.descriptor[:65]}</b>'
                        f'<br><small style="color:#94a3b8">{item.kind} · '
                        f'{item.created_at.strftime("%m/%d %H:%M")}</small></div>',
                        unsafe_allow_html=True,
                    )
                if len(shown) > 20:
                    st.caption(f"Showing 20 of {len(shown)}.")

        # ── Artifact browser ──────────────────────────────────────────────
        with st.expander("📦 Artifacts", expanded=False):
            all_art = art_module.list_all()
            if not all_art:
                st.caption("No artifacts stored yet.")
            else:
                for art in all_art[:8]:
                    st.markdown(
                        f"**{art.descriptor[:50]}**  \n"
                        f"`art:{art.id[:12]}` · {art.size_bytes:,}B",
                    )
                    if st.button(f"📄 View {art.id[:8]}", key=f"v_{art.id[:8]}"):
                        try:
                            raw = art_module.get_bytes(art.id)
                            st.text_area("Content", raw.decode("utf-8", errors="replace"), height=180)
                        except Exception as e:
                            st.error(str(e))

        # ── Log viewer ────────────────────────────────────────────────────
        with st.expander("📋 Run Logs", expanded=False):
            log_files = _list_log_files()
            if not log_files:
                st.caption("No log files yet.")
            else:
                selected_log = st.selectbox(
                    "Select log",
                    [f.name for f in log_files],
                    key="log_sel",
                )
                if selected_log:
                    log_path = _LOGS_DIR / selected_log
                    try:
                        content = log_path.read_text(encoding="utf-8", errors="replace")
                        st.text_area("Log content", content, height=250, key="log_content")
                    except Exception as e:
                        st.error(str(e))
                if st.button("🗑 Delete all logs", key="del_logs"):
                    _clean_logs()
                    st.success("Logs deleted.")
                    st.rerun()

        # ── Run history ───────────────────────────────────────────────────
        with st.expander("🕒 Run History", expanded=False):
            if not st.session_state.runs:
                st.caption("No completed runs yet.")
            else:
                for run in reversed(st.session_state.runs[-10:]):
                    st.markdown(f"**{run.get('ts','')}** — {run.get('query','')[:50]}")

        st.divider()

        # ── Clean State ───────────────────────────────────────────────────
        st.markdown("#### 🧹 State Management")
        st.markdown(
            '<div class="danger-zone">'
            '<b>Clean State</b> — resets memory and artifacts between assignment attempts.<br>'
            '<small>Logs are kept separately and can be cleared from the Logs panel above.</small>'
            '</div>',
            unsafe_allow_html=True,
        )

        if not st.session_state.confirm_clean:
            if st.button("🗑️ Clean State", use_container_width=True, type="secondary"):
                st.session_state.confirm_clean = True
                st.rerun()
        else:
            st.warning(
                f"This will delete **{len(all_mem)} memories** and **{n_art} artifacts**. "
                "Continue?"
            )
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("✅ Yes, clean", use_container_width=True, type="primary"):
                    _clean_state(mem_module)
                    st.session_state.confirm_clean = False
                    st.session_state.history = []
                    st.session_state.current_updates = []
                    st.session_state.current_answer = ""
                    st.success("State cleaned — memory and artifacts reset.")
                    st.rerun()
            with cc2:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.confirm_clean = False
                    st.rerun()

        st.divider()
        if st.button("⟳ Reset conversation", use_container_width=True):
            st.session_state.history = []
            st.session_state.current_updates = []
            st.session_state.current_answer = ""
            st.rerun()

        st.caption("Gateway: `http://localhost:8101`  |  Gemini model: `gemini-2.5-flash-lite`")


# ── Event rendering ──────────────────────────────────────────────────────────
def _render_event(update: dict):
    kind = update.get("kind", "")
    data = update.get("data", {})

    if kind == "iteration":
        st.markdown(
            f'<div class="event-card ev-iteration">🔄 <b>Iteration {data.get("number","?")} / {data.get("max", MAX_ITERS)}</b></div>',
            unsafe_allow_html=True,
        )

    elif kind == "memory_hits":
        count = data.get("count", 0)
        label = f"🧠 Memory: {count} item{'s' if count != 1 else ''} retrieved"
        if count > 0:
            with st.expander(label, expanded=False):
                for item in data.get("items", []):
                    badge = {"fact":"🔵","preference":"🟣","tool_outcome":"🟡","scratchpad":"⚪"}.get(item.get("kind",""), "⚪")
                    st.markdown(f"{badge} **[{item.get('kind')}]** {item.get('descriptor','')}")
        else:
            st.markdown(f'<div class="event-card ev-memory">{label}</div>', unsafe_allow_html=True)

    elif kind == "goals":
        goals = data.get("goals", [])
        done  = sum(1 for g in goals if g.get("done"))
        with st.expander(f"🎯 Goals: {done}/{len(goals)} complete", expanded=True):
            for g in goals:
                if g.get("done"):
                    st.markdown(f'<span style="color:#10b981;font-weight:600">✅ {g["text"]}</span>', unsafe_allow_html=True)
                else:
                    art = g.get("artifact")
                    suffix = f' <small style="color:#8b5cf6">📎 art:{art[:8]}</small>' if art else ""
                    st.markdown(f'<span style="color:#6b7280">○ {g["text"]}{suffix}</span>', unsafe_allow_html=True)

    elif kind == "tool_call":
        name = data.get("name", "?")
        args = data.get("arguments", {})
        args_str = "  ".join(f"`{k}`=`{str(v)[:120]}`" for k, v in list(args.items())[:3])
        st.markdown(
            f'<div class="event-card ev-tool-call">🔧 <b>Calling</b> <code>{name}</code>({args_str})</div>',
            unsafe_allow_html=True,
        )

    elif kind == "tool_result":
        desc   = data.get("descriptor", "")
        art_id = data.get("artifact_id")
        suffix = f' → <code>art:{art_id[:8]}</code>' if art_id else ""
        st.markdown(
            f'<div class="event-card ev-tool-result">📦 <b>Result:</b> {desc[:120]}{suffix}</div>',
            unsafe_allow_html=True,
        )

    elif kind == "artifact_attached":
        art_id = data.get("id", "")
        size   = data.get("size_bytes", 0)
        st.markdown(
            f'<div class="event-card ev-tool-result">📎 <b>Artifact attached:</b> '
            f'<code>art:{art_id[:8]}</code> ({size:,} bytes)</div>',
            unsafe_allow_html=True,
        )

    elif kind == "goal_answer":
        goal_text = data.get("goal_text", "")
        answer    = data.get("answer", "")
        with st.expander(f"✅ Answered: {goal_text[:60]}", expanded=True):
            st.markdown(answer)

    elif kind in ("error", "warning"):
        layer = data.get("layer", "")
        msg   = data.get("message", "")
        icon  = "⚠️" if kind == "warning" else "❌"
        st.markdown(
            f'<div class="event-card ev-error">{icon} <b>[{layer or kind}]</b> {msg[:200]}</div>',
            unsafe_allow_html=True,
        )

    elif kind == "mcp_ready":
        tools = data.get("tools", [])
        st.markdown(
            f'<div class="event-card ev-log">⚙️ MCP: {len(tools)} tools — '
            f'{", ".join(f"<code>{t}</code>" for t in tools[:7])}</div>',
            unsafe_allow_html=True,
        )

    elif kind == "memory_stored":
        st.markdown(
            f'<div class="event-card ev-log">💾 Memory [{data.get("kind")}]: {data.get("descriptor","")[:80]}</div>',
            unsafe_allow_html=True,
        )

    elif kind == "log":
        msg = data.get("message", "")
        icon = "⚠️" if msg.startswith("⚠") else ("⏳" if msg.startswith("⏳") else "ℹ️")
        css = "ev-error" if msg.startswith("⚠") else "ev-log"
        st.markdown(
            f'<div class="event-card {css}">{icon} {msg[:200]}</div>',
            unsafe_allow_html=True,
        )


# ── Agent runner (background thread) ─────────────────────────────────────────
def _run_agent_thread(query: str, history: list, update_q: queue.Queue):
    import agent6

    async def _inner():
        def on_update(u):
            update_q.put({"kind": u.kind, "data": u.data})

        try:
            answer, new_history = await agent6.run(
                query=query,
                history=list(history),
                on_update=on_update,
            )
            update_q.put({"kind": "__done__", "answer": answer, "history": new_history})
        except Exception as exc:
            update_q.put({"kind": "__error__", "error": str(exc)})

    # Use explicit loop management instead of asyncio.run() to avoid the anyio
    # cross-task cancel-scope RuntimeError that fires during shutdown when the
    # MCP stdio_client's cleanup runs in a different task than it was entered in.
    loop = asyncio.new_event_loop()

    def _suppress_anyio_shutdown(loop, context):
        """Silence the known anyio cancel-scope error during event-loop teardown."""
        exc = context.get("exception")
        msg = str(exc) if exc else context.get("message", "")
        if "cancel scope" in msg:
            return
        loop.default_exception_handler(context)

    loop.set_exception_handler(_suppress_anyio_shutdown)
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_inner())
    finally:
        # Cancel any lingering tasks before closing the loop
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


# ── Main UI ──────────────────────────────────────────────────────────────────
def main():
    from utils.logging_utils import setup_logging
    setup_logging()

    agent6_mod, mem_module, art_module = _load_modules()
    _render_sidebar(mem_module, art_module)

    # Header
    st.markdown("## 🧠 Agent6 OS")
    st.markdown(
        "_Memory · Perception (Gemini 2.5 Flash-Lite) · Decision · Action_",
        help="EAG V3 Session 6 — production-grade agentic architecture",
    )

    # ── Final Answer — shown ABOVE query input so it's always visible ─────────
    if st.session_state.current_answer:
        answer_text = st.session_state.current_answer
        is_error = answer_text.startswith("⚠️")
        label = "❌ Error" if is_error else "💡 Final Answer"
        st.markdown(f"### {label}")
        # Use native st.markdown so **bold**, newlines, etc. render correctly
        with st.container(border=True):
            st.markdown(answer_text)
        if st.session_state.current_log_file:
            log_name = Path(st.session_state.current_log_file).name
            st.caption(f"📋 Run log: `{log_name}` — view in **Run Logs** (sidebar)")
        st.divider()

    # ── Query input ───────────────────────────────────────────────────────────
    example_queries = [
        "What time is it in Tokyo right now?",
        "Fetch https://en.wikipedia.org/wiki/Claude_Shannon — birth date, death date, 3 key contributions",
        "Compare Claude, GPT-4, and Gemini for coding tasks",
        "Plan a weekend trip to Goa. Use weather as a constraint.",
        "I prefer vegetarian restaurants",
    ]

    col_input, col_btn = st.columns([5, 1])
    with col_input:
        query = st.text_area(
            "Query",
            placeholder="Ask anything — the agent decomposes it into goals and uses tools.",
            height=90,
            key="query_input",
            label_visibility="collapsed",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn  = st.button("▶ Run", type="primary", use_container_width=True,
                             disabled=st.session_state.running)
        clear_btn = st.button("⟳ New", use_container_width=True)

    # Example query buttons
    st.markdown("**Quick examples:**")
    ex_cols = st.columns(len(example_queries))
    for i, (col, ex) in enumerate(zip(ex_cols, example_queries)):
        with col:
            if st.button(f"#{i+1}", key=f"ex_{i}", help=ex, use_container_width=True):
                st.session_state["_pending_q"] = ex
                st.rerun()

    if "_pending_q" in st.session_state:
        query = st.session_state.pop("_pending_q")

    if clear_btn:
        st.session_state.history = []
        st.session_state.current_updates = []
        st.session_state.current_answer = ""
        st.session_state.current_log_file = ""
        st.rerun()

    st.divider()

    # ── Run the agent ─────────────────────────────────────────────────────────
    if run_btn and query.strip() and not st.session_state.running:
        st.session_state.running = True
        st.session_state.current_updates = []
        st.session_state.current_answer = ""
        st.session_state.current_log_file = ""
        st.session_state.run_count += 1

        update_q: queue.Queue = queue.Queue()
        t = threading.Thread(
            target=_run_agent_thread,
            args=(query.strip(), st.session_state.history, update_q),
            daemon=True,
        )
        t.start()

        updates: list[dict] = []
        had_error = False
        with st.status("🧠 Agent running…", expanded=True) as status:
            while t.is_alive() or not update_q.empty():
                try:
                    item = update_q.get(timeout=0.3)
                except queue.Empty:
                    continue

                if item["kind"] == "__done__":
                    st.session_state.current_answer = item["answer"]
                    st.session_state.history = item["history"]
                    break
                elif item["kind"] == "__error__":
                    had_error = True
                    err_msg = item["error"]
                    st.error(f"Agent error: {err_msg}")
                    # Persist the error so it's visible after st.rerun()
                    st.session_state.current_answer = f"⚠️ **Agent error**\n\n```\n{err_msg}\n```"
                    break
                else:
                    updates.append(item)
                    _render_event(item)
                    if item["kind"] == "final_answer":
                        st.session_state.current_log_file = item["data"].get("log_file", "")

            t.join(timeout=5)

            # If the thread died without sending __done__ or __error__
            if not st.session_state.current_answer:
                had_error = True
                st.session_state.current_answer = (
                    "⚠️ **Agent stopped unexpectedly.**\n\n"
                    "Check the **Run Logs** panel in the sidebar for details."
                )

            if had_error:
                status.update(label="❌ Error — see details below", state="error", expanded=True)
            else:
                status.update(label="✅ Complete", state="complete", expanded=False)

        st.session_state.current_updates = updates
        st.session_state.running = False

        st.session_state.runs.append({
            "query": query.strip(),
            "answer": st.session_state.current_answer,
            "ts": datetime.now().strftime("%H:%M"),
            "log_file": st.session_state.current_log_file,
        })
        st.rerun()

    # Agent trace
    if st.session_state.current_updates:
        with st.expander(
            "🔍 Agent Trace",
            expanded=not bool(st.session_state.current_answer),
        ):
            for update in st.session_state.current_updates:
                if update["kind"] not in ("final_answer",):
                    _render_event(update)

    # Conversation history
    if st.session_state.history:
        with st.expander(
            f"💬 Conversation History ({len(st.session_state.history)} turns)",
            expanded=False,
        ):
            for msg in st.session_state.history[-20:]:
                role    = msg.get("role", "?")
                content = str(msg.get("content", ""))[:400]
                icon    = "🧑" if role == "user" else "🤖"
                st.markdown(f"**{icon} {role.title()}:** {content}")


if __name__ == "__main__":
    main()
