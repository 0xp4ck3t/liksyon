"""
YouTube transcript fetcher.

Uses youtube-transcript-api to pull subtitles and the YouTube oEmbed API
to resolve the video title — no API key required.
"""

import re

import requests
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

_API = YouTubeTranscriptApi()


def extract_video_id(url: str) -> str:
    """Extract an 11-character YouTube video ID from various URL forms."""
    url = url.strip()
    # Bare video ID
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url
    patterns = [
        r"youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    raise ValueError(f"Could not find a YouTube video ID in: {url!r}")


def _get_video_info(video_id: str) -> dict:
    """Fetch title and channel via the YouTube oEmbed endpoint (no API key)."""
    oembed_url = (
        f"https://www.youtube.com/oembed"
        f"?url=https://www.youtube.com/watch?v={video_id}&format=json"
    )
    resp = requests.get(oembed_url, timeout=10)
    if resp.status_code == 404:
        raise ValueError(f"Video not found or not embeddable: {video_id}")
    resp.raise_for_status()
    data = resp.json()
    return {
        "title":   data.get("title",       f"YouTube Video ({video_id})"),
        "channel": data.get("author_name", "Unknown"),
    }


def _fetch_transcript_text(video_id: str) -> str:
    """Download and concatenate the transcript for a video."""
    try:
        # Try English first, then fall back to any available language
        try:
            result = _API.fetch(video_id, languages=("en",))
        except NoTranscriptFound:
            tl     = _API.list(video_id)
            first  = next(iter(tl))      # first available transcript
            result = first.fetch()
        return " ".join(s.text for s in result)
    except TranscriptsDisabled:
        raise ValueError("Transcripts are disabled for this video.")
    except NoTranscriptFound:
        raise ValueError("No transcript is available for this video.")
    except Exception as exc:
        raise ValueError(f"Could not fetch transcript: {exc}") from exc


def fetch_youtube_transcript(url: str) -> dict:
    """
    Fetch video metadata and transcript for a YouTube URL.

    Returns a dict that is compatible with the Udemy transcript format used
    throughout the rest of the pipeline:

        {
            "video_id":  "dQw4w9WgXcQ",
            "id":        "yt_dQw4w9WgXcQ",
            "title":     "Video Title",
            "channel":   "Channel Name",
            "chapter":   "Channel Name",     # used as chapter in flashcard
            "transcript": "full text …",
            "url":       "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
    """
    video_id = extract_video_id(url)
    info      = _get_video_info(video_id)
    transcript = _fetch_transcript_text(video_id)
    return {
        "video_id":   video_id,
        "id":         f"yt_{video_id}",
        "title":      info["title"],
        "channel":    info["channel"],
        "chapter":    info["channel"],
        "transcript": transcript,
        "url":        f"https://www.youtube.com/watch?v={video_id}",
    }
