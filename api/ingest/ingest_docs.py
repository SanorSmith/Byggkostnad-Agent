"""Fetch SCB methodology pages and statistical news for PR0502, chunk, embed.

python -m ingest.ingest_docs           # skips documents whose text is unchanged
python -m ingest.ingest_docs --force   # re-embed everything (after a model change)
"""

import argparse
import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import date

import httpx
import numpy as np
from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader

from app.config import get_settings
from app.db import connection
from app.http import http_retry
from app.logging_setup import log, setup_logging
from app.retrieval.chunk import chunk_text
from app.retrieval.embed import embed
from ingest.scb_client import Throttle

logger = logging.getLogger("ingest.docs")

SCB = "https://www.scb.se"
BKI = (
    f"{SCB}/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser"
    "/priser/byggkostnadsindex-bki"
)
ASSETS = f"{SCB}/contentassets/176b9e8b85b44bafbcb858e0ac2ba884"

STATIC_SOURCES: list[tuple[str, str | None]] = [
    (f"{BKI}/", None),
    (
        f"{BKI}/produktrelaterat/Fordjupad-information/"
        "beskrivning-av-byggnadsprisindex-och-faktorprisindex-for-byggnader/",
        None,
    ),
    (f"{BKI}/produktrelaterat/aktuellt/andringar-i-bki-fran-2024/", None),
    (f"{BKI}/produktrelaterat/aktuellt/andringar-i-byggkostnadsindex-bki-2026/", None),
    (f"{ASSETS}/pr0502_kd_2026_260216.pdf", "Kvalitetsdeklaration Byggkostnadsindex 2026"),
    (f"{ASSETS}/pr0502_staf_2026_260216.pdf", "Statistikens framställning Byggkostnadsindex 2026"),
]

MONTHS_SV = [
    "januari",
    "februari",
    "mars",
    "april",
    "maj",
    "juni",
    "juli",
    "augusti",
    "september",
    "oktober",
    "november",
    "december",
]
NEWS_FROM_YEAR = 2021

BLOCK_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "table"]
DROP_LINES = {"Lyssna", "Statistiknyhet från SCB", "Dela", "Skriv ut"}
# Everything after one of these headings is site chrome, not content.
STOP_HEADINGS = {"Missa inte viktig statistik", "Hitta på sidan", "Kontakt", "Dela sidan"}
# Sections that carry no information about the index itself.
SKIP_SECTIONS = {"Nästa publiceringstillfälle", "Statistikdatabasen"}

# PDF page furniture repeated on every page of SCB's quality declarations.
_PDF_NOISE = [
    re.compile(r"^Statistikansvarig myndighet\s*$"),
    re.compile(r"^Statistiska centralbyrån\s*$"),
    re.compile(r"^(Kvalitetsdeklaration|Statistikens framställning).*(version|Sida)"),
    re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d+\s*\(\d+\)\s*$"),
    re.compile(r"\.{5,}"),  # table-of-contents dot leaders
]
_PDF_HEADING = re.compile(r"^(\d+(?:\.\d+){0,3})\s+([A-ZÅÄÖ][^.]{2,80})$")

_throttle = Throttle(max_calls=10, period=10.0)
_http = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "byggkostnad-agent"})


@dataclass
class FetchedDoc:
    url: str
    title: str
    text: str


def news_urls(today: date) -> list[str]:
    """Candidate monthly news URLs. SCB's slugs are irregular, so missing ones 404."""
    urls = []
    for year in range(NEWS_FROM_YEAR, today.year + 1):
        for i, month in enumerate(MONTHS_SV, start=1):
            if (year, i) > (today.year, today.month):
                break
            urls.append(
                f"{BKI}/pong/statistiknyhet/byggkostnadsindex-for-byggnader-{month}-{year}/"
            )
    return urls


