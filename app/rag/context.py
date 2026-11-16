import re

CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def _label(chunk: dict) -> str:
    label = chunk.get("source", "unknown")
    if chunk.get("section"):
        label += f" > {chunk['section']}"
    if chunk.get("page"):
        label += f", page {chunk['page']}"
    return label


def format_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[{i}] {_label(c)}\n{c['text']}" for i, c in enumerate(chunks, 1)
    )


def cited_numbers(answer: str) -> set[int]:
    return {int(n) for n in CITATION_RE.findall(answer)}


def sources_footer(answer: str, chunks: list[dict]) -> str:
    """Build the Sources list from the citations the answer actually uses."""
    cited = sorted(n for n in cited_numbers(answer) if 1 <= n <= len(chunks))
    if not cited:
        return ""
    lines = ["Sources:"]
    lines += [f"[{n}] {_label(chunks[n - 1])}" for n in cited]
    return "\n".join(lines)