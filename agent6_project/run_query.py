"""
Agent6 OS — Console Query Runner

Usage:
    python run_query.py           # interactive menu
    python run_query.py A         # run query A directly
    python run_query.py B
    python run_query.py C1
    python run_query.py C2
    python run_query.py D

After each run the full iteration trace is appended to README.md.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

_DIR = Path(__file__).parent
sys.path.insert(0, str(_DIR))

_QUERIES: dict[str, tuple[str, Path]] = {
    "A":  ("Query A — Artifact Attachment (Claude Shannon Wikipedia)",
           _DIR / "queries" / "A.txt"),
    "B":  ("Query B — Planning (Weekend Trip to Goa)",
           _DIR / "queries" / "B.txt"),
    "C1": ("Query C1 — Persistent Memory: Store preference (Run 1)",
           _DIR / "queries" / "C1.txt"),
    "C2": ("Query C2 — Persistent Memory: Recall preference (Run 2)",
           _DIR / "queries" / "C2.txt"),
    "D":  ("Query D — Multi-source Synthesis (Claude vs GPT vs Gemini)",
           _DIR / "queries" / "D.txt"),
}

_README = _DIR / "README.md"


# ── Menu ─────────────────────────────────────────────────────────────────────

def _show_menu() -> None:
    print()
    print("=" * 65)
    print("  Agent6 OS — Assignment Query Runner")
    print("=" * 65)
    for key, (label, path) in _QUERIES.items():
        text = path.read_text(encoding="utf-8").strip()
        preview = text[:72] + ("…" if len(text) > 72 else "")
        print(f"  [{key:2s}]  {label}")
        print(f"         {preview}")
        print()
    print("=" * 65)


def _pick() -> tuple[str, str, str]:
    if len(sys.argv) > 1:
        key = sys.argv[1].upper()
    else:
        _show_menu()
        key = input("Enter query key (A / B / C1 / C2 / D): ").strip().upper()

    if key not in _QUERIES:
        print(f"Unknown key '{key}'. Valid: {', '.join(_QUERIES)}")
        sys.exit(1)

    label, path = _QUERIES[key]
    query = path.read_text(encoding="utf-8").strip()
    return key, label, query


# ── Agent runner ──────────────────────────────────────────────────────────────

async def _run_async(query: str) -> tuple[str, list[dict], float]:
    import agent6
    from utils.logging_utils import setup_logging
    setup_logging()

    events: list[dict] = []

    def on_update(u) -> None:
        kind, data = u.kind, u.data
        events.append({"kind": kind, "data": data})

        if kind == "iteration":
            print(f"\n{'─' * 55}")
            print(f"  Iteration {data.get('number')} / {data.get('max', 20)}")

        elif kind == "mcp_ready":
            tools = data.get("tools", [])
            print(f"  MCP: {len(tools)} tools ready — {', '.join(tools)}")

        elif kind == "memory_hits":
            count = data.get("count", 0)
            print(f"  Memory: {count} hit(s)")
            for item in data.get("items", []):
                print(f"    [{item.get('kind')}] {item.get('descriptor', '')[:70]}")

        elif kind == "goals":
            for g in data.get("goals", []):
                st = "[✓]" if g.get("done") else "[ ]"
                art = " (artifact attached)" if g.get("artifact") else ""
                print(f"  {st} {g.get('text','')[:80]}{art}")

        elif kind == "log":
            print(f"  {data.get('message','')}")

        elif kind == "tool_call":
            name = data.get("name", "?")
            args = data.get("arguments", {})
            args_str = ", ".join(f"{k}={str(v)[:80]}" for k, v in args.items())
            print(f"  → {name}({args_str})")

        elif kind == "tool_result":
            desc = str(data.get("descriptor", ""))
            art  = data.get("artifact_id")
            suffix = f"  [artifact: {art[:12]}…]" if art else ""
            print(f"  ← {desc[:120]}{suffix}")

        elif kind == "artifact_attached":
            art_id = data.get("id", "")
            size   = data.get("size_bytes", 0)
            print(f"  📎 Artifact {art_id[:12]}… attached ({size:,} bytes)")

        elif kind == "goal_answer":
            print(f"  ✓ Goal answered: {data.get('goal_text','')[:70]}")

        elif kind in ("error", "warning"):
            icon = "⚠" if kind == "warning" else "✗"
            print(f"  {icon} [{data.get('layer', kind)}]: {data.get('message','')[:120]}")

    t0 = datetime.now()
    answer, _ = await agent6.run(query, [], on_update=on_update)
    elapsed = (datetime.now() - t0).total_seconds()
    return answer, events, elapsed


# ── README formatter ──────────────────────────────────────────────────────────

def _format_section(key: str, label: str, query: str,
                    events: list[dict], answer: str, elapsed: float) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        "",
        "---",
        "",
        f"## Run Result: {label}",
        "",
        f"| | |",
        f"|---|---|",
        f"| **Run date** | {ts} |",
        f"| **Elapsed**  | {elapsed:.1f}s |",
        "",
        "**Query:**",
        "```",
        query,
        "```",
        "",
        "### Execution Trace",
        "",
    ]

    for ev in events:
        kind = ev.get("kind", "")
        data = ev.get("data", {})

        if kind == "iteration":
            n  = data.get("number", "?")
            mx = data.get("max", 20)
            lines.append(f"#### Iteration {n} / {mx}")
            lines.append("")

        elif kind == "mcp_ready":
            tools = data.get("tools", [])
            lines.append(f"- **MCP ready:** {', '.join(f'`{t}`' for t in tools)}")

        elif kind == "memory_hits":
            count = data.get("count", 0)
            lines.append(f"- **Memory:** {count} item(s) retrieved")
            for item in data.get("items", []):
                lines.append(f"  - `[{item.get('kind')}]` {item.get('descriptor','')}")

        elif kind == "goals":
            goals = data.get("goals", [])
            lines.append(f"- **Goals ({len(goals)}):**")
            for g in goals:
                status = "✅" if g.get("done") else "○"
                art = " _(artifact attached)_" if g.get("artifact") else ""
                lines.append(f"  - {status} {g.get('text','')}{art}")

        elif kind == "log":
            msg = data.get("message", "")
            lines.append(f"- _{msg}_")

        elif kind == "tool_call":
            name = data.get("name", "?")
            args = data.get("arguments", {})
            args_fmt = ", ".join(f'`{k}`=`{v}`' for k, v in args.items())
            lines.append(f"- **Tool call:** `{name}({args_fmt})`")

        elif kind == "tool_result":
            desc   = str(data.get("descriptor", ""))
            art_id = data.get("artifact_id")
            art_str = f" → `art:{art_id[:12]}…`" if art_id else ""
            lines.append(f"- **Tool result:** {desc[:300]}{art_str}")

        elif kind == "artifact_attached":
            art_id = data.get("id", "")
            size   = data.get("size_bytes", 0)
            lines.append(f"- **Artifact attached:** `{art_id[:12]}…` ({size:,} bytes)")

        elif kind == "goal_answer":
            goal_text = data.get("goal_text", "")
            ans       = data.get("answer", "")
            lines.append(f"- **Answered:** _{goal_text[:100]}_")
            # Indent the answer as a blockquote
            for ln in ans[:600].splitlines():
                lines.append(f"  > {ln}")

        elif kind in ("error", "warning"):
            layer = data.get("layer", kind)
            msg   = data.get("message", "")
            icon  = "⚠️" if kind == "warning" else "❌"
            lines.append(f"- {icon} **[{layer}]** {msg[:300]}")

    lines += [
        "",
        "### Final Answer",
        "",
        answer,
        "",
    ]
    return "\n".join(lines)


def _append_readme(section: str) -> None:
    current = _README.read_text(encoding="utf-8").rstrip()
    _README.write_text(current + "\n" + section + "\n", encoding="utf-8")
    print(f"\n✅ Full trace appended to {_README.name}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    key, label, query = _pick()

    print()
    print("=" * 65)
    print(f"  Running: {label}")
    print(f"  Query  : {query[:72]}{'…' if len(query) > 72 else ''}")
    print("=" * 65)

    answer, events, elapsed = asyncio.run(_run_async(query))

    print(f"\n{'=' * 65}")
    print("FINAL ANSWER")
    print("=" * 65)
    print(answer)
    print("=" * 65)
    print(f"Total time: {elapsed:.1f}s")

    section = _format_section(key, label, query, events, answer, elapsed)
    _append_readme(section)


if __name__ == "__main__":
    main()
