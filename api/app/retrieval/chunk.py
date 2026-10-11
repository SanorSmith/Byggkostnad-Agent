"""Heading-first, paragraph-second chunking.

Target ~500 tokens per chunk with ~80 tokens of overlap. A chunk never
crosses a heading: each section is chunked on its own, and the section
heading is prefixed to every chunk taken from it so a chunk stays
interpretable on its own. Overlap is carried only inside a section.

Token counts are estimated (4 characters per token). It is close enough
for sizing and avoids a tokenizer dependency tied to a different model.
"""

import math
import re
from dataclasses import dataclass

TARGET_TOKENS = 500
OVERLAP_TOKENS = 80
# A section shorter than this is merged into the next one, heading kept as
# a line of text, so short "Kort information"-style blocks are not orphaned.
MIN_SECTION_TOKENS = 120
CHARS_PER_TOKEN = 4

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_SENTENCE = re.compile(r"(?<=[.?])\s+")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def split_sections(text: str) -> list[tuple[str, list[str]]]:
    """Return (heading, paragraphs) pairs. Headings are markdown '#' lines."""
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    paras: list[str] = []
    buf: list[str] = []

    def flush_para() -> None:
        if buf:
            p = " ".join(buf).strip()
            if p:
                paras.append(p)
            buf.clear()

    for line in text.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            flush_para()
            if paras or heading:
                sections.append((heading, paras))
            heading, paras = m.group(1).strip(), []
        elif not line.strip():
            flush_para()
        else:
            buf.append(line.strip())
    flush_para()
    if paras or heading:
        sections.append((heading, paras))
    return [(h, p) for h, p in sections if p]


def merge_small_sections(
    sections: list[tuple[str, list[str]]], min_tokens: int = MIN_SECTION_TOKENS
) -> list[tuple[str, list[str]]]:
    merged: list[tuple[str, list[str]]] = []
    carry: list[str] = []
    for heading, paras in sections:
        size = estimate_tokens(" ".join(paras))
        if size < min_tokens:
            carry += ([heading] if heading else []) + paras
            continue
        merged.append((heading, carry + paras))
        carry = []
    if carry:
        if merged:
            h, p = merged[-1]
            merged[-1] = (h, p + carry)
        else:
            merged.append(("", carry))
    return merged


def _split_long(paragraph: str, max_tokens: int) -> list[str]:
    """Split an oversized paragraph on sentences, then hard-wrap by words."""
    if estimate_tokens(paragraph) <= max_tokens:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE.split(paragraph):
        candidate = f"{current} {sentence}".strip()
        if estimate_tokens(candidate) <= max_tokens:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        if estimate_tokens(sentence) <= max_tokens:
            current = sentence
            continue
        for w in sentence.split():
            cand = f"{current} {w}".strip()
            if estimate_tokens(cand) > max_tokens and current:
                pieces.append(current)
                current = w
            else:
                current = cand
    if current:
        pieces.append(current)
    return pieces


def _tail(text: str, tokens: int) -> str:
    """Last ~`tokens` worth of text, cut on a word boundary."""
    chars = tokens * CHARS_PER_TOKEN
    if len(text) <= chars:
        return text
    cut = text[-chars:]
    space = cut.find(" ")
    return cut[space + 1 :] if space != -1 else cut


def chunk_text(
    text: str, target: int = TARGET_TOKENS, overlap: int = OVERLAP_TOKENS
) -> list[Chunk]:
    chunks: list[str] = []
    for heading, paras in merge_small_sections(split_sections(text)):
        prefix = f"{heading}\n\n" if heading else ""
        budget = target - estimate_tokens(prefix)
        units = [u for p in paras for u in _split_long(p, budget - overlap)]
        body = ""
        for unit in units:
            candidate = f"{body}\n\n{unit}" if body else unit
            if estimate_tokens(candidate) <= budget or not body:
                body = candidate
                continue
            chunks.append(prefix + body)
            body = f"{_tail(body, overlap)}\n\n{unit}"
        if body:
            chunks.append(prefix + body)
    return [Chunk(i, c, estimate_tokens(c)) for i, c in enumerate(chunks)]
