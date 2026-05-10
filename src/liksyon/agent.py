import json
import re
import shutil
import subprocess
from pathlib import Path
from liksyon.chunker import chunk_transcript, count_tokens
from liksyon.storage import (
    chunk_hash,
    is_chunk_processed,
    mark_chunk_processed,
    save_flashcard,
)

SKILLS_DIR = Path(__file__).parents[2] / ".claude" / "skills"


def load_skill(name: str) -> str:
    skill_file = SKILLS_DIR / name / "SKILL.md"
    if not skill_file.exists():
        raise FileNotFoundError(f"Skill not found: {skill_file}")
    content = skill_file.read_text()
    # strip YAML frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()
    return content


def render_skill(skill: str, **variables) -> str:
    for key, value in variables.items():
        skill = skill.replace("{{" + key + "}}", value)
    return skill


_CLAUDE_SEARCH_PATHS = [
    Path.home() / ".local/bin/claude",
    Path("/usr/local/bin/claude"),
    Path("/opt/homebrew/bin/claude"),
    Path.home() / ".npm-global/bin/claude",
    Path.home() / "AppData/Roaming/npm/claude",  # Windows
]


def _find_claude() -> str:
    # Check PATH first
    found = shutil.which("claude")
    if found:
        return found
    # Fall back to common install locations
    for path in _CLAUDE_SEARCH_PATHS:
        if path.exists():
            return str(path)
    raise RuntimeError(
        "Claude Code CLI not found. "
        "Install it from https://claude.ai/code and make sure it's in your PATH."
    )


def check_claude_installed() -> str:
    return _find_claude()


def call_claude(prompt: str, timeout: int = 120) -> str:
    claude_bin = _find_claude()
    result = subprocess.run(
        [claude_bin, "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def extract_json(text: str) -> dict:
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Markdown code block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Raw JSON object anywhere in output
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from Claude output:\n{text[:500]}")


def _generate_cards_for_chunk(
    chunk: dict,
    lecture_title: str,
    chapter: str,
    course_title: str,
    skill: str,
) -> list[dict]:
    prompt = render_skill(
        skill,
        course_title=course_title,
        chapter=chapter,
        lecture_title=lecture_title,
        transcript=chunk["text"],
    )
    raw = call_claude(prompt)
    data = extract_json(raw)
    return data.get("cards", [])


def run_agent(
    transcripts: list[dict],
    course_title: str,
    max_cards_per_lecture: int = 10,
) -> list[dict]:
    check_claude_installed()  # validates early before processing begins
    skill = load_skill("make_flashcards")
    all_cards = []

    for lecture in transcripts:
        if not lecture.get("transcript"):
            continue

        lecture_id    = lecture["id"]
        lecture_title = lecture["title"]
        chapter       = lecture.get("chapter", "")
        course_id     = lecture["course_id"]

        chunks = chunk_transcript(lecture["transcript"])
        lecture_cards = []

        print(f"\n  {lecture_title} ({len(chunks)} chunk(s))")

        for chunk in chunks:
            h = chunk_hash(chunk["text"])

            if is_chunk_processed(h):
                print(f"    chunk {chunk['chunk_index'] + 1} — already processed, skipping")
                continue

            print(f"    chunk {chunk['chunk_index'] + 1}/{len(chunks)} — {chunk['token_count']} tokens")

            try:
                cards = _generate_cards_for_chunk(chunk, lecture_title, chapter, course_title, skill)
            except Exception as e:
                print(f"    ✗ failed: {e}")
                continue

            mark_chunk_processed(h, lecture_id, chunk["chunk_index"])

            for card in cards:
                lecture_cards.append({
                    "lecture_id":     lecture_id,
                    "course_id":      course_id,
                    "front":          card["front"],
                    "back":           card["back"],
                    "tags":           card.get("tags", []),
                    "difficulty":     card.get("difficulty", "medium"),
                    "chapter":        chapter,
                    "source_lecture": lecture_title,
                    "source_course":  course_title,
                    "chunk_hash":     h,
                })

        if len(lecture_cards) > max_cards_per_lecture:
            lecture_cards = lecture_cards[:max_cards_per_lecture]

        for card in lecture_cards:
            save_flashcard(card)

        print(f"    → {len(lecture_cards)} card(s) saved")
        all_cards.extend(lecture_cards)

    return all_cards
