from app.retrieval.chunk import chunk_text, estimate_tokens, split_sections


def _para(word: str, n: int) -> str:
    return " ".join([word] * n) + "."


def test_sections_split_on_headings() -> None:
    text = "# A\n\none\n\ntwo\n\n## B\n\nthree"
    assert split_sections(text) == [("A", ["one", "two"]), ("B", ["three"])]


def test_chunks_do_not_cross_headings() -> None:
    text = f"# First\n\n{_para('alpha', 150)}\n\n# Second\n\n{_para('beta', 150)}"
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert "alpha" in chunks[0].text
    assert "beta" not in chunks[0].text
    assert chunks[1].text.startswith("Second")


def test_long_section_chunks_are_bounded_and_overlap() -> None:
    paras = "\n\n".join(_para(f"w{i}", 60) for i in range(20))
    chunks = chunk_text(f"# Long\n\n{paras}", target=500, overlap=80)
    assert len(chunks) > 1
    assert all(c.token_count <= 520 for c in chunks)
    # The start of each later chunk repeats the end of the previous one.
    tail = chunks[0].text.split()[-5:]
    assert " ".join(tail) in chunks[1].text


def test_small_sections_merge_forward() -> None:
    text = f"# Tiny\n\nshort note\n\n# Big\n\n{_para('gamma', 200)}"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert "Tiny" in chunks[0].text
    assert "gamma" in chunks[0].text


def test_estimate_tokens() -> None:
    assert estimate_tokens("abcd" * 10) == 10
