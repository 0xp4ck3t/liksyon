import hashlib
import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/liksyon.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transcripts (
                lecture_id   TEXT PRIMARY KEY,
                course_id    TEXT NOT NULL,
                course_title TEXT,
                chapter      TEXT,
                title        TEXT,
                transcript   TEXT,
                locale       TEXT,
                scraped_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS processed_chunks (
                chunk_hash   TEXT PRIMARY KEY,
                lecture_id   TEXT NOT NULL,
                chunk_index  INTEGER NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS flashcards (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                lecture_id     TEXT NOT NULL,
                course_id      TEXT NOT NULL,
                front          TEXT NOT NULL,
                back           TEXT NOT NULL,
                tags           TEXT,
                difficulty     TEXT,
                chapter        TEXT,
                source_lecture TEXT,
                source_course  TEXT,
                chunk_hash     TEXT,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # migrate existing databases that predate the chapter column
        try:
            conn.execute("ALTER TABLE flashcards ADD COLUMN chapter TEXT")
        except sqlite3.OperationalError:
            pass


def save_transcript(lecture: dict, course_title: str = ""):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO transcripts
                (lecture_id, course_id, course_title, chapter, title, transcript, locale)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lecture_id) DO UPDATE SET
                transcript   = excluded.transcript,
                scraped_at   = CURRENT_TIMESTAMP
            """,
            (
                lecture["id"],
                lecture["course_id"],
                course_title,
                lecture.get("chapter"),
                lecture.get("title"),
                lecture.get("transcript"),
                lecture.get("locale"),
            ),
        )


def get_transcript(lecture_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM transcripts WHERE lecture_id = ?", (lecture_id,)
        ).fetchone()
        return dict(row) if row else None


def chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def is_chunk_processed(hash_: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_chunks WHERE chunk_hash = ?", (hash_,)
        ).fetchone()
        return row is not None


def mark_chunk_processed(hash_: str, lecture_id: str, chunk_index: int):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO processed_chunks (chunk_hash, lecture_id, chunk_index)
            VALUES (?, ?, ?)
            """,
            (hash_, lecture_id, chunk_index),
        )


def save_flashcard(card: dict):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO flashcards
                (lecture_id, course_id, front, back, tags, difficulty,
                 chapter, source_lecture, source_course, chunk_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card["lecture_id"],
                card["course_id"],
                card["front"],
                card["back"],
                json.dumps(card.get("tags", [])),
                card.get("difficulty"),
                card.get("chapter"),
                card.get("source_lecture"),
                card.get("source_course"),
                card.get("chunk_hash"),
            ),
        )


def get_flashcards(course_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM flashcards WHERE course_id = ? ORDER BY id",
            (course_id,),
        ).fetchall()
        cards = []
        for row in rows:
            card = dict(row)
            card["tags"] = json.loads(card["tags"] or "[]")
            cards.append(card)
        return cards


def update_flashcard(card_id: int, front: str, back: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE flashcards SET front = ?, back = ? WHERE id = ?",
            (front, back, card_id),
        )


def get_unprocessed_lectures(course_id: str) -> list[dict]:
    """Return transcripts that have no flashcards yet."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.* FROM transcripts t
            WHERE t.course_id = ?
              AND t.transcript IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM flashcards f WHERE f.lecture_id = t.lecture_id
              )
            ORDER BY t.scraped_at
            """,
            (course_id,),
        ).fetchall()
        return [dict(row) for row in rows]
