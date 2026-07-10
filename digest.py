#!/usr/bin/env python3
"""daily-paper-digest — a 5-minute daily digest of trending AI papers.

Fetches trending papers (Hugging Face daily_papers API, arXiv Atom fallback,
bundled sample as last resort), then writes a plain-language Markdown digest.

Format is owned by this code. An LLM (optional, bring-your-own
ANTHROPIC_API_KEY) only fills the prose. With no key, the digest gracefully
degrades to each paper's own abstract plus metadata — still useful, no lock-in.

Usage:
    python3 digest.py [--date YYYY-MM-DD] [--top 5] [--out docs]

Public, vendor-neutral, local-first. MIT. Not affiliated with arXiv or
Hugging Face. AI-assisted summaries may err — verify against the source.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
SAMPLE_FIXTURE = REPO_ROOT / "sample" / "daily_papers_fixture.json"

HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
ARXIV_ATOM_URL = (
    "http://export.arxiv.org/api/query?"
    "search_query=cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.AI"
    "&sortBy=submittedDate&sortOrder=descending&max_results=25"
)
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
ANTHROPIC_VERSION = "2023-06-01"

HTTP_TIMEOUT = 20
ABSTRACT_TRUNCATE = 600  # chars, degraded mode


# --------------------------------------------------------------------------- #
# Fetching (defensive: every network path falls back, never raises to caller)
# --------------------------------------------------------------------------- #
def _http_get(url: str, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "daily-paper-digest/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def _normalize_hf(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize HF daily_papers objects into our internal shape.

    HF returns a list of objects; each has a nested `paper` dict. We read
    everything with .get() so a shape change degrades instead of crashing.
    """
    papers: list[dict[str, Any]] = []
    for entry in items or []:
        if not isinstance(entry, dict):
            continue
        paper = entry.get("paper") or entry  # tolerate flattened shape
        if not isinstance(paper, dict):
            continue
        arxiv_id = str(paper.get("id") or paper.get("arxivId") or "").strip()
        title = str(paper.get("title") or "").strip()
        if not title:
            continue
        summary = str(paper.get("summary") or paper.get("abstract") or "").strip()
        upvotes = paper.get("upvotes")
        try:
            upvotes = int(upvotes)
        except (TypeError, ValueError):
            upvotes = 0
        authors_raw = paper.get("authors") or []
        authors: list[str] = []
        for a in authors_raw:
            if isinstance(a, dict):
                name = str(a.get("name") or "").strip()
            else:
                name = str(a).strip()
            if name:
                authors.append(name)
        published = str(entry.get("publishedAt") or paper.get("publishedAt") or "").strip()
        papers.append(
            {
                "id": arxiv_id,
                "title": title,
                "summary": summary,
                "upvotes": upvotes,
                "authors": authors,
                "published": published,
            }
        )
    return papers


def _fetch_hf() -> list[dict[str, Any]]:
    raw = _http_get(HF_DAILY_PAPERS_URL)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("unexpected HF payload shape")
    papers = _normalize_hf(data)
    if not papers:
        raise ValueError("HF returned no usable papers")
    return papers


def _fetch_arxiv() -> list[dict[str, Any]]:
    """Fallback: parse arXiv Atom feed with stdlib XML (no upvote signal)."""
    import xml.etree.ElementTree as ET

    raw = _http_get(ARXIV_ATOM_URL)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    papers: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        published = (entry.findtext("a:published", default="", namespaces=ns) or "").strip()
        raw_id = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        arxiv_id = raw_id.rsplit("/abs/", 1)[-1] if "/abs/" in raw_id else raw_id
        authors = [
            (a.findtext("a:name", default="", namespaces=ns) or "").strip()
            for a in entry.findall("a:author", ns)
        ]
        authors = [a for a in authors if a]
        if not title:
            continue
        papers.append(
            {
                "id": arxiv_id,
                "title": " ".join(title.split()),
                "summary": " ".join(summary.split()),
                "upvotes": 0,  # arXiv has no upvote signal; order preserved by recency
                "authors": authors,
                "published": published,
            }
        )
    if not papers:
        raise ValueError("arXiv returned no usable papers")
    return papers


