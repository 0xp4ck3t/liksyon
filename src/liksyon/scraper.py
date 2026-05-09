import platform
import random
import re
import time
from pathlib import Path

import browser_cookie3
import requests

API_FIELDS = (
    "?page_size=200"
    "&fields[lecture]=title,object_index,is_published,sort_order,created,asset,is_free"
    "&fields[chapter]=title,object_index,is_published,sort_order"
    "&fields[asset]=title,filename,asset_type,status,time_estimation,is_external,captions"
    "&caching_intent=True"
)

BROWSERS = {
    "1": ("firefox",   "Firefox"),
    "2": ("chrome",    "Chrome"),
    "3": ("chromium",  "Chromium"),
    "4": ("edge",      "Microsoft Edge"),
    "5": ("brave",     "Brave"),
    "6": ("safari",    "Safari (Mac only)"),
}

_BROWSER_LOADERS = {
    "firefox":  browser_cookie3.firefox,
    "chrome":   browser_cookie3.chrome,
    "chromium": browser_cookie3.chromium,
    "edge":     browser_cookie3.edge,
    "brave":    browser_cookie3.brave,
    "safari":   browser_cookie3.safari,
}

_USER_AGENTS = {
    "firefox":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "chrome":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "chromium": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "edge":     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "brave":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "safari":   "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
}


def pick_browser() -> str:
    print("\nWhich browser are you logged into Udemy with?")
    for key, (_, label) in BROWSERS.items():
        print(f"  [{key}] {label}")
    print()
    while True:
        choice = input("Pick a browser: ").strip()
        if choice in BROWSERS:
            browser_id, label = BROWSERS[choice]
            print(f"Using {label}\n")
            return browser_id
        print(f"  Enter a number between 1 and {len(BROWSERS)}.")


def _find_firefox_cookie_file() -> str:
    os_name = platform.system()
    if os_name == "Darwin":
        base = Path.home() / "Library/Application Support/Firefox/Profiles"
    elif os_name == "Linux":
        base = Path.home() / ".mozilla/firefox"
    elif os_name == "Windows":
        base = Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles"
    else:
        raise RuntimeError(f"Unsupported OS: {os_name}")

    if not base.exists():
        raise FileNotFoundError(f"Firefox profiles folder not found: {base}")

    profiles = [p for p in base.iterdir() if p.is_dir()]
    # prefer default-release, fall back to any default profile
    profile = (
        next((p for p in profiles if p.name.endswith(".default-release")), None)
        or next((p for p in profiles if "default" in p.name), None)
        or (profiles[0] if profiles else None)
    )
    if not profile:
        raise FileNotFoundError("No Firefox profile found.")

    cookie_file = profile / "cookies.sqlite"
    if not cookie_file.exists():
        raise FileNotFoundError(f"cookies.sqlite not found in profile: {profile}")

    return str(cookie_file)


def load_browser_cookies(browser: str) -> requests.cookies.RequestsCookieJar:
    loader = _BROWSER_LOADERS.get(browser)
    if not loader:
        raise ValueError(f"Unsupported browser: {browser}")
    try:
        if browser == "firefox":
            cookie_file = _find_firefox_cookie_file()
            return loader(cookie_file=cookie_file, domain_name=".udemy.com")
        return loader(domain_name=".udemy.com")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Could not read {browser} cookies. "
            f"Make sure you are logged into Udemy in {browser}.\nDetail: {e}"
        )


class UdemyScraper:
    def __init__(self, browser: str = "firefox"):
        self.browser = browser
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _USER_AGENTS.get(browser, _USER_AGENTS["firefox"]),
            "Referer": "https://www.udemy.com/",
        })

    def __enter__(self):
        cookies = load_browser_cookies(self.browser)
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

    def _fetch_vtt(self, vtt_url: str, retries: int = 3) -> str:
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(vtt_url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                if attempt == retries:
                    raise
                print(f"    (retry {attempt}/{retries - 1}: {e})")
                time.sleep(2 * attempt)

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
                try:
                    vtt = self._fetch_vtt(lecture["caption_url"])
                    transcript_text = self._parse_vtt(vtt)
                except Exception as e:
                    print(f"    (failed to fetch transcript: {e})")
                    transcript_text = None
            else:
                print("    (no captions — skipping)")
                transcript_text = None
            transcripts.append({**lecture, "course_id": course_id, "transcript": transcript_text})
            if i < len(lectures) - 1:
                time.sleep(random.uniform(1, 3))
        return transcripts
