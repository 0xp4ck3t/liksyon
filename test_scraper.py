from src.liksyon.agent import run_agent
from src.liksyon.export.ankiconnect import deliver_to_anki
from src.liksyon.export.genanki_export import export_to_apkg
from src.liksyon.scraper import UdemyScraper, pick_browser
from src.liksyon.storage import get_flashcards, init_db, save_transcript


def pick_course(courses: list[dict]) -> dict:
    print("\n=== Your Udemy Courses ===\n")
    for i, c in enumerate(courses, 1):
        print(f"  [{i}] {c['title']}")
    print()
    while True:
        raw = input("Pick a course number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(courses):
            return courses[int(raw) - 1]
        print(f"  Enter a number between 1 and {len(courses)}.")


def pick_lectures(lectures: list[dict]) -> list[dict]:
    # build section index: section_num → list of lecture indices (1-based)
    sections: list[tuple[str, list[int]]] = []
    current_chapter = None
    current_section_indices: list[int] = []

    for i, lec in enumerate(lectures, 1):
        if lec["chapter"] != current_chapter:
            if current_chapter is not None:
                sections.append((current_chapter, current_section_indices))
            current_chapter = lec["chapter"]
            current_section_indices = []
        current_section_indices.append(i)
    if current_chapter is not None:
        sections.append((current_chapter, current_section_indices))

    print("\n=== Lectures ===\n")
    sec_idx = 1
    sec_map: dict[int, list[int]] = {}
    current_chapter = None
    for i, lec in enumerate(lectures, 1):
        if lec["chapter"] != current_chapter:
            current_chapter = lec["chapter"]
            sec_map[sec_idx] = next(idxs for ch, idxs in sections if ch == current_chapter)
            print(f"\n  [s{sec_idx}] {current_chapter}")
            sec_idx += 1
        has_transcript = "✓" if lec["caption_url"] else "✗"
        print(f"    [{i:>3}] {has_transcript} {lec['title']}")

    print("\n  ✓ = has transcript   ✗ = no transcript")
    print("\nPick lectures to scrape:")
    print("  all       — scrape everything")
    print("  s1,s2     — entire sections by number")
    print("  1,2,5     — specific lecture numbers")
    print("  1-10      — a range of lectures")
    print()

    while True:
        raw = input("Your selection: ").strip().lower()
        if raw == "all":
            return lectures

        try:
            indices = set()
            for part in raw.split(","):
                part = part.strip()
                if part.startswith("s"):
                    sn = int(part[1:])
                    if sn in sec_map:
                        indices.update(sec_map[sn])
                elif "-" in part:
                    start, end = part.split("-")
                    indices.update(range(int(start), int(end) + 1))
                else:
                    indices.add(int(part))
            selected = [lectures[i - 1] for i in sorted(indices) if 1 <= i <= len(lectures)]
            if selected:
                return selected
        except (ValueError, IndexError):
            pass
        print("  Invalid selection. Try again.")


def main():
    init_db()
    browser = pick_browser()
    with UdemyScraper(browser=browser) as scraper:
        print("Checking login...")
        if not scraper.is_logged_in():
            print("Not logged in. Please log into Udemy in Firefox and try again.")
            return

        print("Loading your courses...")
        courses = scraper.get_owned_courses()
        if not courses:
            print("No courses found.")
            return

        course = pick_course(courses)
        print(f"\nSelected: {course['title']}")

        print("Fetching course structure...")
        course_id = str(course["id"])
        results = scraper.get_course_structure(course_id)
        lectures = scraper.build_lecture_list(results)

        if not lectures:
            print("No video lectures found.")
            return

        selected = pick_lectures(lectures)
        print(f"\nScraping {len(selected)} lecture(s)...\n")
        transcripts = scraper.scrape_lectures(selected, course_id)

        print(f"\nSaving to database...")
        for t in transcripts:
            save_transcript(t, course_title=course["title"])
        print(f"Saved {len(transcripts)} lectures to data/liksyon.db")

        print("\nGenerating flashcards...\n")
        cards = run_agent(transcripts, course_title=course["title"])
        print(f"\nDone. {len(cards)} flashcard(s) saved to database.")

        print("\nExporting to Anki...")
        all_cards = get_flashcards(course_id)
        apkg_path = export_to_apkg(all_cards, course_title=course["title"])
        deliver_to_anki(all_cards, course_title=course["title"], apkg_path=apkg_path)


if __name__ == "__main__":
    main()
