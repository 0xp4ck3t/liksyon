import re
import tiktoken

CHUNK_SIZE = 600      # target tokens per chunk
CHUNK_OVERLAP = 50    # tokens of overlap between chunks to preserve context

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def clean_transcript(text: str) -> str:
    """Remove filler words and normalize whitespace."""
    fillers = r"\b(um+|uh+|ah+|er+|hmm+|like|you know|right\?|okay so|so um|alright)\b"
    text = re.sub(fillers, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def split_into_sentences(text: str) -> list[str]:
    """Split on sentence boundaries without breaking abbreviations."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_transcript(transcript: str) -> list[dict]:
    """
    Split a cleaned transcript into token-aware chunks.
    Returns list of {text, token_count, chunk_index}.
    """
    cleaned = clean_transcript(transcript)
    sentences = split_into_sentences(cleaned)

    chunks = []
    current_sentences = []
    current_tokens = 0
    overlap_sentences = []

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        # If a single sentence exceeds chunk size, force-split it
        if sentence_tokens > CHUNK_SIZE:
            if current_sentences:
                chunks.append(" ".join(current_sentences))
                overlap_sentences = current_sentences[-3:]
                current_sentences = list(overlap_sentences)
                current_tokens = sum(count_tokens(s) for s in current_sentences)

            # Hard split the long sentence by words
            words = sentence.split()
            buffer = []
            buffer_tokens = 0
            for word in words:
                wt = count_tokens(word)
                if buffer_tokens + wt > CHUNK_SIZE and buffer:
                    chunks.append(" ".join(buffer))
                    buffer = buffer[-10:]  # small word overlap
                    buffer_tokens = sum(count_tokens(w) for w in buffer)
                buffer.append(word)
                buffer_tokens += wt
            if buffer:
                current_sentences = [" ".join(buffer)]
                current_tokens = buffer_tokens
            continue

        # Normal case: add sentence to current chunk
        if current_tokens + sentence_tokens > CHUNK_SIZE and current_sentences:
            chunks.append(" ".join(current_sentences))
            # carry last few sentences as overlap into next chunk
            overlap_sentences = current_sentences[-3:]
            current_sentences = list(overlap_sentences)
            current_tokens = sum(count_tokens(s) for s in current_sentences)

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return [
        {
            "text": chunk,
            "token_count": count_tokens(chunk),
            "chunk_index": i,
        }
        for i, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def estimate_cost(transcripts: list[dict], model: str = "claude-sonnet-4-6") -> dict:
    """
    Estimate token usage and approximate cost before sending to Claude.
    Prices per million tokens (input) as of 2026.
    """
    prices = {
        "claude-haiku-4-5":   0.80,
        "claude-sonnet-4-6":  3.00,
        "claude-opus-4-7":   15.00,
    }

    total_chunks = 0
    total_tokens = 0

    for t in transcripts:
        if not t.get("transcript"):
            continue
        chunks = chunk_transcript(t["transcript"])
        total_chunks += len(chunks)
        total_tokens += sum(c["token_count"] for c in chunks)

    price_per_million = prices.get(model, 3.00)
    estimated_cost = (total_tokens / 1_000_000) * price_per_million

    return {
        "lectures": len([t for t in transcripts if t.get("transcript")]),
        "chunks": total_chunks,
        "tokens": total_tokens,
        "model": model,
        "estimated_cost_usd": round(estimated_cost, 4),
    }
