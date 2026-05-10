import json
import platform
import subprocess
import time
from pathlib import Path

import requests

ANKI_CONNECT_URL = "http://localhost:8765"
ANKI_CONNECT_PLUGIN = "2055492"
ANKI_DOWNLOAD_URL = "https://apps.ankiweb.net"

_ANKI_PATHS = {
    "Darwin":  [Path("/Applications/Anki.app")],
    "Linux":   [],  # detected via which
    "Windows": [
        Path.home() / "AppData/Local/Programs/Anki/anki.exe",
        Path("C:/Program Files/Anki/anki.exe"),
    ],
}


def is_anki_installed() -> bool:
    system = platform.system()
    for path in _ANKI_PATHS.get(system, []):
        if path.exists():
            return True
    if system == "Linux":
        return subprocess.run(
            ["which", "anki"], capture_output=True
        ).returncode == 0
    return False


def is_ankiconnect_running() -> bool:
    try:
        resp = requests.post(
            ANKI_CONNECT_URL,
            json={"action": "version", "version": 6},
            timeout=3,
        )
        return resp.status_code == 200
    except Exception:
        return False


def launch_anki():
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", "-a", "Anki"])
    elif system == "Linux":
        subprocess.Popen(["anki"])
    elif system == "Windows":
        for path in _ANKI_PATHS["Windows"]:
            if path.exists():
                subprocess.Popen([str(path)])
                return


def wait_for_ankiconnect(timeout: int = 30, interval: int = 2) -> bool:
    print("Waiting for Anki to start", end="", flush=True)
    elapsed = 0
    while elapsed < timeout:
        if is_ankiconnect_running():
            print(" connected.")
            return True
        print(".", end="", flush=True)
        time.sleep(interval)
        elapsed += interval
    print(" timed out.")
    return False


def _anki_request(action: str, **params) -> dict:
    payload = {"action": action, "version": 6, "params": params}
    resp = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10)
    result = resp.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect error: {result['error']}")
    return result["result"]


def _ensure_deck(deck_name: str):
    _anki_request("createDeck", deck=deck_name)



def push_cards(flashcards: list[dict], course_title: str) -> int:
    pushed = 0
    for card in flashcards:
        deck_name = f"{course_title}::{card.get('chapter', 'General')}"
        _ensure_deck(deck_name)

        tags = card.get("tags") or []
        if isinstance(tags, str):
            tags = json.loads(tags)

        try:
            _anki_request(
                "addNote",
                note={
                    "deckName": deck_name,
                    "modelName": "Basic",
                    "fields": {
                        "Front": card["front"],
                        "Back": card["back"],
                    },
                    "tags": tags,
                    "options": {"allowDuplicate": False},
                },
            )
            pushed += 1
        except RuntimeError as e:
            if "duplicate" in str(e).lower():
                continue
            raise

    try:
        _anki_request("sync")
    except RuntimeError as e:
        if "auth" in str(e).lower():
            pass  # AnkiWeb not configured — cards are still in local Anki
        else:
            raise

    try:
        _anki_request("guiDeckBrowser")
    except Exception:
        pass  # non-critical — window focus is best-effort

    return pushed


def open_apkg(apkg_path: Path):
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(apkg_path)])
    elif system == "Linux":
        subprocess.run(["xdg-open", str(apkg_path)])
    elif system == "Windows":
        subprocess.run(["start", str(apkg_path)], shell=True)


def deliver_to_anki(flashcards: list[dict], course_title: str, apkg_path: Path):
    """
    Full delivery flow:
    1. Always export .apkg (silent backup)
    2. Try AnkiConnect
    3. If not running, offer to open Anki and retry
    4. If still fails, auto-open the .apkg
    """
    print(f"\nBackup saved → {apkg_path}")

    # --- Check AnkiConnect ---
    if is_ankiconnect_running():
        pushed = push_cards(flashcards, course_title)
        print(f"Pushed {pushed} card(s) to Anki via AnkiConnect.")
        launch_anki()  # bring Anki window to foreground
        return

    # --- AnkiConnect not running ---
    print("\nAnkiConnect not detected.")

    if not is_anki_installed():
        print(f"Anki is not installed. Download it from: {ANKI_DOWNLOAD_URL}")
        print(f"Then install the AnkiConnect plugin (code: {ANKI_CONNECT_PLUGIN})")
        print(f"Or import the backup file manually: {apkg_path}")
        return

    answer = input("Open Anki now and push cards? (Y/n): ").strip().lower()
    if answer in ("", "y", "yes"):
        launch_anki()
        connected = wait_for_ankiconnect(timeout=30)
        if connected:
            pushed = push_cards(flashcards, course_title)
            print(f"Pushed {pushed} card(s) to Anki.")
            print(f"Tip: Install AnkiConnect plugin (code: {ANKI_CONNECT_PLUGIN}) to skip this step next time.")
            return

    # --- Fallback: open .apkg ---
    print("Opening .apkg for manual import...")
    open_apkg(apkg_path)
    print(f"Tip: Install AnkiConnect plugin (code: {ANKI_CONNECT_PLUGIN}) for seamless sync next time.")