def _fetch_sample() -> list[dict[str, Any]]:
    data = json.loads(SAMPLE_FIXTURE.read_text(encoding="utf-8"))
    return _normalize_hf(data)


def fetch_papers(offline: bool = False) -> tuple[list[dict[str, Any]], str]:
    """Return (papers, source_label). Never raises; always yields something."""
    if not offline:
        for name, fn in (("Hugging Face daily_papers", _fetch_hf), ("arXiv Atom", _fetch_arxiv)):
            try:
                return fn(), name
            except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"[warn] {name} unavailable ({exc}); trying next source", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001 - stay resilient in CI/offline
                print(f"[warn] {name} failed unexpectedly ({exc}); trying next source", file=sys.stderr)
    try:
        return _fetch_sample(), "bundled sample (offline)"
    except Exception as exc:  # noqa: BLE001
        print(f"[error] sample fixture unreadable: {exc}", file=sys.stderr)
        return [], "none"


# --------------------------------------------------------------------------- #
# Optional LLM prose (bring-your-own key). Degrades cleanly to abstract.
# --------------------------------------------------------------------------- #
def _anthropic_prose(paper: dict[str, Any], api_key: str) -> dict[str, Any] | None:
    """Ask Anthropic for a 3-sentence 'why it matters' + 3 bullets. None on failure."""
    prompt = (
        "You are briefing a busy AI/ML engineer. Given a paper title and abstract, "
        "write plain-language output as strict JSON with two keys:\n"
        '  "why_it_matters": a 3-sentence plain-English explanation of why this '
        "matters to a practitioner (no hype, no jargon where avoidable),\n"
        '  "bullets": an array of exactly 3 short takeaway strings.\n'
        "Return ONLY the JSON object, no prose around it.\n\n"
        f"Title: {paper.get('title', '')}\n\n"
        f"Abstract: {paper.get('summary', '')}\n"
    )
    body = json.dumps(
        {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT * 3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[-1] if "\n" in text else text
        parsed = json.loads(text)
        why = str(parsed.get("why_it_matters", "")).strip()
        bullets = [str(b).strip() for b in (parsed.get("bullets") or []) if str(b).strip()]
        if not why or not bullets:
            return None
        return {"why_it_matters": why, "bullets": bullets[:3]}
    except Exception as exc:  # noqa: BLE001 - never let LLM failure break the digest
        print(f"[warn] Anthropic summarization failed ({exc}); degrading to abstract", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# Rendering — deterministic, code-owned template. Model only fills prose.
# --------------------------------------------------------------------------- #
def _arxiv_url(arxiv_id: str) -> str:
    aid = (arxiv_id or "").strip()
    if not aid:
        return ""
    return f"https://arxiv.org/abs/{aid}"


def _truncate(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + " …"


def render_digest(
    date_str: str, papers: list[dict[str, Any]], source_label: str, llm_enabled: bool
) -> str:
    lines: list[str] = []
    lines.append(f"# Daily Paper Digest — {date_str}")
    lines.append("")
    mode = "AI-assisted summaries" if llm_enabled else "metadata + abstract (no API key)"
    lines.append(
        f"> {len(papers)} trending AI/ML papers, ~5-minute read. "
        f"Source: {source_label}. Mode: {mode}."
    )
    lines.append(">")
    lines.append(
        "> AI-assisted summaries may contain errors — always verify against the "
        "linked source. Not affiliated with arXiv or Hugging Face."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    for idx, paper in enumerate(papers, start=1):
        title = paper.get("title", "Untitled")
        url = _arxiv_url(paper.get("id", ""))
        heading = f"## {idx}. {title}"
        lines.append(heading)
        lines.append("")

        meta_bits = []
        upvotes = paper.get("upvotes", 0)
        if upvotes:
            meta_bits.append(f"upvotes: {upvotes}")
        authors = paper.get("authors") or []
        if authors:
            shown = ", ".join(authors[:4])
            if len(authors) > 4:
                shown += " et al."
            meta_bits.append(f"authors: {shown}")
        if paper.get("id"):
            meta_bits.append(f"arXiv: {paper['id']}")
        if meta_bits:
            lines.append("**" + " · ".join(meta_bits) + "**")
            lines.append("")

        prose = paper.get("_prose")
        if prose:
            lines.append("**Why it matters**")
            lines.append("")
            lines.append(prose["why_it_matters"])
            lines.append("")
            lines.append("**Takeaways**")
            lines.append("")
            for bullet in prose["bullets"]:
                lines.append(f"- {bullet}")
            lines.append("")
        else:
            lines.append("**Abstract (excerpt)**")
            lines.append("")
            lines.append(_truncate(paper.get("summary", ""), ABSTRACT_TRUNCATE) or "_No abstract available._")
            lines.append("")

        if url:
            lines.append(f"[Read on arXiv]({url})")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(
        "_Generated by [daily-paper-digest](https://github.com/sylvanus4/daily-paper-digest) — content from the "
        "papers themselves, format owned by code. Summaries are AI-assisted and may err._"
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Index / README maintenance
# --------------------------------------------------------------------------- #
def _list_digest_dates(out_dir: Path) -> list[str]:
    dates: list[str] = []
    for p in out_dir.glob("*.md"):
        stem = p.stem
        try:
            _dt.date.fromisoformat(stem)
        except ValueError:
            continue
        dates.append(stem)
    return sorted(set(dates), reverse=True)


def write_index(out_dir: Path) -> None:
    dates = _list_digest_dates(out_dir)
    lines = ["# Daily Paper Digest", "", "A daily 5-minute digest of trending AI/ML papers.", ""]
    if dates:
        lines.append("## Archive")
        lines.append("")
        for d in dates:
            lines.append(f"- [{d}]({d}.md)")
        lines.append("")
        latest = dates[0]
        lines.append(f"Latest: **[{latest}]({latest}.md)**")
        lines.append("")
    else:
        lines.append("_No digests yet._")
        lines.append("")
    content = "\n".join(lines)
    (out_dir / "index.md").write_text(content, encoding="utf-8")
    # README mirror so GitHub renders the archive at the docs/ root too.
    (out_dir / "README.md").write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def generate(date_str: str, top: int, out_dir: Path, offline: bool = False) -> Path:
    papers, source_label = fetch_papers(offline=offline)
    papers.sort(key=lambda p: p.get("upvotes", 0), reverse=True)
    selected = papers[: max(1, top)]

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    llm_enabled = bool(api_key) and bool(selected)
    if llm_enabled:
        for paper in selected:
            prose = _anthropic_prose(paper, api_key)
            if prose:
                paper["_prose"] = prose

    used_llm = any(p.get("_prose") for p in selected)
    md = render_digest(date_str, selected, source_label, used_llm)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.md"
    out_path.write_text(md, encoding="utf-8")
    write_index(out_dir)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a daily AI-paper digest.")
    parser.add_argument("--date", default=None, help="Digest date (YYYY-MM-DD). Default: today (UTC).")
    parser.add_argument("--top", type=int, default=5, help="Number of papers (default: 5).")
    parser.add_argument("--out", default="docs", help="Output directory (default: docs).")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip network; use the bundled sample fixture (for CI / testing).",
    )
    args = parser.parse_args(argv)

    if args.date:
        try:
            _dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"[error] --date must be YYYY-MM-DD, got: {args.date}", file=sys.stderr)
            return 2
        date_str = args.date
    else:
        date_str = _dt.datetime.now(_dt.timezone.utc).date().isoformat()

    out_dir = (REPO_ROOT / args.out) if not os.path.isabs(args.out) else Path(args.out)
    out_path = generate(date_str, args.top, out_dir, offline=args.offline)
    print(f"[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
