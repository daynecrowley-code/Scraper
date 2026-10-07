"""Polite page fetcher: honours robots.txt, rate-limits per domain, returns clean text."""
import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx2 as httpx
from bs4 import BeautifulSoup

USER_AGENT = "ResearchScraperAgent/0.1 (+personal research use)"
MIN_DELAY_S = 2.0
MAX_CHARS = 40_000

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}


def _allowed(url: str) -> bool:
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    if origin not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = httpx.get(f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT},
                          timeout=10, follow_redirects=True)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots[origin] = rp
        except httpx.HTTPError:
            _robots[origin] = None  # unreachable robots.txt -> treat as no rules
    rp = _robots[origin]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def html_to_text(html: str) -> str:
    """Flatten HTML to text, keeping table rows as ' | '-separated lines and links inline."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        t.decompose()
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label:
            a.replace_with(soup.new_string(f"{label} <{a['href']}>"))
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        tr.replace_with(soup.new_string(" | ".join(cells) + "\n"))
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def fetch_page(url: str) -> str:
    """Return page text (truncated), or an 'ERROR: ...' string the model can react to."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return "ERROR: only absolute http(s) URLs are supported"
    if not _allowed(url):
        return "ERROR: blocked by robots.txt; skip this site or find another source"
    wait = MIN_DELAY_S - (time.monotonic() - _last_hit.get(p.netloc, 0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[p.netloc] = time.monotonic()
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
    except httpx.HTTPError as e:
        return f"ERROR: {type(e).__name__}: {e}"
    if r.status_code >= 400:
        return f"ERROR: HTTP {r.status_code}"
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        return f"ERROR: unsupported content-type {ctype}"
    text = html_to_text(r.text)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n[truncated at {MAX_CHARS} chars]"
    return text
