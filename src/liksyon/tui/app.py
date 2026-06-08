import asyncio
import io
import os
import sys
import time

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    RichLog,
    SelectionList,
    Static,
)
from rich.text import Text
from textual.widgets.selection_list import Selection

from liksyon.agent import run_agent
from liksyon.export.ankiconnect import (
    deliver_to_anki,
    is_anki_installed,
    is_ankiconnect_running,
    push_cards,
)
from liksyon.export.genanki_export import export_to_apkg
from liksyon.scraper import UdemyScraper, load_browser_cookies
from liksyon.storage import get_flashcards, init_db, save_transcript, update_flashcard
from liksyon.youtube_scraper import fetch_youtube_transcript

BROWSERS = [
    ("chrome",   "🌐", "Google Chrome",   "/Applications/Google Chrome.app"),
    ("edge",     "🌊", "Microsoft Edge",  "/Applications/Microsoft Edge.app"),
    ("brave",    "🦁", "Brave Browser",   "/Applications/Brave Browser.app"),
    ("firefox",  "🦊", "Firefox",         "/Applications/Firefox.app"),
    ("chromium", "⬡",  "Chromium",        "/Applications/Chromium.app"),
    ("safari",   "🧭", "Safari",          "/Applications/Safari.app"),
]

def _installed_browsers() -> list[tuple]:
    found = [(k, i, n, p) for k, i, n, p in BROWSERS if os.path.exists(p)]
    return found or BROWSERS  # fallback: show all on non-macOS


def _fmt_duration(info: str) -> str:
    """'22.5 total hours' → '22h 30m'"""
    import re
    m = re.match(r"([\d.]+)", info or "")
    if not m:
        return info or ""
    total_h = float(m.group(1))
    h, mins = int(total_h), round((total_h % 1) * 60)
    return f"{h}h {mins}m" if mins else f"{h}h"


