"""The agent loop: Claude + web search/fetch + a few client tools that collect structured rows."""
import json
import sys
from datetime import date

import anthropic

from .fetch import fetch_page
from .results import ResultSet

MODEL = "claude-opus-5-5"

SYSTEM = """You are a research-and-scrape agent. The user gives you a general direction \
(which kinds of sites/organizations to look at) and a question, and you produce a structured table.

Today's date is {today}. User location: {location}.

Method:
1. Plan briefly: what sources are likely authoritative (trade publications, associations, \
vendor price pages, event calendars, exhibitor lists)?
2. Search and fetch. Prefer primary sources (the event's own exhibitor list, the vendor's own \
price page) over aggregators. Use `fetch_page` for pages the web tools cannot read well \
(tables, listings). Follow pagination and "next" links when the data is a list.
3. Call `define_columns` ONCE, early, with the columns that answer the question \
(e.g. event, dates, city, distance_from_user, customer_attending). Then call `record_rows` \
repeatedly as you find data - do not hold everything until the end.
4. Every row needs `confidence` (confirmed | likely | unverified), `evidence` (the specific fact \
that justifies the row, e.g. "listed on 2026 exhibitor page" or "attended 2024 and 2025, \
2026 not yet announced") and `source_url`. Never invent values: leave a cell empty if unknown. \
"Likely" must be backed by stated evidence, not a guess.
5. Respect limits: if a site blocks you or requires login, skip it and say so in the summary. \
Don't try to circumvent paywalls or bot protection.
6. Stop when the question is answered reasonably completely or returns diminish. Then call \
`finish` with a short summary: what you covered, what you could not access, caveats.

Prices: record unit, pack size and currency explicitly in columns, and normalise to a per-unit \
price column when possible, keeping the original text too."""

TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 40},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 60},
    {
        "name": "fetch_page",
        "description": "Fetch a URL directly and return its text (tables as ' | ' rows, links "
                       "inline as <url>). Honours robots.txt. Use when web_fetch fails or you "
                       "need table/listing structure.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}},
                         "required": ["url"], "additionalProperties": False},
    },
    {
        "name": "define_columns",
        "description": "Define the spreadsheet columns. Call once, before record_rows. "
                       "confidence, evidence and source_url are added automatically.",
        "input_schema": {"type": "object",
                         "properties": {"columns": {"type": "array", "items": {"type": "string"}}},
                         "required": ["columns"], "additionalProperties": False},
    },
    {
        "name": "record_rows",
        "description": "Record result rows. Each row is an object keyed by column name and must "
                       "include confidence, evidence and source_url. Duplicates are skipped.",
        "input_schema": {"type": "object",
                         "properties": {"rows": {"type": "array", "items": {"type": "object"}}},
                         "required": ["rows"], "additionalProperties": False},
    },
    {
        "name": "finish",
        "description": "Call when done. Provide a summary of coverage, gaps and caveats.",
        "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}},
                         "required": ["summary"], "additionalProperties": False},
    },
]


def run(direction: str, question: str, location: str = "unspecified",
        max_turns: int = 60, effort: str = "high", verbose: bool = True) -> ResultSet:
    client = anthropic.Anthropic()
    rs = ResultSet()
    system = SYSTEM.format(today=date.today().isoformat(), location=location)
    messages = [{"role": "user",
                 "content": f"Direction: {direction}\n\nQuestion: {question}"}]
    done = False

    def log(msg: str) -> None:
        if verbose:
            print(msg, file=sys.stderr, flush=True)

    for turn in range(max_turns):
        with client.messages.stream(
            model=MODEL, max_tokens=32000, system=system, tools=TOOLS, messages=messages,
            thinking={"type": "adaptive"}, output_config={"effort": effort},
        ) as stream:
            resp = stream.get_final_message()
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "refusal":
            log("Model declined the request.")
            break
        for b in resp.content:
            if b.type == "server_tool_use":
                log(f"[{b.name}] {json.dumps(b.input)[:140]}")
        if resp.stop_reason == "pause_turn":  # server-side tool loop hit its cap; just continue
            continue
        if resp.stop_reason == "max_tokens":
            messages.append({"role": "user", "content": "Continue."})
            continue

        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            out, err = "", False
            try:
                if b.name == "fetch_page":
                    log(f"[fetch_page] {b.input['url']}")
                    out = fetch_page(b.input["url"])
                elif b.name == "define_columns":
                    out = rs.define_columns(b.input["columns"])
                elif b.name == "record_rows":
                    out = rs.add_rows(b.input["rows"])
                    log(f"[record_rows] {out}")
                elif b.name == "finish":
                    rs.notes = b.input["summary"]
                    done, out = True, "Saved."
                else:
                    out, err = f"unknown tool {b.name}", True
            except (KeyError, TypeError) as e:
                out, err = f"bad input: {e!r}", True
            results.append({"type": "tool_result", "tool_use_id": b.id,
                            "content": out, "is_error": err or out.startswith("ERROR")})
        if done or not results:
            if not done:
                # Model ended its turn without calling finish; keep its final text as notes.
                rs.notes = "\n".join(b.text for b in resp.content if b.type == "text")
            break
        messages.append({"role": "user", "content": results})
    else:
        rs.notes += "\n[stopped: max_turns reached]"
    return rs
