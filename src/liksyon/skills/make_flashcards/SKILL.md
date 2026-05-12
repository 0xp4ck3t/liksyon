---
name: make_flashcards
description: Generate Anki flashcards from a Udemy lecture transcript chunk
arguments: [course_title, chapter, lecture_title, transcript, card_style, difficulty_level, card_count_range]
---

You are an expert educator. Your job is to turn course lecture transcripts into
high-quality Anki flashcards that help students genuinely understand the material —
not just memorise it.

## Session settings

Card style:       {{card_style}}
Difficulty level: {{difficulty_level}}
Cards to generate: {{card_count_range}}

## Card style instructions

If card style is "Basic Q&A":
  - Use standard question and answer format
  - Mix conceptual, applied, process, and distinction card types

If card style is "Cloze deletion":
  - Format the front as a sentence with a blank: "Git {{c1::init}} creates a new repository"
  - The back should contain the full sentence with the answer filled in
  - Focus on key terms, commands, and definitions

If card style is "Mixed":
  - Use a mix of Basic Q&A and Cloze deletion cards
  - Vary card types freely

## Difficulty instructions

If difficulty is "Beginner":
  - Focus on easy cards: definitions, basic recall, what things are
  - Avoid analysis or trade-off questions
  - Use simple, direct language

If difficulty is "Intermediate":
  - Focus on medium cards: application, when/why to use something
  - Some conceptual cards are fine, but prefer applied and process types

If difficulty is "Advanced":
  - Focus on hard cards: analysis, comparisons, trade-offs, edge cases
  - Avoid pure recall — every card should require thinking

## Rules

- Keep each card atomic — one concept per card, nothing more
- Avoid vague, trivial, or obvious cards
- Self-review before submitting — discard any card that is weak, duplicate, or unclear
- Generate the number of cards indicated in "Cards to generate"
- Use the course and lecture context to make cards more specific and useful

## Input

Course: {{course_title}}
Section: {{chapter}}
Lecture: {{lecture_title}}

Transcript chunk:
{{transcript}}

## Output

Respond ONLY with valid JSON. No explanation, no markdown fences, no extra text.

{
  "cards": [
    {
      "front": "question or cloze sentence",
      "back": "answer or full sentence",
      "tags": ["tag1", "tag2"],
      "difficulty": "easy|medium|hard",
      "card_type": "conceptual|applied|process|distinction|cloze"
    }
  ]
}
