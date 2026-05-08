# Liksyon

A TUI-based AI study tool that turns course transcripts, videos, and learning materials into reviewable Anki flashcards.

## Requirements

- Python 3.11+
- Anthropic API key
- Udemy account (only processes courses you own)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
cp .env.example .env  # add your ANTHROPIC_API_KEY
```

## Legal

Personal use only. Processes only courses you own. You assume responsibility for Udemy's ToS compliance.

## License

MIT
