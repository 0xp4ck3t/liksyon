from src.liksyon.scraper import UdemyScraper
from src.liksyon.storage import init_db, save_transcript


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
    print("\n=== Lectures ===\n")
    current_chapter = None
    for i, lec in enumerate(lectures, 1):
        if lec["chapter"] != current_chapter:
            current_chapter = lec["chapter"]
            print(f"\n  {current_chapter}")
        has_transcript = "✓" if lec["caption_url"] else "✗"
        print(f"    [{i:>3}] {has_transcript} {lec['title']}")

    print("\n  ✓ = has transcript   ✗ = no transcript")
    print("\nPick lectures to scrape:")
    print("  all       — scrape everything")
    print("  1,2,5     — specific numbers")
    print("  1-10      — a range")
    print()

    while True:
        raw = input("Your selection: ").strip().lower()
        if raw == "all":
            return lectures
        try:
            indices = set()
            for part in raw.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-")
                    indices.update(range(int(start), int(end) + 1))
                else:
                    indices.add(int(part))
            selected = [lectures[i - 1] for i in sorted(indices) if 1 <= i <= len(lectures)]
            if selected:
                return selected
        except (ValueError, IndexError):
            pass
        print(f"  Invalid selection. Try again.")


def main():
    init_db()
    with UdemyScraper() as scraper:
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

        print(f"\n=== Preview (first 3) ===")
        for t in transcripts[:3]:
            print(f"\n--- {t['chapter']} > {t['title']} ---")
            print(t["transcript"][:300] if t["transcript"] else "(no transcript)")


if __name__ == "__main__":
    main()
