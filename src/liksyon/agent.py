import os
from anthropic import Anthropic
from src.liksyon.chunker import chunk_transcript, count_tokens, estimate_cost
from src.liksyon.storage import (
    chunk_hash,
    is_chunk_processed,
    mark_chunk_processed,
    save_flashcard,
)

MODELS = {
    "1": "claude-haiku-4-5-20251001",
    "2": "claude-sonnet-4-6",
    "3": "claude-opus-4-7",
}

MODEL_LABELS = {
    "claude-haiku-4-5-20251001": "Haiku 4.5  — fast, cheap",
    "claude-sonnet-4-6":         "Sonnet 4.6 — recommended",
    "claude-opus-4-7":           "Opus 4.7   — best quality",
}

SYSTEM_PROMPT = """\
You are an expert educator generating Anki flashcards from course lecture transcripts.

Rules:
- Create cards that test UNDERSTANDING, not just memorisation
- Prefer applied questions: "When would you use X?", "What happens if Y?"
- Keep each card atomic — one concept per card
- Avoid vague or trivial cards (e.g. "What is the title of this course?")
- Difficulty: easy = definition/recall, medium = application, hard = analysis/comparison

Card types you should mix:
- conceptual  : "What is X?" or "What does X mean?"
- applied     : "When/why/how would you use X?"
- process     : "What are the steps to do X?"
- distinction : "What is the difference between X and Y?"
"""

SUBMIT_TOOL = {
    "name": "submit_cards",
    "description": (
        "Submit the final list of flashcards generated from this transcript chunk. "
        "Only include cards that are clear, accurate, and worth reviewing. "
        "Discard anything vague, trivial, or duplicate."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "front":      {"type": "string"},
                        "back":       {"type": "string"},
                        "tags":       {"type": "array", "items": {"type": "string"}},
                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                        "card_type":  {"type": "string", "enum": ["conceptual", "applied", "process", "distinction"]},
                    },
                    "required": ["front", "back", "tags", "difficulty", "card_type"],
                },
            }
        },
        "required": ["cards"],
    },
}


def pick_model() -> str:
    print("\nWhich Claude model?")
    for key, model_id in MODELS.items():
        print(f"  [{key}] {MODEL_LABELS[model_id]}")
    print()
    while True:
        choice = input("Pick a model (default 2): ").strip() or "2"
        if choice in MODELS:
            model = MODELS[choice]
            print(f"Using {MODEL_LABELS[model]}\n")
            return model
        print("  Enter 1, 2, or 3.")


def _generate_cards_for_chunk(
    client: Anthropic,
    model: str,
    chunk: dict,
    lecture_title: str,
    chapter: str,
    course_title: str,
) -> list[dict]:
    user_message = (
        f"Course: {course_title}\n"
        f"Section: {chapter}\n"
        f"Lecture: {lecture_title}\n\n"
        f"Transcript chunk ({chunk['token_count']} tokens):\n\n"
        f"{chunk['text']}"
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[SUBMIT_TOOL],
        tool_choice={"type": "tool", "name": "submit_cards"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_cards":
            return block.input.get("cards", [])
    return []


def run_agent(
    transcripts: list[dict],
    course_title: str,
    model: str,
    max_cards_per_lecture: int = 10,
) -> list[dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment.")

    client = Anthropic(api_key=api_key)
    all_cards = []

    for lecture in transcripts:
        if not lecture.get("transcript"):
            continue

        lecture_id   = lecture["id"]
        lecture_title = lecture["title"]
        chapter      = lecture.get("chapter", "")
        course_id    = lecture["course_id"]

        chunks = chunk_transcript(lecture["transcript"])
        lecture_cards = []

        for chunk in chunks:
            h = chunk_hash(chunk["text"])

            if is_chunk_processed(h):
                print(f"    (chunk {chunk['chunk_index']} already processed — skipping)")
                continue

            print(f"    chunk {chunk['chunk_index'] + 1}/{len(chunks)} — {chunk['token_count']} tokens")

            cards = _generate_cards_for_chunk(
                client, model, chunk, lecture_title, chapter, course_title
            )

            mark_chunk_processed(h, lecture_id, chunk["chunk_index"])

            for card in cards:
                card_record = {
                    "lecture_id":     lecture_id,
                    "course_id":      course_id,
                    "front":          card["front"],
                    "back":           card["back"],
                    "tags":           card.get("tags", []),
                    "difficulty":     card.get("difficulty", "medium"),
                    "source_lecture": lecture_title,
                    "source_course":  course_title,
                    "chunk_hash":     h,
                }
                lecture_cards.append(card_record)

        # cap cards per lecture
        if len(lecture_cards) > max_cards_per_lecture:
            lecture_cards = lecture_cards[:max_cards_per_lecture]

        for card in lecture_cards:
            save_flashcard(card)

        print(f"  → {len(lecture_cards)} cards saved for: {lecture_title}")
        all_cards.extend(lecture_cards)

    return all_cards