@http_retry
def _get(url: str) -> httpx.Response | None:
    _throttle.wait()
    resp = _http.get(url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp


def _table_text(table: Tag) -> str:
    lines = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def html_to_text(html: str) -> tuple[str, str]:
    """Main content of an scb.se page as heading-marked plain text, plus its title."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    main = soup.find(id="pageContent") or soup.find("main") or soup.body
    if not isinstance(main, Tag):
        return title, ""
    for junk in main.find_all(["script", "style", "nav", "form", "button", "noscript"]):
        junk.decompose()

    out: list[str] = []
    skipping = False
    for el in main.find_all(BLOCK_TAGS):
        if el.find_parent(BLOCK_TAGS) is not None:
            continue  # nested inside a block we already emit
        if el.name == "table":
            text = _table_text(el)
        else:
            text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if not text or text in DROP_LINES:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            if text in STOP_HEADINGS:
                break
            skipping = text in SKIP_SECTIONS
            if not skipping:
                out.append(f"{'#' * int(el.name[1])} {text}")
        elif not skipping:
            out.append(text)
    return title, "\n\n".join(out)


def pdf_to_text(data: bytes) -> str:
    """PDF text with page furniture removed and numbered headings marked."""
    reader = PdfReader(io.BytesIO(data))
    lines: list[str] = []
    for page in reader.pages:
        for raw in (page.extract_text() or "").splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if not line:
                lines.append("")
            elif any(p.search(line) for p in _PDF_NOISE):
                continue
            elif m := _PDF_HEADING.match(line):
                depth = min(m.group(1).count(".") + 1, 4)
                lines += ["", f"{'#' * depth} {m.group(1)} {m.group(2)}", ""]
            else:
                lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def fetch(url: str, title_override: str | None = None) -> FetchedDoc | None:
    resp = _get(url)
    if resp is None:
        return None
    if url.lower().endswith(".pdf") or "pdf" in resp.headers.get("content-type", ""):
        return FetchedDoc(url, title_override or url.rsplit("/", 1)[-1], pdf_to_text(resp.content))
    title, text = html_to_text(resp.text)
    return FetchedDoc(url, title_override or title, text)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def store(doc: FetchedDoc, force: bool) -> str:
    """Insert or refresh one document. Returns 'skipped', 'embedded' or 'empty'."""
    if len(doc.text) < 200:
        return "empty"
    model = get_settings().embedding_model
    digest = content_hash(doc.text)
    with connection() as conn:
        existing = conn.execute(
            "select d.id, d.content_hash, "
            "  (select count(*) from doc_chunks c where c.document_id = d.id "
            "   and c.embedding_model = %s) as current_chunks "
            "from documents d where d.source_url = %s",
            (model, doc.url),
        ).fetchone()
        if (
            not force
            and existing
            and existing["content_hash"] == digest
            and existing["current_chunks"] > 0
        ):
            return "skipped"

    chunks = chunk_text(doc.text)
    vectors = embed([c.text for c in chunks], "document")

    with connection() as conn, conn.transaction():
        row = conn.execute(
            "insert into documents (source_url, title, raw_text, content_hash) "
            "values (%s, %s, %s, %s) "
            "on conflict (source_url) do update set title = excluded.title, "
            "  raw_text = excluded.raw_text, content_hash = excluded.content_hash, "
            "  fetched_at = now() "
            "returning id",
            (doc.url, doc.title, doc.text, digest),
        ).fetchone()
        assert row is not None
        doc_id = row["id"]
        conn.execute("delete from doc_chunks where document_id = %s", (doc_id,))
        with conn.cursor() as cur:
            cur.executemany(
                "insert into doc_chunks "
                "(document_id, chunk_index, text, token_count, embedding, embedding_model) "
                "values (%s, %s, %s, %s, %s, %s)",
                [
                    (doc_id, c.index, c.text, c.token_count, np.array(v, dtype=np.float32), model)
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
    return "embedded"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-embed unchanged documents")
    args = parser.parse_args()
    setup_logging()

    sources = STATIC_SOURCES + [(u, None) for u in news_urls(date.today())]
    counts: dict[str, int] = {}
    for url, title in sources:
        doc = fetch(url, title)
        status = "missing" if doc is None else store(doc, args.force)
        counts[status] = counts.get(status, 0) + 1
        log(logger, "document", url=url, status=status)
    log(logger, "done", **counts)


if __name__ == "__main__":
    main()
