import asyncio
import io
import sys

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    RichLog,
    SelectionList,
    Static,
)
from textual.widgets.selection_list import Selection

from liksyon.agent import run_agent
from liksyon.export.ankiconnect import deliver_to_anki
from liksyon.export.genanki_export import export_to_apkg
from liksyon.scraper import UdemyScraper, load_browser_cookies
from liksyon.storage import get_flashcards, init_db, save_transcript

BROWSERS = [
    ("firefox",  "Firefox"),
    ("chrome",   "Chrome"),
    ("chromium", "Chromium"),
    ("edge",     "Microsoft Edge"),
    ("brave",    "Brave"),
    ("safari",   "Safari (Mac only)"),
]

CSS = """
Screen {
    background: $surface;
}

.title {
    text-align: center;
    padding: 1 2;
    color: $accent;
    text-style: bold;
}

.subtitle {
    text-align: center;
    color: $text-muted;
    padding: 0 2 1 2;
}

ListView, SelectionList {
    border: solid $primary;
    margin: 1 4;
    height: auto;
    max-height: 24;
}

#lecture-list {
    height: 1fr;
    max-height: 100%;
}

#log {
    border: solid $primary;
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
    border: solid $success;
    margin: 2 4;
    padding: 1 2;
    height: auto;
}

.stat {
    padding: 0 1;
}

.error {
    color: $error;
    text-align: center;
    padding: 1 4;
}

#splash-content {
    align: center middle;
    height: 1fr;
}

#logo {
    text-align: center;
    padding: 1 4;
}

#tagline {
    text-align: center;
    color: $text-muted;
    padding: 0 0 2 0;
}
"""


class SplashScreen(Screen):
    TITLE = "Liksyon"

    BINDINGS = [Binding("enter", "start", "Start")]

    LOGO = """\
[bold #00d7ff]██╗     ██╗██╗  ██╗███████╗██╗   ██╗ ██████╗ ███╗   ██╗[/]
[bold #00d7ff]██║     ██║██║ ██╔╝██╔════╝╚██╗ ██╔╝██╔═══██╗████╗  ██║[/]
[bold #00afff]██║     ██║█████╔╝ ███████╗ ╚████╔╝ ██║   ██║██╔██╗ ██║[/]
[bold #00afff]██║     ██║██╔═██╗ ╚════██║  ╚██╔╝  ██║   ██║██║╚██╗██║[/]
[bold #0087ff]███████╗██║██║  ██╗███████║   ██║   ╚██████╔╝██║ ╚████║[/]
[bold #0087ff]╚══════╝╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═══╝[/]"""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Center(
            Vertical(
                Static(self.LOGO, id="logo"),
                Static(
                    "[dim]AI-powered flashcards from your Udemy courses[/dim]",
                    id="tagline",
                ),
                Center(Button("Get Started →", variant="primary", id="start")),
                id="splash-content",
            )
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.action_start()

    def action_start(self) -> None:
        self.app.push_screen(BrowserScreen())


class BrowserScreen(Screen):
    TITLE = "Liksyon — Pick Browser"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Which browser are you logged into Udemy with?", classes="title")
        yield ListView(
            *[ListItem(Label(label), id=f"b-{key}") for key, label in BROWSERS],
        )
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        browser_id = event.item.id.replace("b-", "")
        self.app.browser = browser_id
        self.app.push_screen(CourseScreen())


class CourseScreen(Screen):
    TITLE = "Liksyon — Select Course"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Your Udemy Courses", classes="title")
        yield LoadingIndicator(id="loader")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._load(), exclusive=True)

    async def _load(self) -> None:
        try:
            courses = await asyncio.to_thread(self._fetch)
            self.app.courses = courses
            await self.query_one("#loader").remove()
            items = [ListItem(Label(c["title"]), id=f"c-{i}") for i, c in enumerate(courses)]
            await self.mount(ListView(*items))
        except Exception as e:
            await self.query_one("#loader").remove()
            await self.mount(Label(f"Error: {e}", classes="error"))

    def _fetch(self) -> list[dict]:
        scraper = UdemyScraper(browser=self.app.browser)
        cookies = load_browser_cookies(self.app.browser)
        scraper.session.cookies.update(cookies)
        self.app.scraper = scraper
        if not scraper.is_logged_in():
            raise RuntimeError(
                "Not logged in. Please log into Udemy in your browser first."
            )
        return scraper.get_owned_courses()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.replace("c-", ""))
        self.app.course = self.app.courses[idx]
        self.app.push_screen(LectureScreen())


