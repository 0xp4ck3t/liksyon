# Liksyon

> *Liksyon* is Haitian Creole for "lesson."

A terminal-based study tool that turns your Udemy courses into Anki flashcards using AI. Pick a course, select sections, and Liksyon fetches the video transcripts, runs them through Claude, and generates context-aware flashcards you can review and export directly to Anki.

Quizzes and additional study formats are planned for future iterations.

![Liksyon demo](files/demo.gif)

---

## How it works

1. **Select a course** — Liksyon reads your browser cookies to fetch courses from your Udemy account (no password required)
2. **Pick sections** — choose which sections or individual lectures to study
3. **Configure** — set card style, difficulty, and max cards per lecture
4. **Generate** — Claude processes each transcript chunk and produces flashcards
5. **Review** — keep, skip, or mark cards for review; edit any card inline
6. **Export** — push directly to Anki via AnkiConnect, save as `.apkg`, or export as CSV

---

## Requirements

- **Python 3.11+**
- **Claude Code CLI** — install from [claude.ai/code](https://claude.ai/code) (used to generate cards)
- **Anki** + **AnkiConnect plugin** (optional, for direct push)
- A **Udemy account** with courses you own
- A browser where you are **logged into Udemy** (Chrome, Firefox, Edge, Brave, Safari, or Chromium)

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/0xp4ck3t/liksyon/main/scripts/install.sh | bash
```

Then run:

```bash
liksyon
```

> If `liksyon` is not found after install, add `~/.local/bin` to your PATH:
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
> ```

---

## Manual install

```bash
git clone https://github.com/0xp4ck3t/liksyon
cd liksyon
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
liksyon
```

---

## AnkiConnect setup (optional)

To push cards directly into Anki:

1. Open Anki
2. Go to **Tools → Add-ons → Get Add-ons**
3. Enter code `2055492159` (AnkiConnect)
4. Restart Anki
5. Keep Anki open when you reach the Export screen in Liksyon

---

## Navigation

| Key | Action |
|-----|--------|
| `↑ ↓` | Navigate |
| `Enter` | Select / confirm |
| `Space` | Toggle selection |
| `Esc` | Back |
| `E` | Edit card (Review screen) |
| `/` | Search courses |
| `q` | Quit |

---

## Notes

- Liksyon only processes courses you own on Udemy
- Transcripts are fetched from Udemy's closed-caption API — lectures without captions are skipped
- Cards and transcripts are cached locally in `data/liksyon.db` so re-runs skip already-processed chunks
- Exported `.apkg` files are saved to the `exports/` directory

---

## Legal

Personal use only. Processes only courses you own. You are responsible for compliance with Udemy's Terms of Service.

---

## License

MIT
