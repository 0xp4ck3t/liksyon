import json
import random
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

import requests

FIREFOX_PROFILE = Path.home() / "Library/Application Support/Firefox/Profiles/3jw93za9.default-release"

API_FIELDS = (
    "?page_size=200"
    "&fields[lecture]=title,object_index,is_published,sort_order,created,asset,is_free"
    "&fields[chapter]=title,object_index,is_published,sort_order"
    "&fields[asset]=title,filename,asset_type,status,time_estimation,is_external,captions"
    "&caching_intent=True"
)


def load_firefox_cookies(profile_path: Path = FIREFOX_PROFILE) -> dict:
    cookies_db = profile_path / "cookies.sqlite"
    if not cookies_db.exists():
        raise FileNotFoundError(f"Firefox cookies not found at {cookies_db}")

    # Copy to temp — Firefox may have the file locked
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        tmp = Path(f.name)
    shutil.copy2(cookies_db, tmp)

    try:
        conn = sqlite3.connect(tmp)
        rows = conn.execute(
            "SELECT name, value FROM moz_cookies WHERE host LIKE '%udemy.com'"
        ).fetchall()
        conn.close()
    finally:
        tmp.unlink(missing_ok=True)

    return {name: value for name, value in rows}


class UdemyScraper:
    def __init__(self, profile_path: Path = FIREFOX_PROFILE):
        self.profile_path = profile_path
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) "
                "Gecko/20100101 Firefox/124.0"
            ),
            "Referer": "https://www.udemy.com/",
        })

    def __enter__(self):
        cookies = load_firefox_cookies(self.profile_path)
        self.session.cookies.update(cookies)
        return self

    def __exit__(self, *args):
        self.session.close()

    def _api_get(self, url: str) -> dict:
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def is_logged_in(self) -> bool:
        try:
            data = self._api_get("https://www.udemy.com/api-2.0/contexts/me/?header=True")
            return bool(data.get("header", {}).get("user", {}).get("id"))
        except Exception:
            return False

    def get_owned_courses(self) -> list[dict]:
        courses = []
        url = (
            "https://www.udemy.com/api-2.0/users/me/subscribed-courses/"
            "?page_size=100&ordering=-last_accessed&fields[course]=id,title,url"
        )
        while url:
            data = self._api_get(url)
            courses.extend(data.get("results", []))
            url = data.get("next")
        return courses

    def get_course_structure(self, course_id: str) -> list[dict]:
        url = f"https://www.udemy.com/api-2.0/courses/{course_id}/subscriber-curriculum-items/{API_FIELDS}"
        return self._api_get(url).get("results", [])

    def build_lecture_list(self, results: list[dict]) -> list[dict]:
        lectures = []
        current_chapter = "Uncategorized"
        for item in results:
            cls = item.get("_class")
            if cls == "chapter":
                current_chapter = item["title"]
            elif cls == "lecture":
                asset = item.get("asset") or {}
                if not str(asset.get("asset_type", "")).lower().startswith("video"):
                    continue
                captions = asset.get("captions") or []
                en = next((c for c in captions if str(c.get("locale_id", "")).startswith("en")), None)
                caption = en or (captions[0] if captions else None)
                lectures.append({
                    "id": str(item["id"]),
                    "title": item["title"],
                    "chapter": current_chapter,
                    "caption_url": caption["url"] if caption else None,
                    "locale": caption.get("locale_id") if caption else None,
                })
        return lectures

    def _fetch_vtt(self, vtt_url: str) -> str:
        resp = self.session.get(vtt_url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _parse_vtt(self, vtt: str) -> str:
        lines = []
        for line in vtt.splitlines():
            line = line.strip()
            if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                continue
            line = re.sub(r"<[^>]+>", "", line)
            lines.append(line)
        deduped = [lines[i] for i in range(len(lines)) if i == 0 or lines[i] != lines[i - 1]]
        return " ".join(deduped)

    def scrape_lectures(self, lectures: list[dict], course_id: str) -> list[dict]:
        transcripts = []
        for i, lecture in enumerate(lectures):
            print(f"  [{i + 1}/{len(lectures)}] {lecture['chapter']} — {lecture['title']}")
            if lecture["caption_url"]:
                vtt = self._fetch_vtt(lecture["caption_url"])
                transcript_text = self._parse_vtt(vtt)
            else:
                print("    (no captions — skipping)")
                transcript_text = None
            transcripts.append({**lecture, "course_id": course_id, "transcript": transcript_text})
            if i < len(lectures) - 1:
                time.sleep(random.uniform(1, 3))
        return transcripts
