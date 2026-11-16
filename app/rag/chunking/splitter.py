from dataclasses import dataclass

from app.rag.loader.loader import Block

# ~350 words is roughly 450 to 500 tokens, within common 512-token embedding limits.
# Verify against your embedding model's tokenizer.
MAX_WORDS = 350
OVERLAP_WORDS = 50


@dataclass(frozen=True)
class Chunk:
    text: str
    section: str | None
    page: int | None
    index: int  # position within the source file


def split_text(text: str, max_words: int = MAX_WORDS,
               overlap: int = OVERLAP_WORDS) -> list[str]:
    if overlap < 0 or overlap >= max_words:
        raise ValueError("overlap must be >= 0 and < max_words")

    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    step = max_words - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + max_words]))
        if start + max_words >= len(words):
            break
    return chunks


def chunk_blocks(blocks: list[Block]) -> list[Chunk]:
    """Split every block, keeping its section and page on each chunk."""
    chunks: list[Chunk] = []
    for block in blocks:
        for text in split_text(block.text):
            chunks.append(Chunk(text, block.section, block.page, len(chunks)))
    return chunks