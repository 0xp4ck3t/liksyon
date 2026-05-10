import hashlib
import html
import json
import re
from pathlib import Path

import genanki

EXPORTS_DIR = Path("exports")

CARD_CSS = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 18px;
    text-align: left;
    color: #1a1a1a;
    background-color: #ffffff;
    padding: 20px;
    max-width: 700px;
    margin: 0 auto;
    line-height: 1.6;
}
.front { font-weight: 600; font-size: 20px; }
.back  { margin-top: 12px; }
.source {
    margin-top: 16px;
    font-size: 11px;
    color: #999;
    border-top: 1px solid #eee;
    padding-top: 8px;
}
.tag {
    display: inline-block;
    background: #f0f0f0;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    margin-right: 4px;
    color: #666;
}
.difficulty-easy   { color: #2e7d32; font-size: 11px; }
.difficulty-medium { color: #e65100; font-size: 11px; }
.difficulty-hard   { color: #b71c1c; font-size: 11px; }
"""

CARD_TEMPLATE = [
    {
        "name": "Liksyon Card",
        "qfmt": """
<div class="card">
  <div class="front">{{Front}}</div>
  <div class="source">{{Source}}</div>
</div>
""",
        "afmt": """
<div class="card">
  <div class="front">{{Front}}</div>
  <hr>
  <div class="back">{{Back}}</div>
  <div class="source">
    {{Source}}<br>
    <span class="{{DifficultyClass}}">{{Difficulty}}</span>
    &nbsp;{{Tags}}
  </div>
</div>
""",
    }
]


def _stable_id(name: str) -> int:
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)


def _safe_filename(name: str) -> str:
    return re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')


def _build_model(course_title: str) -> genanki.Model:
    return genanki.Model(
        _stable_id(f"liksyon-model-{course_title}"),
        "Liksyon Flashcard",
        fields=[
            {"name": "Front"},
            {"name": "Back"},
            {"name": "Source"},
            {"name": "Difficulty"},
            {"name": "DifficultyClass"},
            {"name": "Tags"},
        ],
        templates=CARD_TEMPLATE,
        css=CARD_CSS,
    )


def export_to_apkg(flashcards: list[dict], course_title: str) -> Path:
    """
    Export flashcards to an Anki .apkg file.
    Cards are grouped into sub-decks by chapter: CourseName::ChapterName
    Returns the path to the generated file.
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    model = _build_model(course_title)
    decks: dict[str, genanki.Deck] = {}
    package_decks = []

    for card in flashcards:
        deck_name = f"{course_title}::{card.get('chapter') or 'General'}"

        if deck_name not in decks:
            deck = genanki.Deck(_stable_id(deck_name), deck_name)
            decks[deck_name] = deck
            package_decks.append(deck)

        tags = card.get("tags") or []
        if isinstance(tags, str):
            tags = json.loads(tags)

        difficulty = card.get("difficulty", "medium")

        note = genanki.Note(
            model=model,
            fields=[
                html.escape(card["front"]),
                html.escape(card["back"]),
                html.escape(card.get("source_lecture", "")),
                difficulty.capitalize(),
                f"difficulty-{difficulty}",
                "  ".join(f"[{html.escape(t)}]" for t in tags),
            ],
            tags=tags,
            guid=genanki.guid_for(card["front"]),
        )
        decks[deck_name].add_note(note)

    output_path = EXPORTS_DIR / f"{_safe_filename(course_title)}.apkg"
    genanki.Package(package_decks).write_to_file(str(output_path))

    return output_path