def _fmt_secs(secs: int) -> str:
    if not secs:
        return ""
    h, m = divmod(secs // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _progress_bar(pct: int, width: int = 8) -> str:
    filled = round(pct / 100 * width)
    return "[#2563EB]" + "█" * filled + "[/]" + "[#1F2937]" + "░" * (width - filled) + "[/]"

CSS = """
/* ── Global ─────────────────────────────────────────── */

Screen {
    background: #060B10;
}

/* DataTable cursor rows — use !important-equivalent specificity trick */
DataTable .datatable--cursor {
    background: #0B1118;
    color: #8B949E;
}

DataTable:focus .datatable--cursor {
    background: #1D4ED8;
    color: #E5E7EB;
    text-style: bold;
}

DataTable .datatable--header {
    background: #060B10;
    color: #38BDF8;
    text-style: bold;
}

DataTable .datatable--odd-row {
    background: #060B10;
}

DataTable .datatable--even-row {
    background: #0B1118;
}

.title {
    text-align: center;
    padding: 1 2;
    color: #38BDF8;
    text-style: bold;
}

.subtitle {
    text-align: center;
    color: #8B949E;
    padding: 0 2 1 2;
}

ListView, SelectionList {
    border: solid #263241;
    margin: 1 4;
    height: auto;
    max-height: 24;
}

#lecture-list {
    height: 1fr;
    max-height: 100%;
}

#log {
    border: solid #263241;
    margin: 1 4;
    height: 1fr;
}

.button-row {
    height: auto;
    align: center middle;
    padding: 1 0;
}

Button {
    margin: 0 1;
}

.done-box {
    border: solid #22C55E;
    margin: 2 4;
    padding: 1 2;
    height: auto;
}

.stat {
    padding: 0 1;
}

/* ── Done screen ────────────────────────────────────── */

#done-outer {
    align: center middle;
    height: 1fr;
}

#done-inner {
    width: 54;
    height: auto;
}

#done-check {
    text-align: center;
    color: #22C55E;
    padding: 0 0 0 0;
}

#done-heading {
    text-align: center;
    color: #22C55E;
    text-style: bold;
    padding: 0 0 1 0;
}

#done-stats {
    padding: 0 2 1 2;
    height: auto;
}

#done-next-label {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#done-options {
    margin: 0 2 0 2;
    border: solid #263241;
    height: auto;
    padding: 0;
}

#done-options > ListItem {
    padding: 0 2;
}

#done-footer {
    dock: bottom;
    height: 3;
    border-top: solid #1F2937;
    background: #0B1118;
    padding: 0 2;
    content-align: left middle;
}

.error {
    color: #EF4444;
    text-align: center;
    padding: 1 4;
}

/* ── Splash / main-menu ──────────────────────────────── */

#splash-outer {
    align: center middle;
    height: 1fr;
}

#splash-inner {
    width: auto;
    height: auto;
    align: center middle;
}

#logo {
    text-align: center;
    padding: 1 4 0 4;
}

#tagline {
    text-align: center;
    color: #8B949E;
    padding: 0 0 1 0;
}

#menu-list {
    border: solid #263241;
    margin: 1 0;
    height: auto;
    max-height: 20;
    width: 68;
}

#menu-list > ListItem {
    padding: 0 2;
}

#splash-footer {
    dock: bottom;
    height: 3;
    border-top: solid #263241;
    background: #0B1118;
    content-align: left middle;
    padding: 0 2;
}

/* ── Browser screen ──────────────────────────────────── */

#breadcrumb {
    padding: 1 2 0 2;
    color: #8B949E;
}

#browser-icon {
    text-align: center;
    padding: 1 0 0 0;
}

#browser-description {
    text-align: center;
    color: #8B949E;
    padding: 0 4 0 4;
}

#browser-sublabel {
    text-align: center;
    padding: 1 0 0 0;
    color: #8B949E;
}

#browser-list {
    width: 66;
    border: solid #263241;
    margin: 1 0 0 0;
    height: auto;
}

#browser-list > ListItem {
    padding: 0 2;
}

#browser-info {
    width: 66;
    border: solid #263241;
    margin: 1 0 0 0;
    padding: 1 2;
    height: auto;
    color: #8B949E;
}

#browser-content {
    width: 68;
    height: auto;
}

/* ── Course screen ───────────────────────────────────── */

#course-title {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#course-desc {
    padding: 0 2 1 2;
    color: #8B949E;
}

#search-row {
    height: 3;
    border: solid #263241;
    margin: 0 2 0 2;
    padding: 0 1;
    align: left middle;
}

#search-row Input {
    border: none;
    height: 1;
    background: transparent;
    padding: 0 1;
    width: 1fr;
}

#search-hint {
    width: auto;
    color: #8B949E;
    content-align: right middle;
}

#course-count {
    padding: 0 2;
    color: #8B949E;
}

#course-loading {
    height: 1fr;
}

#course-table {
    margin: 0 2;
    height: 1fr;
    display: none;
}

/* ── Analyze screen ──────────────────────────────────── */

#analyze-course-label {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#analyze-course-title {
    padding: 0 2;
    text-style: bold;
}

#analyze-course-meta {
    padding: 0 2 1 2;
    color: #8B949E;
}

#analyze-divider {
    border-bottom: solid #1F2937;
    height: 1;
    margin: 0 2;
}

#analyze-checking {
    padding: 1 2 0 2;
    color: #8B949E;
}

#analyze-log {
    height: auto;
    max-height: 10;
    margin: 0 2;
    padding: 0;
    border: none;
}

#analyze-progress-bar {
    padding: 1 2 0 2;
}

#analyze-note {
    padding: 0 2 1 2;
    color: #8B949E;
}

#analyze-cancel {
    dock: bottom;
    height: 3;
    border: solid #263241;
    margin: 0 2 0 2;
    padding: 0 1;
    content-align: left middle;
    background: #0B1118;
}

#analyze-step {
    dock: bottom;
    height: 1;
    text-align: center;
    color: #8B949E;
    background: #060B10;
}

/* ── Section picker screen ───────────────────────────── */

#section-course-title {
    padding: 0 2;
    color: #38BDF8;
    text-style: bold;
}

#section-desc {
    padding: 0 2 1 2;
    color: #8B949E;
}

#section-table {
    margin: 0 2;
    height: 1fr;
}

#section-summary {
    padding: 1 2;
    color: #8B949E;
    border-top: solid #1F2937;
}

#section-step {
    dock: bottom;
    height: 1;
    text-align: center;
    color: #8B949E;
    background: #060B10;
}

/* ── Generate screen ────────────────────────────────── */

#gen-title {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#gen-course {
    padding: 0 2;
}

#gen-sections {
    padding: 0 2 1 2;
    color: #8B949E;
}

#gen-steps {
    padding: 0 2 1 2;
}

#gen-progress-box {
    margin: 0 2 1 2;
    border: solid #263241;
    padding: 1 2;
    height: auto;
}

#gen-note {
    padding: 0 2 1 2;
    color: #8B949E;
}

/* ── Review screen ──────────────────────────────────── */

#review-count {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#review-table {
    margin: 0 2;
    height: 1fr;
}

#review-preview-label {
    padding: 1 2 0 2;
    color: #8B949E;
}

#review-preview {
    margin: 0 2 0 2;
    border: solid #263241;
    padding: 0 2;
    height: 6;
}

#review-footer {
    dock: bottom;
    height: 3;
    border-top: solid #1F2937;
    background: #0B1118;
    padding: 0 2;
    content-align: left middle;
}

/* ── Export screen ──────────────────────────────────── */

#export-title {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#export-deck-label {
    padding: 1 2 0 2;
    color: #8B949E;
}

#export-deck-name {
    padding: 0 2 1 2;
}

#export-cards-label {
    padding: 1 2 0 2;
    color: #8B949E;
}

#export-cards-info {
    padding: 0 2 1 2;
}

#export-dest-label {
    padding: 1 2 0 2;
    color: #8B949E;
}

#export-dest-options {
    padding: 0 2 1 2;
    height: auto;
}

#export-anki-label {
    padding: 1 2 0 2;
    color: #8B949E;
}

#export-anki-status {
    padding: 0 2 1 2;
    height: auto;
}

#export-footer {
    dock: bottom;
    height: 3;
    border-top: solid #1F2937;
    background: #0B1118;
    padding: 0 2;
    content-align: left middle;
}

/* ── Edit card screen ────────────────────────────────── */

#edit-title {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#edit-front-label, #edit-back-label {
    padding: 1 2 0 2;
    color: #8B949E;
}

#edit-front, #edit-back {
    margin: 0 2;
    border: solid #263241;
}

#edit-hint {
    padding: 1 2;
    color: #8B949E;
}

/* ── Help screen ────────────────────────────────────── */

#help-outer {
    height: 1fr;
    overflow-y: auto;
    padding: 0 4 2 4;
}

#help-section-title {
    color: #38BDF8;
    text-style: bold;
    padding: 1 0 0 0;
}

#help-footer {
    dock: bottom;
    height: 3;
    border-top: solid #1F2937;
    background: #0B1118;
    padding: 0 2;
    content-align: left middle;
}

/* ── Configure screen ───────────────────────────────── */

#cfg-title {
    padding: 1 2 0 2;
    color: #38BDF8;
    text-style: bold;
}

#cfg-course {
    padding: 0 2;
}

#cfg-selection {
    padding: 0 2 1 2;
    color: #8B949E;
}

#cfg-groups {
    height: auto;
    margin: 0 2;
}

#cfg-left {
    width: 1fr;
    height: auto;
}

#cfg-right {
    width: 1fr;
    height: auto;
}

.cfg-option {
    height: 1;
}

.cfg-spacer {
    height: 1;
}

#cfg-estimate {
    margin: 1 2 0 2;
    border: solid #263241;
    padding: 0 2;
    height: 3;
    content-align: left middle;
}

/* ── SourceScreen ─────────────────────────────────────── */

#source-content {
    width: 70;
    height: auto;
    padding: 2 4;
}

#source-title {
    margin: 0 0 1 0;
}

#source-subtitle {
    margin: 0 0 2 0;
    color: #8B949E;
}

#source-list {
    height: auto;
    border: none;
}

/* ── YouTubeScreen ────────────────────────────────────── */

#yt-title {
    margin: 1 2 0 2;
}

#yt-desc {
    margin: 0 2 1 2;
    color: #8B949E;
}

#yt-input-row {
    height: 3;
    margin: 0 2;
}

#yt-url-input {
    width: 1fr;
}

#yt-status {
    margin: 0 2;
    height: 1;
}

#yt-table {
    margin: 1 2;
    height: 1fr;
}

#yt-count {
    margin: 0 2 1 2;
    color: #8B949E;
    height: 1;
}

#yt-hint {
    margin: 0 2 1 2;
    color: #3D5166;
    height: 1;
}
"""


class SplashScreen(Screen):
    TITLE = "Liksyon"

    BINDINGS = [
        Binding("enter", "select_item", "Select", show=False),
        Binding("escape", "app.exit", "Quit", show=False),
        Binding("q", "app.exit", "Quit", show=False),
    ]

    LOGO = """\
[bold #38BDF8]██╗     ██╗██╗  ██╗███████╗██╗   ██╗ ██████╗ ███╗   ██╗[/]
[bold #38BDF8]██║     ██║██║ ██╔╝██╔════╝╚██╗ ██╔╝██╔═══██╗████╗  ██║[/]
[bold #2563EB]██║     ██║█████╔╝ ███████╗ ╚████╔╝ ██║   ██║██╔██╗ ██║[/]
[bold #2563EB]██║     ██║██╔═██╗ ╚════██║  ╚██╔╝  ██║   ██║██║╚██╗██║[/]
[bold #1D4ED8]███████╗██║██║  ██╗███████║   ██║   ╚██████╔╝██║ ╚████║[/]
[bold #1D4ED8]╚══════╝╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═══╝[/]"""

    # (icon, label, description, action-key)
    MENU = [
        ("▶",  "Start New Session",  "Create flashcards from a course",    "start"),
        ("☐",  "My Sessions",        "View and continue past sessions",     "stub"),
        ("≡",  "Flashcard Library",  "Browse and manage your flashcards",   "stub"),
        ("↑",  "Import",             "Import from file or other sources",   "stub"),
        ("⚙",  "Settings",           "Configure Liksyon",                   "stub"),
        ("?",  "Help",               "Documentation and usage guide",        "help"),
        ("→",  "Quit",               "Exit Liksyon",                         "quit"),
    ]

    FOOTER = (
        " [reverse] ↑ [/] [reverse] ↓ [/] Navigate"
        "    [reverse] Enter [/] Select"
        "    [reverse] Esc [/] Quit"
        "    [reverse] ? [/] Help"
    )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Center(
            Vertical(
                Static(self.LOGO, id="logo"),
                Static(
                    "[dim]AI-powered flashcards from YouTube videos and Udemy courses[/dim]",
                    id="tagline",
                ),
                ListView(
                    *[
                        ListItem(
                            Label(
                                f" {icon}  [bold]{label:<22}[/bold]  [dim]{desc}[/dim]",
                                markup=True,
                            ),
                            id=f"menu-{i}",
                        )
                        for i, (icon, label, desc, _) in enumerate(self.MENU)
                    ],
                    id="menu-list",
                ),
                id="splash-inner",
            ),
            id="splash-outer",
        )
        yield Static(self.FOOTER, id="splash-footer")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-")[1])
        action = self.MENU[idx][3]
        if action == "start":
            self.app.push_screen(SourceScreen())
        elif action == "help":
            self.app.push_screen(HelpScreen())
        elif action == "quit":
            self.app.exit()
        else:
            self.notify("Coming soon!", severity="information")

    def action_select_item(self) -> None:
        self.query_one(ListView).action_select_cursor()


class SourceScreen(Screen):
    TITLE = "Liksyon — Select Source"

    BINDINGS = [
        Binding("escape", "back", "Back", show=False),
        Binding("q",      "back", "Back", show=False),
    ]

    SOURCES = [
        ("▶", "Udemy",   "Generate flashcards from your Udemy courses", "udemy"),
        ("▶", "YouTube", "Generate flashcards from YouTube videos",     "youtube"),
    ]

    FOOTER = (
        " [reverse] ↑ [/] [reverse] ↓ [/] Navigate"
        "    [reverse] Enter [/] Select"
        "    [reverse] Esc [/] Back"
    )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  [bold]Select Source[/]",
            id="breadcrumb",
        )
        yield Center(
            Vertical(
                Static("[bold #38BDF8]Select Source[/]", id="source-title"),
                Static(
                    "[dim]Where do you want to generate flashcards from?[/dim]",
                    id="source-subtitle",
                ),
                ListView(
                    *[
                        ListItem(
                            Label(
                                f" {icon}  [bold]{label:<12}[/bold]  [dim]{desc}[/dim]",
                                markup=True,
                            ),
                            id=f"src-{i}",
                        )
                        for i, (icon, label, desc, _) in enumerate(self.SOURCES)
                    ],
                    id="source-list",
                ),
                id="source-content",
            ),
        )
        yield Static(self.FOOTER, id="splash-footer")

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-")[1])
        _, _, _, key = self.SOURCES[idx]
        self.app.source = key
        if key == "udemy":
            self.app.push_screen(BrowserScreen())
        else:
            self.app.push_screen(YouTubeScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class YouTubeScreen(Screen):
    TITLE = "Liksyon — YouTube"

    BINDINGS = [
        Binding("escape", "back",         "Back",   show=False),
        Binding("d",      "delete_video", "Remove", show=False),
    ]

    FOOTER = (
        " [reverse] Enter [/] Add URL"
        "    [reverse] D [/] Remove selected"
        "    [reverse] Esc [/] Back"
    )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  [bold]YouTube[/]",
            id="breadcrumb",
        )
        yield Static("[bold #38BDF8]Add YouTube Videos[/]", id="yt-title")
        yield Static(
            "Paste a YouTube URL and press [bold]Enter[/bold] to add it.",
            id="yt-desc",
        )
        yield Input(
            placeholder="https://www.youtube.com/watch?v=…",
            id="yt-url-input",
        )
        yield Static("", id="yt-status")
        yield DataTable(id="yt-table", cursor_type="row")
        yield Static("", id="yt-count")
        yield Static(
            "[dim]Leave the URL field empty and press Enter to continue →[/dim]",
            id="yt-hint",
        )
        yield Static(self.FOOTER, id="splash-footer")

    def on_mount(self) -> None:
        self._videos: list[dict] = []
        t = self.query_one(DataTable)
        t.add_column("#",          width=4)
        t.add_column("Title",      width=46)
        t.add_column("Channel",    width=22)
        t.add_column("Transcript", width=12)
        self.query_one(Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        url = event.value.strip()
        if not url:
            self._do_confirm()
            return
        event.input.clear()
        await self._add_video(url)

    async def _add_video(self, url: str) -> None:
        status = self.query_one("#yt-status", Static)
        status.update("[dim]Fetching video info…[/]")
        try:
            info = await asyncio.to_thread(fetch_youtube_transcript, url)
        except Exception as exc:
            status.update(f"[bold red]✗[/] {exc}")
            return
        # Deduplicate by video_id
        existing_ids = {v["video_id"] for v in self._videos}
        if info["video_id"] in existing_ids:
            status.update("[dim]Already added.[/]")
            return
        self._videos.append(info)
        self._rebuild_table()
        title_short = info["title"][:48] + ("…" if len(info["title"]) > 48 else "")
        status.update(f"[bold #22C55E]✓[/] Added: {title_short}")

    def _rebuild_table(self) -> None:
        t = self.query_one(DataTable)
        t.clear()
        for i, v in enumerate(self._videos):
            has_t = "✓  yes" if v.get("transcript") else "✗  none"
            t.add_row(
                str(i + 1),
                (v["title"][:45] + "…" if len(v["title"]) > 45 else v["title"]),
                (v["channel"][:21] + "…" if len(v["channel"]) > 21 else v["channel"]),
                has_t,
            )
        n = len(self._videos)
        self.query_one("#yt-count", Static).update(
            f"  [bold]{n}[/] video{'s' if n != 1 else ''} added" if n else ""
        )

    def action_delete_video(self) -> None:
        t = self.query_one(DataTable)
        row = t.cursor_row
        if 0 <= row < len(self._videos):
            removed = self._videos.pop(row)
            self._rebuild_table()
            self.query_one("#yt-status", Static).update(
                f"[dim]Removed: {removed['title'][:50]}[/]"
            )

    def _do_confirm(self) -> None:
        if not self._videos:
            self.query_one("#yt-status", Static).update(
                "[dim]Add at least one video to continue.[/]"
            )
            return
        with_transcript = [v for v in self._videos if v.get("transcript")]
        if not with_transcript:
            self.query_one("#yt-status", Static).update(
                "[bold red]✗[/] No transcripts available — cannot generate cards."
            )
            return
        session_id = f"yt_{with_transcript[0]['video_id']}"
        self.app.course = {
            "title": (
                with_transcript[0]["title"]
                if len(with_transcript) == 1
                else "YouTube Videos"
            ),
            "id": session_id,
        }
        self.app.selected_lectures = [
            {
                "id":         v["id"],
                "title":      v["title"],
                "chapter":    v["channel"],
                "course_id":  session_id,
                "transcript": v["transcript"],
            }
            for v in with_transcript
        ]
        self.app.push_screen(ConfigureScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class HelpScreen(Screen):
    TITLE = "Liksyon — Help"

    BINDINGS = [
        Binding("escape", "back", "Back", show=False),
        Binding("q",      "back", "Back", show=False),
    ]

    CONTENT = """\
[bold #38BDF8]What is Liksyon?[/]

Liksyon is a terminal-based study tool that turns your Udemy courses into Anki
flashcards using AI. It fetches video transcripts, processes them with Claude,
and lets you review and export the generated cards directly into Anki.


[bold #38BDF8]How it works[/]

  [bold #38BDF8]1. Select Browser[/]    Choose the browser where you're logged into Udemy.
                    Liksyon reads your session cookies — no password needed.

  [bold #38BDF8]2. Select Course[/]     Pick any course from your Udemy library.
                    Use [reverse] / [/] to search by title or instructor.

  [bold #38BDF8]3. Select Sections[/]   Choose which sections or individual lectures to process.
                    Press [reverse] Space [/] to toggle, [reverse] Enter [/] to expand a section.

  [bold #38BDF8]4. Configure[/]         Set card style, difficulty, and cards per lecture.

  [bold #38BDF8]5. Generate[/]          Claude processes each transcript chunk and creates cards.
                    Already-processed chunks are skipped automatically on re-runs.

  [bold #38BDF8]6. Review[/]            Go through each card — keep, skip, or flag for review.
                    Press [reverse] E [/] to edit a card inline.

  [bold #38BDF8]7. Export[/]            Push cards to Anki via AnkiConnect, save as .apkg,
                    or export as CSV.


[bold #38BDF8]Global keys[/]

  [reverse] ↑ ↓ [/]      Navigate lists and tables
  [reverse] Enter [/]    Select / confirm
  [reverse] Esc [/]      Go back
  [reverse] q [/]        Quit


[bold #38BDF8]Course screen[/]

  [reverse] / [/]        Focus search bar
  [reverse] r [/]        Refresh course list
  [reverse] b [/]        Go back


[bold #38BDF8]Select Sections screen[/]

  [reverse] Space [/]    Toggle section or lecture on/off
  [reverse] → [/]        Expand section to show individual lectures
  [reverse] ← [/]        Collapse section
  [reverse] A [/]        Select all sections
  [reverse] N [/]        Deselect all
  [reverse] Enter [/]    Continue to Configure


[bold #38BDF8]Review screen[/]

  [reverse] Space [/]    Cycle card status: Keep → Skip → Review
  [reverse] E [/]        Edit card front and back
  [reverse] Enter [/]    Continue to Export
  [reverse] Esc [/]      Go back


[bold #38BDF8]AnkiConnect setup[/]

  To push cards directly into Anki:
    1. Open Anki
    2. Tools → Add-ons → Get Add-ons
    3. Enter code  2055492159  (AnkiConnect)
    4. Restart Anki
    5. Keep Anki open when you reach the Export screen


[bold #38BDF8]Notes[/]

  • Only courses you own on Udemy are processed
  • Lectures without captions are skipped
  • Cards and transcripts are cached in  data/liksyon.db
  • Exported .apkg files are saved to the  exports/  directory
  • Re-running a session skips already-processed chunks automatically
"""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Help",
            id="breadcrumb",
        )
        yield Static(self.CONTENT, id="help-outer")
        yield Static(
            " [reverse] Esc [/] Back    [reverse] q [/] Quit",
            id="help-footer",
        )

    def action_back(self) -> None:
        self.app.pop_screen()


class BrowserScreen(Screen):
    TITLE = "Liksyon — Select Browser"

    BINDINGS = [
        Binding("escape", "back", "Back", show=False),
    ]

    FOOTER = (
        " [reverse] ↑ [/] [reverse] ↓ [/] Navigate"
        "    [reverse] Enter [/] Select"
        "    [reverse] Esc [/] Back"
    )

    def compose(self) -> ComposeResult:
        browsers = _installed_browsers()
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  [bold]Select Browser[/]",
            id="breadcrumb",
        )
        yield Center(
            Vertical(
                Static("🌐", id="browser-icon"),
                Static("[bold #38BDF8]Select Browser[/]", classes="title"),
                Static(
                    "[dim]Liksyon needs access to a browser where you're logged\n"
                    "in to Udemy, so we can fetch your courses.[/dim]",
                    id="browser-description",
                ),
                Static("Choose a browser to continue:", id="browser-sublabel"),
                ListView(
                    *[
                        ListItem(
                            Label(
                                f" {icon}  [bold]{name:<20}[/bold]  [dim]{path}[/dim]",
                                markup=True,
                            ),
                            id=f"b-{key}",
                        )
                        for key, icon, name, path in browsers
                    ],
                    id="browser-list",
                ),
                Static(
                    "  ℹ   Make sure you're logged in to Udemy in the selected browser.\n"
                    "      We never see your password or personal data.",
                    id="browser-info",
                ),
                id="browser-content",
            ),
        )
        yield Static(self.FOOTER, id="splash-footer")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.app.browser = event.item.id.replace("b-", "")
        self.app.push_screen(CourseScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class CourseScreen(Screen):
    TITLE = "Liksyon — Select Course"

    BINDINGS = [
        Binding("/", "focus_search", "Search", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("b", "back", "Back", show=False),
        Binding("escape", "back", "Back", show=False),
        Binding("q", "app.exit", "Quit", show=False),
    ]

    FOOTER = (
        " [reverse] ↑ [/] [reverse] ↓ [/] Navigate"
        "    [reverse] Enter [/] Select"
        "    [reverse] / [/] Search"
        "    [reverse] r [/] Refresh"
        "    [reverse] b [/] Back"
        "    [reverse] q [/] Quit"
    )

    _display: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  Select Browser"
            "  [bold #38BDF8]›[/]  [bold]Select Course[/]",
            id="breadcrumb",
        )
        yield Static("Select a Udemy Course", id="course-title")
        yield Static(
            "We found the following courses in your Udemy account.\n"
            "Choose the course you want to generate flashcards from.",
            id="course-desc",
        )
        yield Horizontal(
            Static("🔍 "),
            Input(placeholder="Search courses...", id="course-search"),
            Static("(Press / to focus)", id="search-hint"),
            id="search-row",
        )
        yield Static("", id="course-count")
        yield LoadingIndicator(id="course-loading")
        yield DataTable(id="course-table", cursor_type="row")
        yield Static(self.FOOTER, id="splash-footer")

    def on_mount(self) -> None:
        t = self.query_one(DataTable)
        t.add_column("#",           width=4)
        t.add_column("Course Title",width=38)
        t.add_column("Instructor",  width=22)
        t.add_column("Duration",    width=9)
        t.add_column("Progress",    width=15)
        t.add_column("Transcript",  width=13)
        self.run_worker(self._load(), exclusive=True)

    async def _load(self) -> None:
        self.query_one("#course-count", Static).update("Loading courses…")
        self.query_one("#course-loading").display = True
        self.query_one("#course-table").display = False
        try:
            courses = await asyncio.to_thread(self._fetch)
            self.app.courses = courses
            self._repopulate(courses)
        except Exception as e:
            self.notify(str(e), severity="error", timeout=10)
            self.query_one("#course-count", Static).update("Error loading courses.")
        finally:
            self.query_one("#course-loading").display = False
            self.query_one("#course-table").display = True

    def _fetch(self) -> list[dict]:
        scraper = UdemyScraper(browser=self.app.browser)
        cookies = load_browser_cookies(self.app.browser)
        scraper.session.cookies.update(cookies)
        self.app.scraper = scraper
        if not scraper.is_logged_in():
            raise RuntimeError("Not logged in. Please log into Udemy in your browser first.")
        return scraper.get_owned_courses()

    def _repopulate(self, courses: list[dict]) -> None:
        t = self.query_one(DataTable)
        t.clear()
        self._display = courses
        for i, c in enumerate(courses):
            pct = int(c.get("completion_ratio", 0) or 0)
            bar = _progress_bar(pct)
            progress = f"{pct}%  {bar}"
            vis = c.get("visible_instructors") or []
            instructor = vis[0].get("display_name", "") if vis else ""
            duration = _fmt_duration(c.get("content_info", ""))
            t.add_row(
                str(i + 1),
                c.get("title", ""),
                instructor,
                duration,
                progress,
                "[green]✓[/green] Available",
                key=str(c["id"]),
            )
        self.query_one("#course-count", Static).update(f"Found {len(courses)} courses")
        self.query_one("#course-table", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        q = event.value.lower()
        if not q:
            self._repopulate(self.app.courses or [])
            return
        filtered = [
            c for c in (self.app.courses or [])
            if q in c.get("title", "").lower()
            or q in (c.get("visible_instructors") or [{}])[0].get("display_name", "").lower()
        ]
        self._repopulate(filtered)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        course_id = str(event.row_key.value)
        course = next((c for c in self._display if str(c["id"]) == course_id), None)
        if course:
            self.app.course = course
            self.app.all_lectures = []  # clear so AnalyzeScreen re-fetches
            self.app.push_screen(AnalyzeCourseScreen())

    def action_focus_search(self) -> None:
        self.query_one("#course-search", Input).focus()

    def action_refresh(self) -> None:
        self.run_worker(self._load(), exclusive=True)

    def action_back(self) -> None:
        self.app.pop_screen()


class AnalyzeCourseScreen(Screen):
    TITLE = "Liksyon — Analyze Course"

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        course = self.app.course
        vis = course.get("visible_instructors") or []
        instructor = vis[0].get("display_name", "") if vis else ""
        pct = int(course.get("completion_ratio", 0) or 0)
        duration = _fmt_duration(course.get("content_info", ""))

        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  Select Course"
            "  [bold #38BDF8]›[/]  [bold]Analyze Course[/]",
            id="breadcrumb",
        )
        yield Static("[bold #38BDF8]Selected Course:[/]", id="analyze-course-label")
        yield Static(course.get("title", ""), id="analyze-course-title")
        yield Static(
            f"{instructor}  •  {duration}  •  {pct}% watched",
            id="analyze-course-meta",
        )
        yield Static("", id="analyze-divider")
        yield Static("Checking course content...", id="analyze-checking")
        yield RichLog(id="analyze-log", highlight=False, markup=True, auto_scroll=True)
        yield Static("", id="analyze-progress-bar")
        yield Static("[dim]This may take a few moments.[/dim]", id="analyze-note")
        yield Static(" [reverse] Esc [/] Cancel", id="analyze-cancel")
        yield Static("1. Analyzing Course", id="analyze-step")

    def on_mount(self) -> None:
        self.run_worker(self._analyze(), exclusive=True)

    async def _analyze(self) -> None:
        log = self.query_one("#analyze-log", RichLog)
        bar_widget = self.query_one("#analyze-progress-bar", Static)

        def set_bar(pct: int) -> None:
            w = 20
            filled = round(pct / 100 * w)
            bar = "[bold #1a6ca8]" + "█" * filled + "[/]" + "[#2a3a4a]" + "█" * (w - filled) + "[/]"
            bar_widget.update(f" {bar}  [bold]{pct}%[/bold]")

        try:
            log.write("  [green]●[/green] Course found")
            set_bar(15)
            await asyncio.sleep(0.1)

            scraper = self.app.scraper
            course_id = str(self.app.course["id"])
            set_bar(30)

            results = await asyncio.to_thread(scraper.get_course_structure, course_id)
            set_bar(60)

            lectures = scraper.build_lecture_list(results)
            sections = {lec["chapter"] for lec in lectures}
            has_transcript = any(lec.get("caption_url") for lec in lectures)

            if has_transcript:
                log.write("  [green]●[/green] Transcript available")
            else:
                log.write("  [yellow]⚠[/yellow] No transcripts detected")

            set_bar(72)
            log.write(f"  [green]●[/green] {len(lectures)} lectures detected")
            log.write(f"  [green]●[/green] {len(sections)} sections detected")
            set_bar(90)
            log.write(f"  [bold #38BDF8]→[/bold #38BDF8] [bold #38BDF8]Preparing section list[/bold #38BDF8]")

            self.app.all_lectures = lectures
            set_bar(100)
            await asyncio.sleep(0.4)
            self.app.push_screen(LectureScreen())

        except Exception as e:
            self.notify(str(e), severity="error", timeout=15)

    def action_cancel(self) -> None:
        self.app.pop_screen()


class LectureScreen(Screen):
    TITLE = "Liksyon — Select Sections"

    BINDINGS = [
        Binding("space",  "toggle_row",       "Toggle",      show=False),
        Binding("right",  "expand_section",   "Expand",      show=False),
        Binding("left",   "collapse_section", "Collapse",    show=False),
        Binding("a",      "select_all",       "Select All",  show=False),
        Binding("n",      "select_none",      "Select None", show=False),
        Binding("enter",  "confirm",          "Continue",    show=False, priority=True),
        Binding("escape", "back",             "Back",        show=False),
    ]

    FOOTER = (
        " [reverse] ↑ [/] [reverse] ↓ [/] Navigate"
        "    [reverse] Space [/] Toggle"
        "    [reverse] → [/] Expand  [reverse] ← [/] Collapse"
        "    [reverse] A [/] All  [reverse] N [/] None"
        "    [reverse] Enter [/] Continue"
        "    [reverse] Esc [/] Back"
    )

    def compose(self) -> ComposeResult:
        course = self.app.course
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  Select Course"
            "  [bold #38BDF8]›[/]  [bold]Select Sections[/]",
            id="breadcrumb",
        )
        yield Static(
            f"[bold #38BDF8]{course.get('title', '')}[/]",
            id="section-course-title",
        )
        yield Static("Choose which sections to include:", id="section-desc")
        yield DataTable(id="section-table", cursor_type="row")
        yield Static("", id="section-summary")
        yield Static(self.FOOTER, id="splash-footer")
        yield Static("2. Select Sections", id="section-step")

    def on_mount(self) -> None:
        self._sections = self._build_sections()
        self._selected: set[int] = set()
        self._lecture_selections: dict[int, set[int]] = {}
        self._expanded: set[int] = set()
        self._focused_key: str = "s0" if self._sections else ""
        self._row_order: list[str] = []
        self._rk: dict = {}

        t = self.query_one(DataTable)
        self._col_sel = t.add_column("Sel",        width=5)
        self._col_sec = t.add_column("Section",    width=34)
        self._col_cnt = t.add_column("Lectures",   width=9)
        self._col_dur = t.add_column("Duration",   width=8)
        self._col_tr  = t.add_column("Transcript", width=13)

        self._rebuild_table()
        self._update_summary()

    def _build_sections(self) -> list[dict]:
        seen: dict[str, dict] = {}
        order: list[str] = []
        for lec in (self.app.all_lectures or []):
            ch = lec["chapter"]
            if ch not in seen:
                seen[ch] = {"title": ch, "lectures": [], "has_transcript": False, "duration": 0}
                order.append(ch)
            seen[ch]["lectures"].append(lec)
            seen[ch]["duration"] += lec.get("duration", 0)
            if lec.get("caption_url"):
                seen[ch]["has_transcript"] = True
        return [seen[k] for k in order]

    def _parse_key(self, key: str) -> tuple:
        if "-l" in key:
            si, li = key.split("-l")
            return ("lecture", int(si[1:]), int(li))
        return ("section", int(key[1:]))

    def _is_lecture_selected(self, si: int, li: int) -> bool:
        if si not in self._selected:
            return False
        if si in self._lecture_selections:
            return li in self._lecture_selections[si]
        return True

    def _sec_sel_str(self, idx: int, focused: bool = False) -> Text:
        arrow = "> " if focused else "  "
        if idx not in self._selected:
            box = "[ ]"
        elif idx in self._lecture_selections:
            n_custom = len(self._lecture_selections[idx])
            n_total  = len(self._sections[idx]["lectures"])
            box = "[x]" if n_custom >= n_total else "[~]"
        else:
            box = "[x]"
        return Text(f"{arrow}{box}", no_wrap=True)

    def _sec_title_cell(self, idx: int, expanded: bool = False) -> Text:
        title = self._sections[idx]["title"]
        t = Text(no_wrap=True)
        t.append("▼ " if expanded else "▶ ", style="bold #38BDF8" if expanded else "dim")
        t.append(title)
        return t

    def _lec_sel_str(self, si: int, li: int, focused: bool = False) -> Text:
        arrow = "> " if focused else "  "
        box = "[x]" if self._is_lecture_selected(si, li) else "[ ]"
        return Text(f"{arrow}{box}", no_wrap=True)

    def _lec_title_cell(self, title: str) -> Text:
        t = Text(no_wrap=True)
        t.append("  ↳ ", style="dim")
        t.append(title)
        return t

    def _rebuild_table(self) -> None:
        t = self.query_one(DataTable)
        t.clear()
        self._row_order = []
        self._rk = {}

        for i, sec in enumerate(self._sections):
            key = f"s{i}"
            is_focused = key == self._focused_key
            expanded = i in self._expanded
            transcript = (
                "[green]✓ Available[/green]" if sec["has_transcript"]
                else "[dim]None[/dim]"
            )
            rk = t.add_row(
                self._sec_sel_str(i, is_focused),
                self._sec_title_cell(i, expanded),
                str(len(sec["lectures"])),
                _fmt_secs(sec.get("duration", 0)),
                transcript,
                key=key,
            )
            self._row_order.append(key)
            self._rk[key] = rk

            if expanded:
                for j, lec in enumerate(sec["lectures"]):
                    lkey = f"s{i}-l{j}"
                    is_lec_focused = lkey == self._focused_key
                    tr = (
                        "[green]✓[/green]" if lec.get("caption_url")
                        else "[dim]—[/dim]"
                    )
                    lrk = t.add_row(
                        self._lec_sel_str(i, j, is_lec_focused),
                        self._lec_title_cell(lec["title"]),
                        "",
                        _fmt_secs(lec.get("duration", 0)),
                        tr,
                        key=lkey,
                    )
                    self._row_order.append(lkey)
                    self._rk[lkey] = lrk

        if self._focused_key in self._row_order:
            t.move_cursor(row=self._row_order.index(self._focused_key))
        elif self._row_order:
            self._focused_key = self._row_order[0]
            t.move_cursor(row=0)

    def _update_summary(self) -> None:
        n_sec = len(self._selected)
        n_lec = sum(
            len(self._lecture_selections[i]) if i in self._lecture_selections
            else len(self._sections[i]["lectures"])
            for i in self._selected
        )
        lo, hi = max(1, round(n_lec * 1.3)), round(n_lec * 2.1)
        self.query_one("#section-summary", Static).update(
            f"  Selected: [bold]{n_sec} sections[/bold]"
            f"  •  [bold]{n_lec} lectures[/bold]"
            f"  •  [dim]est. {lo}–{hi} flashcards[/dim]"
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        new_row = event.cursor_row
        if not (0 <= new_row < len(self._row_order)):
            return
        new_key = self._row_order[new_row]
        prev_key = self._focused_key
        if prev_key == new_key:
            return

        t = self.query_one(DataTable)

        if prev_key in self._rk:
            info = self._parse_key(prev_key)
            if info[0] == "section":
                t.update_cell(self._rk[prev_key], self._col_sel, self._sec_sel_str(info[1], False))
            else:
                t.update_cell(self._rk[prev_key], self._col_sel, self._lec_sel_str(info[1], info[2], False))

        if new_key in self._rk:
            info = self._parse_key(new_key)
            if info[0] == "section":
                t.update_cell(self._rk[new_key], self._col_sel, self._sec_sel_str(info[1], True))
            else:
                t.update_cell(self._rk[new_key], self._col_sel, self._lec_sel_str(info[1], info[2], True))

        self._focused_key = new_key

    def action_toggle_row(self) -> None:
        key = self._focused_key
        if not key:
            return
        info = self._parse_key(key)
        t = self.query_one(DataTable)

        if info[0] == "section":
            si = info[1]
            if si in self._selected:
                self._selected.discard(si)
                self._lecture_selections.pop(si, None)
            else:
                self._selected.add(si)
            t.update_cell(self._rk[key], self._col_sel, self._sec_sel_str(si, True))
            if si in self._expanded:
                for j in range(len(self._sections[si]["lectures"])):
                    lkey = f"s{si}-l{j}"
                    if lkey in self._rk:
                        t.update_cell(self._rk[lkey], self._col_sel, self._lec_sel_str(si, j, False))
        else:
            si, li = info[1], info[2]
            n_total = len(self._sections[si]["lectures"])
            if si not in self._lecture_selections:
                self._lecture_selections[si] = (
                    set(range(n_total)) if si in self._selected else set()
                )
            lset = self._lecture_selections[si]
            if li in lset:
                lset.discard(li)
            else:
                lset.add(li)
            if len(lset) == 0:
                self._selected.discard(si)
                self._lecture_selections.pop(si, None)
            elif len(lset) == n_total:
                self._selected.add(si)
                self._lecture_selections.pop(si, None)
            else:
                self._selected.add(si)
            t.update_cell(self._rk[key], self._col_sel, self._lec_sel_str(si, li, True))
            skey = f"s{si}"
            if skey in self._rk:
                t.update_cell(self._rk[skey], self._col_sel, self._sec_sel_str(si, False))

        self._update_summary()

    def action_expand_section(self) -> None:
        key = self._focused_key
        if not key:
            return
        si = self._parse_key(key)[1]
        if si not in self._expanded:
            self._expanded.add(si)
            self._focused_key = f"s{si}"
            self._rebuild_table()

    def action_collapse_section(self) -> None:
        key = self._focused_key
        if not key:
            return
        si = self._parse_key(key)[1]
        if si in self._expanded:
            self._expanded.discard(si)
            self._focused_key = f"s{si}"
            self._rebuild_table()

    def action_select_all(self) -> None:
        self._selected = set(range(len(self._sections)))
        self._lecture_selections.clear()
        t = self.query_one(DataTable)
        for key in self._row_order:
            info = self._parse_key(key)
            focused = key == self._focused_key
            if info[0] == "section":
                t.update_cell(self._rk[key], self._col_sel, self._sec_sel_str(info[1], focused))
            else:
                t.update_cell(self._rk[key], self._col_sel, self._lec_sel_str(info[1], info[2], focused))
        self._update_summary()

    def action_select_none(self) -> None:
        self._selected = set()
        self._lecture_selections.clear()
        t = self.query_one(DataTable)
        for key in self._row_order:
            info = self._parse_key(key)
            focused = key == self._focused_key
            if info[0] == "section":
                t.update_cell(self._rk[key], self._col_sel, self._sec_sel_str(info[1], focused))
            else:
                t.update_cell(self._rk[key], self._col_sel, self._lec_sel_str(info[1], info[2], focused))
        self._update_summary()

    def action_confirm(self) -> None:
        if not self._selected:
            self.notify("Select at least one section.", severity="warning")
            return
        lectures = []
        for i in sorted(self._selected):
            sec = self._sections[i]
            if i in self._lecture_selections:
                lectures.extend(sec["lectures"][j] for j in sorted(self._lecture_selections[i]))
            else:
                lectures.extend(sec["lectures"])
        self.app.selected_lectures = lectures
        self.app.push_screen(ConfigureScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class _RadioOption(Static):
    """Single clickable radio option row."""

    can_focus = False

    def __init__(self, group_idx: int, opt_idx: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self._group_idx = group_idx
        self._opt_idx = opt_idx

    def on_click(self) -> None:
        screen = self.screen
        if isinstance(screen, ConfigureScreen):
            screen.select_option(self._group_idx, self._opt_idx)


class ConfigureScreen(Screen):
    TITLE = "Liksyon — Configure"

    BINDINGS = [
        Binding("up",     "prev_option", "Navigate", show=False, priority=True),
        Binding("down",   "next_option", "Navigate", show=False, priority=True),
        Binding("left",   "prev_group",  "Change",   show=False, priority=True),
        Binding("right",  "next_group",  "Change",   show=False, priority=True),
        Binding("enter",  "confirm",     "Generate", show=False, priority=True),
        Binding("escape", "back",        "Back",     show=False),
    ]

    FOOTER = (
        " [reverse] ↑↓ [/] Change option"
        "    [reverse] ←→ [/] Switch group"
        "    [reverse] Enter [/] Generate"
        "    [reverse] Esc [/] Back"
    )

    _GROUPS = [
        ("Card style:",   ["Basic Q&A", "Cloze deletion", "Mixed"]),
        ("Difficulty:",   ["Beginner", "Intermediate", "Advanced"]),
        ("Card density:", ["Light (fewer cards)", "Balanced (recommended)", "Detailed (more cards)"]),
        ("Output:",       ["Push to Anki", "Export .apkg", "Export CSV"]),
    ]
    _DEFAULTS = [0, 1, 1, 0]

    def compose(self) -> ComposeResult:
        course  = self.app.course
        source  = getattr(self.app, "source", "udemy")
        src_lbl = "YouTube" if source == "youtube" else "Select Course"
        yield Header()
        yield Static(
            f"Start New Session  [bold #38BDF8]›[/]  {src_lbl}"
            "  [bold #38BDF8]›[/]  [bold]Configure[/]",
            id="breadcrumb",
        )
        yield Static("[bold #38BDF8]Flashcard Settings[/]", id="cfg-title")
        yield Static(f"Course: {course.get('title', '')}", id="cfg-course")
        yield Static("", id="cfg-selection")
        with Horizontal(id="cfg-groups"):
            with Vertical(id="cfg-left"):
                for gi in (0, 2):
                    yield Static(
                        f"[bold #38BDF8]{self._GROUPS[gi][0]}[/]",
                        id=f"cfg-lbl-{gi}",
                    )
                    for oi in range(len(self._GROUPS[gi][1])):
                        yield _RadioOption(gi, oi, classes="cfg-option", id=f"cfg-opt-{gi}-{oi}")
                    yield Static("", classes="cfg-spacer")
            with Vertical(id="cfg-right"):
                for gi in (1, 3):
                    yield Static(
                        f"[bold #38BDF8]{self._GROUPS[gi][0]}[/]",
                        id=f"cfg-lbl-{gi}",
                    )
                    for oi in range(len(self._GROUPS[gi][1])):
                        yield _RadioOption(gi, oi, classes="cfg-option", id=f"cfg-opt-{gi}-{oi}")
                    yield Static("", classes="cfg-spacer")
        yield Static("", id="cfg-estimate")
        yield Static(self.FOOTER, id="splash-footer")

    def on_mount(self) -> None:
        self._selections = list(self._DEFAULTS)
        self._focused = 0

        lectures = self.app.selected_lectures or []
        sections = len({l["chapter"] for l in lectures})
        self.query_one("#cfg-selection", Static).update(
            f"Selected: [bold]{sections} sections[/bold]  •  [bold]{len(lectures)} lectures[/bold]"
        )
        self._render_all()

    def _opt_text(self, gi: int, oi: int) -> str:
        selected = oi == self._selections[gi]
        focused  = gi == self._focused
        opt = self._GROUPS[gi][1][oi]
        dot    = "◉" if selected else "○"
        cursor = "> " if (selected and focused) else "  "
        if selected and focused:
            return f"{cursor}[bold #38BDF8]{dot} {opt}[/]"
        elif selected:
            return f"  [#38BDF8]{dot} {opt}[/]"
        else:
            return f"  [dim]{dot}[/] {opt}"

    def _render_all(self) -> None:
        for gi in range(4):
            for oi in range(len(self._GROUPS[gi][1])):
                self.query_one(f"#cfg-opt-{gi}-{oi}", _RadioOption).update(self._opt_text(gi, oi))
        self._update_estimate()

    def _update_estimate(self) -> None:
        lectures = self.app.selected_lectures or []
        n = len(lectures)
        multipliers = [(1.0, 1.5), (1.3, 2.1), (1.8, 3.0)]
        lo_m, hi_m = multipliers[self._selections[2]]
        lo, hi = max(1, round(n * lo_m)), round(n * hi_m)
        self.query_one("#cfg-estimate", Static).update(
            f"  Estimated output: [bold]{lo}–{hi} flashcards[/bold]"
        )

    def select_option(self, gi: int, oi: int) -> None:
        self._focused = gi
        self._selections[gi] = oi
        self._render_all()

    def action_prev_group(self) -> None:
        self._focused = (self._focused - 1) % len(self._GROUPS)
        self._render_all()

    def action_next_group(self) -> None:
        self._focused = (self._focused + 1) % len(self._GROUPS)
        self._render_all()

    def action_prev_option(self) -> None:
        options = self._GROUPS[self._focused][1]
        self._selections[self._focused] = (self._selections[self._focused] - 1) % len(options)
        self._render_all()

    def action_next_option(self) -> None:
        options = self._GROUPS[self._focused][1]
        self._selections[self._focused] = (self._selections[self._focused] + 1) % len(options)
        self._render_all()

    def action_confirm(self) -> None:
        self.app.config = {
            "card_style":   self._GROUPS[0][1][self._selections[0]],
            "difficulty":   self._GROUPS[1][1][self._selections[1]],
            "card_density": self._GROUPS[2][1][self._selections[2]],
            "output":       self._GROUPS[3][1][self._selections[3]],
        }
        self.app.push_screen(ProcessScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class ProcessScreen(Screen):
    TITLE = "Liksyon — Generate"

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
    ]

    _STEPS = [
        "Fetching transcripts",
        "Cleaning transcript text",
        "Splitting into chunks",
        "Generating flashcards with Claude",
        "Validating cards",
        "Preparing Anki deck",
    ]

    def compose(self) -> ComposeResult:
        course   = self.app.course
        lectures = self.app.selected_lectures or []
        chapters = list(dict.fromkeys(l["chapter"] for l in lectures))
        ch_str   = ", ".join(chapters[:4])
        if len(chapters) > 4:
            ch_str += f"  +{len(chapters) - 4} more"

        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  [bold]Generate[/]",
            id="breadcrumb",
        )
        yield Static("[bold #38BDF8]Generating flashcards...[/]", id="gen-title")
        yield Static(f"Course: {course.get('title', '')}", id="gen-course")
        yield Static(f"Sections: {ch_str}", id="gen-sections")
        yield Static("", id="gen-steps")
        with Container(id="gen-progress-box"):
            yield Static("", id="gen-chunk-line")
            yield Static("", id="gen-card-line")
            yield Static("", id="gen-bar-line")
        yield Static("This may take a few minutes.", id="gen-note")
        yield Static(" [reverse] Esc [/] Cancel", id="splash-footer")

    def on_mount(self) -> None:
        self._step          = 0
        self._step_detail   = ""
        self._chunks_done   = 0
        self._chunks_total  = 0
        self._cards_done    = 0
        self._skipped       = 0
        self._chunk_running = False
        self._update_steps()
        self._update_progress()
        self._worker = self.run_worker(self._run(), exclusive=True)

    def _update_steps(self) -> None:
        lines = []
        for i, label in enumerate(self._STEPS):
            if i < self._step:
                lines.append(f"  [green]⊙[/] {label}")
            elif i == self._step:
                detail = f"  [dim]{self._step_detail}[/]" if self._step_detail else ""
                lines.append(f"  [bold #38BDF8]→[/] [bold #38BDF8]{label}[/]{detail}")
            else:
                lines.append(f"  [dim]·[/dim] {label}")
        self.query_one("#gen-steps", Static).update("\n".join(lines))

    def _update_progress(self) -> None:
        if self._chunks_total == 0:
            self.query_one("#gen-chunk-line", Static).update("[dim]Fetching transcripts…[/]")
            self.query_one("#gen-card-line", Static).update("")
            self.query_one("#gen-bar-line", Static).update("")
            return
        if self._chunks_done == 0:
            chunk_line = f"Chunk [bold]–[/] of [bold]{self._chunks_total}[/]"
        else:
            chunk_line = f"Chunk [bold]{self._chunks_done}[/] of [bold]{self._chunks_total}[/]"
        self.query_one("#gen-chunk-line", Static).update(chunk_line)
        card_line = f"Generated: [bold]{self._cards_done} cards[/]"
        if self._skipped:
            card_line += f"  [dim]Skipped: {self._skipped} low-quality chunks[/]"
        self.query_one("#gen-card-line", Static).update(card_line)
        pct = round(self._chunks_done / self._chunks_total * 100) if self._chunks_done else 0
        bar_label = f"[dim]Claude running…[/]" if self._chunks_done == 0 or self._chunk_running else f"[bold]{pct}%[/]"
        self.query_one("#gen-bar-line", Static).update(
            f"{_progress_bar(pct, width=24)}  {bar_label}"
        )

    async def _run(self) -> None:
        def set_step(i: int, detail: str = "") -> None:
            self._step        = i
            self._step_detail = detail
            self.app.call_from_thread(self._update_steps)

        def on_progress(done: int, total: int, cards: int, skipped: int = 0) -> None:
            self._chunks_done  = done
            self._chunks_total = total
            self._cards_done   = cards
            self._skipped      = skipped
            self.app.call_from_thread(self._update_progress)

        try:
            await asyncio.to_thread(self._pipeline, set_step, on_progress)
            await asyncio.sleep(5)
            self.app.push_screen(ReviewScreen())
        except Exception as e:
            self.notify(str(e), severity="error", timeout=30)

    def _pipeline(self, set_step, on_progress) -> dict:
        scraper   = self.app.scraper
        course    = self.app.course
        lectures  = self.app.selected_lectures
        course_id = str(course["id"])

        set_step(0)

        if scraper is not None:
            # Udemy: fetch transcripts via the scraper
            def fetch_cb(done: int, total: int, title: str) -> None:
                set_step(0, f"{done}/{total}  {title}")
            transcripts = scraper.scrape_lectures(lectures, course_id, progress_cb=fetch_cb)
        else:
            # YouTube (or any pre-fetched source): transcripts already in selected_lectures
            transcripts = lectures

        set_step(1)
        for t in transcripts:
            save_transcript(t, course_title=course["title"])

        set_step(2)

        set_step(3, "invoking Claude Code CLI per chunk…")

        # prime the progress box with chunk count before Claude starts
        from liksyon.chunker import chunk_transcript as _chunk
        valid = [t for t in transcripts if t.get("transcript")]
        total_chunks_pre = sum(len(_chunk(t["transcript"])) for t in valid)
        if total_chunks_pre:
            self._chunks_total = total_chunks_pre
            self.app.call_from_thread(self._update_progress)

        def on_chunk_start(chunk_idx: int, total: int) -> None:
            self._chunk_running = True
            self._chunks_done   = chunk_idx
            self._chunks_total  = total
            self.app.call_from_thread(self._update_progress)

        def on_chunk_done(done: int, total: int, cards: int, skipped: int = 0) -> None:
            self._chunk_running = False
            on_progress(done, total, cards, skipped)

        run_agent(
            transcripts,
            course_title=course["title"],
            config=self.app.config,
            progress_cb=on_chunk_done,
            chunk_start_cb=on_chunk_start,
        )
        selected_ids = {l["id"] for l in (self.app.selected_lectures or [])}
        session_cards = [
            c for c in get_flashcards(course_id)
            if c["lecture_id"] in selected_ids
        ]
        on_progress(
            self._chunks_total or total_lec,
            self._chunks_total or total_lec,
            len(session_cards),
            self._skipped,
        )

        set_step(4)
        time.sleep(1)

        set_step(5)
        time.sleep(1)

    def action_cancel(self) -> None:
        self._worker.cancel()
        self.app.pop_screen()


class EditCardScreen(Screen):
    TITLE = "Liksyon — Edit Card"

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, card: dict) -> None:
        super().__init__()
        self._card = card

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Review Cards  [bold #38BDF8]›[/]  [bold]Edit Card[/]",
            id="breadcrumb",
        )
        yield Static("[bold #38BDF8]Edit Flashcard[/]", id="edit-title")
        yield Static("Front (Question):", id="edit-front-label")
        yield Input(value=self._card["front"], id="edit-front")
        yield Static("Back (Answer):", id="edit-back-label")
        yield Input(value=self._card["back"], id="edit-back")
        yield Static(
            "  [dim]Tab[/dim] switch field   [dim]Enter[/dim] save   [dim]Esc[/dim] cancel",
            id="edit-hint",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "edit-front":
            self.query_one("#edit-back", Input).focus()
        else:
            self._save()

    def _save(self) -> None:
        front = self.query_one("#edit-front", Input).value.strip()
        back  = self.query_one("#edit-back",  Input).value.strip()
        if not front or not back:
            self.notify("Front and back cannot be empty.", severity="warning")
            return
        update_flashcard(self._card["id"], front, back)
        self.dismiss({"front": front, "back": back})

    def action_cancel(self) -> None:
        self.dismiss(None)


_STATUS_CYCLE = ["keep", "skip", "review"]
_STATUS_LABEL = {
    "keep":   "[green]Keep[/]",
    "skip":   "[dim]Skip[/]",
    "review": "[yellow]Review[/]",
}


class ReviewScreen(Screen):
    TITLE = "Liksyon — Review Cards"

    BINDINGS = [
        Binding("space",  "toggle_status", "Keep/Skip", show=False, priority=True),
        Binding("e",      "edit_card",     "Edit",      show=False),
        Binding("enter",  "confirm",       "Continue",  show=False, priority=True),
        Binding("escape", "back",          "Back",      show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  [bold]Review Cards[/]",
            id="breadcrumb",
        )
        yield Static("", id="review-count")
        yield DataTable(id="review-table", cursor_type="row")
        yield Static("[bold #38BDF8]Preview:[/]", id="review-preview-label")
        yield Static("", id="review-preview")
        yield Static(
            " [reverse] ↑↓ [/] Navigate"
            "    [reverse] Space [/] Keep/Skip/Review"
            "    [reverse] E [/] Edit"
            "    [reverse] Enter [/] Continue"
            "    [reverse] Esc [/] Back",
            id="review-footer",
        )

    def on_mount(self) -> None:
        course_id    = str(self.app.course["id"])
        selected_ids = {l["id"] for l in (self.app.selected_lectures or [])}
        self._cards  = [
            c for c in get_flashcards(course_id)
            if c["lecture_id"] in selected_ids
        ]
        card_style  = self.app.config.get("card_style", "Basic Q&A")

        self._status: dict[int, str] = {c["id"]: "keep" for c in self._cards}
        self._focused_row = 0
        self._rk: dict[int, object] = {}

        self.query_one("#review-count", Static).update(
            f"[bold #38BDF8]Generated {len(self._cards)} flashcards[/]"
        )

        t = self.query_one(DataTable)
        self._col_num    = t.add_column("#",        width=4)
        self._col_q      = t.add_column("Question", width=38)
        self._col_type   = t.add_column("Type",     width=12)
        self._col_status = t.add_column("Status",   width=8)

        for i, card in enumerate(self._cards):
            rk = t.add_row(
                Text(f"> {i+1}" if i == 0 else f"  {i+1}", no_wrap=True),
                card["front"],
                card_style,
                _STATUS_LABEL["keep"],
                key=str(card["id"]),
            )
            self._rk[card["id"]] = rk

        if self._cards:
            self._update_preview(0)

    def _update_preview(self, row: int) -> None:
        if not (0 <= row < len(self._cards)):
            return
        card = self._cards[row]
        self.query_one("#review-preview", Static).update(
            f"[bold]Q:[/] {card['front']}\n[bold]A:[/] {card['back']}"
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        t   = self.query_one(DataTable)
        prev, new = self._focused_row, event.cursor_row
        if prev != new:
            if 0 <= prev < len(self._cards):
                c = self._cards[prev]
                t.update_cell(self._rk[c["id"]], self._col_num, Text(f"  {prev+1}", no_wrap=True))
            if 0 <= new < len(self._cards):
                c = self._cards[new]
                t.update_cell(self._rk[c["id"]], self._col_num, Text(f"> {new+1}", no_wrap=True))
        self._focused_row = new
        self._update_preview(new)

    def action_toggle_status(self) -> None:
        if not self._cards:
            return
        card = self._cards[self._focused_row]
        cid  = card["id"]
        cur  = self._status[cid]
        nxt  = _STATUS_CYCLE[((_STATUS_CYCLE.index(cur)) + 1) % len(_STATUS_CYCLE)]
        self._status[cid] = nxt
        t = self.query_one(DataTable)
        t.update_cell(self._rk[cid], self._col_status, _STATUS_LABEL[nxt])

    def action_edit_card(self) -> None:
        if not self._cards:
            return
        card = self._cards[self._focused_row]
        row  = self._focused_row

        def on_return(result: dict | None) -> None:
            if result is None:
                return
            self._cards[row] = {**self._cards[row], **result}
            t = self.query_one(DataTable)
            t.update_cell(self._rk[card["id"]], self._col_q, result["front"])
            self._update_preview(row)

        self.app.push_screen(EditCardScreen(card), on_return)

    def action_confirm(self) -> None:
        kept    = [c for c in self._cards if self._status[c["id"]] in ("keep", "review")]
        skipped = [c for c in self._cards if self._status[c["id"]] == "skip"]
        if not kept:
            self.notify("Keep at least one card.", severity="warning")
            return
        self.app.push_screen(ExportScreen(kept, skipped))

    def action_back(self) -> None:
        self.app.pop_screen()


class ExportScreen(Screen):
    TITLE = "Liksyon — Export"

    _DESTINATIONS = [
        "Anki via AnkiConnect",
        "Export .apkg",
        "Export CSV",
    ]

    BINDINGS = [
        Binding("up",     "move_up",   "", show=False, priority=True),
        Binding("down",   "move_down", "", show=False, priority=True),
        Binding("enter",  "export",    "Export",      show=False, priority=True),
        Binding("escape", "back",      "Back",        show=False),
    ]

    def __init__(self, kept: list[dict], skipped: list[dict]) -> None:
        super().__init__()
        self._kept    = kept
        self._skipped = skipped
        self._dest    = 0  # selected destination index
        self._anki_installed  = False
        self._ankiconnect_ok  = False

    def _deck_name(self) -> str:
        return f"{self.app.course.get('title', '')} - Liksyon"

    def _footer_label(self) -> str:
        labels = ["Push to Anki", "Save .apkg", "Save .csv"]
        return labels[self._dest]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  [bold]Export[/]",
            id="breadcrumb",
        )
        yield Static("[bold #38BDF8]Ready to Export[/]", id="export-title")

        yield Static("Deck name:", id="export-deck-label")
        yield Static(self._deck_name(), id="export-deck-name")

        yield Static("Cards:", id="export-cards-label")
        yield Static("", id="export-cards-info")

        yield Static("Destination:", id="export-dest-label")
        yield Static("", id="export-dest-options")

        yield Static("Anki status:", id="export-anki-label")
        yield Static("", id="export-anki-status")

        yield Static("", id="export-footer")

    def on_mount(self) -> None:
        self._anki_installed = is_anki_installed()
        self._ankiconnect_ok = is_ankiconnect_running()
        self._refresh_all()

    def _refresh_all(self) -> None:
        n_kept    = len(self._kept)
        n_skipped = len(self._skipped)
        self.query_one("#export-cards-info", Static).update(
            f"  [#22C55E]✓[/]  {n_kept} selected\n"
            f"  [#EF4444]✗[/]  {n_skipped} skipped"
        )

        dest_lines = []
        for i, label in enumerate(self._DESTINATIONS):
            dot = "[bold #38BDF8]◉[/]" if i == self._dest else "○"
            dest_lines.append(f"  {dot}  {label}")
        self.query_one("#export-dest-options", Static).update("\n".join(dest_lines))

        status_lines = []
        if self._anki_installed:
            status_lines.append("  [#22C55E]✓[/]  Anki is running")
        else:
            status_lines.append("  [#EF4444]✗[/]  Anki not detected")
        if self._ankiconnect_ok:
            status_lines.append("  [#22C55E]✓[/]  AnkiConnect detected")
        else:
            status_lines.append("  [#8B949E]–[/]  AnkiConnect not available")
        anki_visible = self._dest == 0
        self.query_one("#export-anki-label", Static).display = anki_visible
        self.query_one("#export-anki-status", Static).display = anki_visible
        if anki_visible:
            self.query_one("#export-anki-status", Static).update("\n".join(status_lines))

        self.query_one("#export-footer", Static).update(
            f" [reverse] Enter [/] {self._footer_label()}"
            "    [reverse] Esc [/] Back"
        )

    def action_move_up(self) -> None:
        self._dest = (self._dest - 1) % len(self._DESTINATIONS)
        self._refresh_all()

    def action_move_down(self) -> None:
        self._dest = (self._dest + 1) % len(self._DESTINATIONS)
        self._refresh_all()

    async def action_export(self) -> None:
        footer = self.query_one("#export-footer", Static)
        footer.update(" [dim]Exporting… please wait[/]")

        course_title = self.app.course.get("title", "")
        dest = self._dest

        def _do_export():
            if dest == 0:
                apkg_path = export_to_apkg(self._kept, course_title=course_title)
                if not is_ankiconnect_running():
                    raise RuntimeError(
                        "AnkiConnect not reachable. Open Anki, enable AnkiConnect, then try again."
                    )
                pushed = push_cards(self._kept, course_title=course_title)
                return {"cards": pushed, "total": len(self._kept),
                        "apkg": str(apkg_path), "dest": "anki"}
            elif dest == 1:
                apkg_path = export_to_apkg(self._kept, course_title=course_title)
                return {"cards": len(self._kept), "total": len(self._kept),
                        "apkg": str(apkg_path), "dest": "apkg"}
            else:
                import csv
                from pathlib import Path as _Path
                out = _Path("data") / f"{course_title} - Liksyon.csv"
                out.parent.mkdir(parents=True, exist_ok=True)
                with open(out, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["Front", "Back", "Tags", "Chapter", "Lecture"])
                    for c in self._kept:
                        w.writerow([c["front"], c["back"],
                                    " ".join(c.get("tags") or []),
                                    c.get("chapter", ""), c.get("source_lecture", "")])
                return {"cards": len(self._kept), "total": len(self._kept),
                        "apkg": str(out), "dest": "csv"}

        try:
            result = await asyncio.to_thread(_do_export)
        except Exception as e:
            self._refresh_all()  # restore footer
            self.notify(str(e), severity="error", timeout=20)
            return

        self.app.result = result
        self.app.push_screen(DoneScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class DoneScreen(Screen):
    TITLE = "Liksyon — Done"

    _OPTIONS = [
        ("open_anki",    "Open Anki"),
        ("new_session",  "Start another session"),
        ("quit",         "Quit"),
    ]

    BINDINGS = [
        Binding("up",    "move_up",   "", show=False, priority=True),
        Binding("down",  "move_down", "", show=False, priority=True),
        Binding("enter", "select",    "Select", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cursor = 0

    def _build_stats(self) -> list[str]:
        result = self.app.result
        n      = result.get("cards", 0)
        total  = result.get("total", n)
        dest   = result.get("dest", "anki")
        path   = result.get("apkg", "")
        dupes  = total - n
        deck   = f"{self.app.course.get('title', '')} - Liksyon"
        lines  = []
        lines.append(f"  [#22C55E]✓[/]  Created deck: {deck}")
        if dest == "anki":
            lines.append(f"  [#22C55E]✓[/]  Added [bold]{n}[/] flashcard(s) to Anki")
            if dupes:
                lines.append(f"  [dim]     {dupes} duplicate(s) skipped[/dim]")
        elif dest == "apkg":
            lines.append(f"  [#22C55E]✓[/]  Saved [bold]{n}[/] flashcard(s) to .apkg")
        else:
            lines.append(f"  [#22C55E]✓[/]  Exported [bold]{n}[/] flashcard(s) to CSV")
        lines.append(f"  [#22C55E]✓[/]  Session saved")
        if path:
            lines.append(f"  [dim]     {path}[/dim]")
        return lines

    def _option_text(self, idx: int) -> str:
        _, label = self._OPTIONS[idx]
        if idx == self._cursor:
            return f"  [bold #38BDF8]›[/]  {label}"
        return f"  ○  {label}"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Start New Session  [bold #38BDF8]›[/]  [bold]Done[/]",
            id="breadcrumb",
        )
        yield Center(
            Vertical(
                Static(
                    "[bold #22C55E]  ╭──────────╮\n"
                    "  │          │\n"
                    "  │    ✓     │\n"
                    "  │          │\n"
                    "  ╰──────────╯[/]",
                    id="done-check",
                ),
                Static("[bold #22C55E]Done![/]", id="done-heading"),
                Static("", id="done-stats"),
                Static("[bold #38BDF8]What's next?[/]", id="done-next-label"),
                ListView(
                    *[ListItem(Static("", id=f"done-opt-{i}")) for i in range(len(self._OPTIONS))],
                    id="done-options",
                ),
                id="done-inner",
            ),
            id="done-outer",
        )
        yield Static(
            " [reverse] ↑↓ [/] Navigate    [reverse] Enter [/] Select",
            id="done-footer",
        )

    def on_mount(self) -> None:
        self.query_one("#done-stats", Static).update("\n".join(self._build_stats()))
        self._refresh_options()
        lv = self.query_one("#done-options", ListView)
        lv.focus()

    def _refresh_options(self) -> None:
        for i in range(len(self._OPTIONS)):
            item = self.query_one(f"#done-opt-{i}", Static)
            item.update(self._option_text(i))

    def action_move_up(self) -> None:
        self._cursor = (self._cursor - 1) % len(self._OPTIONS)
        self._refresh_options()
        lv = self.query_one("#done-options", ListView)
        lv.index = self._cursor

    def action_move_down(self) -> None:
        self._cursor = (self._cursor + 1) % len(self._OPTIONS)
        self._refresh_options()
        lv = self.query_one("#done-options", ListView)
        lv.index = self._cursor

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        idx = event.list_view.index
        if idx is not None:
            self._cursor = idx
            self._refresh_options()

    def action_select(self) -> None:
        key, _ = self._OPTIONS[self._cursor]
        if key == "open_anki":
            from liksyon.export.ankiconnect import launch_anki
            try:
                launch_anki()
            except Exception:
                pass
        elif key == "new_session":
            # pop Done, Export, Review, Process, Configure
            # → lands on LectureScreen (Udemy) or YouTubeScreen (YouTube)
            for _ in range(5):
                self.app.pop_screen()
        elif key == "quit":
            self.app.exit()


class LiksyonApp(App):
    CSS = CSS
    DARK = True
    TITLE = "Liksyon"

    # shared state across screens
    source: str = ""
    browser: str = ""
    courses: list = []
    course: dict = {}
    all_lectures: list = []
    selected_lectures: list = []
    config: dict = {}
    scraper = None
    result: dict = {}

    def on_mount(self) -> None:
        init_db()
        self.register_theme(Theme(
            name="liksyon",
            primary="#38BDF8",
            accent="#38BDF8",
            secondary="#2563EB",
            dark=True,
            background="#060B10",
            surface="#0B1118",
            panel="#0B1118",
            success="#22C55E",
            warning="#F59E0B",
            error="#EF4444",
            variables={
                "block-cursor-background": "#1D4ED8",
                "block-cursor-foreground": "#E5E7EB",
                "block-cursor-blurred-background": "#0B1118",
                "block-cursor-blurred-foreground": "#8B949E",
                "block-cursor-text-style": "bold",
            },
        ))
        self.theme = "liksyon"
        self.push_screen(SplashScreen())


def run() -> None:
    LiksyonApp().run()