class LectureScreen(Screen):
    TITLE = "Liksyon — Select Lectures"

    BINDINGS = [
        Binding("a", "select_all", "All"),
        Binding("n", "select_none", "None"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(self.app.course.get("title", ""), classes="title")
        yield Label(
            "Space = toggle  ·  a = select all  ·  n = deselect all",
            classes="subtitle",
        )
        yield LoadingIndicator(id="loader")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._load(), exclusive=True)

    async def _load(self) -> None:
        try:
            lectures = await asyncio.to_thread(self._fetch)
            self.app.all_lectures = lectures
            await self.query_one("#loader").remove()
            await self._mount_list(lectures)
        except Exception as e:
            await self.query_one("#loader").remove()
            await self.mount(Label(f"Error: {e}", classes="error"))

    def _fetch(self) -> list[dict]:
        scraper = self.app.scraper
        course_id = str(self.app.course["id"])
        results = scraper.get_course_structure(course_id)
        return scraper.build_lecture_list(results)

    async def _mount_list(self, lectures: list[dict]) -> None:
        selections = []
        current_chapter = None
        sec_num = 0

        for i, lec in enumerate(lectures):
            if lec["chapter"] != current_chapter:
                current_chapter = lec["chapter"]
                sec_num += 1
                selections.append(
                    Selection(
                        f"── [s{sec_num}] {current_chapter} ──",
                        value=f"__sec_{sec_num}",
                        disabled=True,
                    )
                )
            icon = "✓" if lec["caption_url"] else "✗"
            selections.append(Selection(f"  {icon}  {lec['title']}", value=i))

        await self.mount(SelectionList(*selections, id="lecture-list"))
        await self.mount(
            Horizontal(
                Button("Confirm", variant="primary", id="confirm"),
                classes="button-row",
            )
        )

    def action_select_all(self) -> None:
        try:
            self.query_one(SelectionList).select_all()
        except Exception:
            pass

    def action_select_none(self) -> None:
        try:
            self.query_one(SelectionList).deselect_all()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "confirm":
            return
        sel = self.query_one(SelectionList)
        chosen = [v for v in sel.selected if isinstance(v, int)]
        if not chosen:
            self.notify("Select at least one lecture.", severity="warning")
            return
        self.app.selected_lectures = [self.app.all_lectures[i] for i in sorted(chosen)]
        self.app.push_screen(ProcessScreen())


class ProcessScreen(Screen):
    TITLE = "Liksyon — Processing"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Generating flashcards...", classes="title")
        yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._run(), exclusive=True)

    async def _run(self) -> None:
        log = self.query_one(RichLog)

        def emit(msg: str) -> None:
            self.app.call_from_thread(log.write, msg)

        try:
            result = await asyncio.to_thread(self._pipeline, emit)
            self.app.result = result
            await self.app.push_screen(DoneScreen())
        except Exception as e:
            log.write(f"[red]Fatal error: {e}[/red]")

    def _pipeline(self, emit) -> dict:
        class _Capture(io.TextIOBase):
            def write(self_, text):
                if text.strip():
                    emit(text.rstrip())
                return len(text)

            def flush(self_):
                pass

        old_stdout = sys.stdout
        sys.stdout = _Capture()
        try:
            scraper  = self.app.scraper
            course   = self.app.course
            lectures = self.app.selected_lectures
            course_id = str(course["id"])

            emit(f"[bold]Scraping {len(lectures)} lecture(s)...[/bold]")
            transcripts = scraper.scrape_lectures(lectures, course_id)

            emit("\n[bold]Saving transcripts...[/bold]")
            for t in transcripts:
                save_transcript(t, course_title=course["title"])

            emit("\n[bold]Generating flashcards with Claude...[/bold]")
            cards = run_agent(transcripts, course_title=course["title"])

            emit(f"\n[green]Done — {len(cards)} card(s) generated.[/green]")

            emit("\n[bold]Exporting to Anki...[/bold]")
            all_cards = get_flashcards(course_id)
            apkg_path = export_to_apkg(all_cards, course_title=course["title"])
            deliver_to_anki(
                all_cards,
                course_title=course["title"],
                apkg_path=apkg_path,
                interactive=False,
            )

            return {"cards": len(cards), "apkg": str(apkg_path)}
        finally:
            sys.stdout = old_stdout
            try:
                scraper.session.close()
            except Exception:
                pass


class DoneScreen(Screen):
    TITLE = "Liksyon — Done"

    BINDINGS = [Binding("q", "app.exit", "Quit")]

    def compose(self) -> ComposeResult:
        result = self.app.result
        n = result.get("cards", 0)
        apkg = result.get("apkg", "")

        yield Header()
        yield Label("All done!", classes="title")
        yield Container(
            Label(f"[green]✓[/green]  {n} flashcard(s) generated", classes="stat"),
            Label(f"[green]✓[/green]  Cards pushed to Anki", classes="stat"),
            Label(f"[dim]Backup → {apkg}[/dim]", classes="stat"),
            classes="done-box",
        )
        yield Horizontal(
            Button("Run Again", variant="primary", id="again"),
            Button("Quit", id="quit"),
            classes="button-row",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.exit()
        elif event.button.id == "again":
            # pop back to BrowserScreen: Done → Process → Lecture → Course
            for _ in range(4):
                self.app.pop_screen()


class LiksyonApp(App):
    CSS = CSS
    TITLE = "Liksyon"

    # shared state across screens
    browser: str = ""
    courses: list = []
    course: dict = {}
    all_lectures: list = []
    selected_lectures: list = []
    scraper = None
    result: dict = {}

    def on_mount(self) -> None:
        init_db()
        self.push_screen(SplashScreen())


def run() -> None:
    LiksyonApp().run()
