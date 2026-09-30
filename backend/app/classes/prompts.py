"""Prompts de generación y evaluación.

La aplicación decide nivel, skills y tipos; la IA solo rellena contenido
dentro de ese marco (documento funcional §2.1) y devuelve JSON validable (§31).
"""

import json

GENERATION_SYSTEM = """You generate English-learning exercises for a structured learning app.
The app owns the curriculum: you MUST stay within the requested CEFR level, skills,
objectives and exercise types. Never add skills that were not requested.

Return ONLY a JSON object with this shape:
{
  "title": "short class title in Spanish",
  "exercises": [
    {
      "skillKey": "<one of the requested skill keys>",
      "type": "fill_blank | multiple_choice | reading_multiple_choice | rewrite | short_writing",
      "instruction": "short instruction in simple English",
      "question": "the item shown to the student",
      "passage": "only for reading_multiple_choice: 40-80 word text",
      "stimulus": "only when the slot presentation is LISTEN: the text the student will HEAR",
      "options": ["only for multiple_choice and reading_multiple_choice: 3 or 4 options"],
      "acceptedAnswers": ["EVERY correct answer variant"],
      "commonErrors": [
        {"answer": "typical wrong answer",
         "feedback": "explicación breve en español",
         "conceptResults": [{"concept": "<expected concept>", "status": "correct|incorrect"}]}
      ],
      "expectedConcepts": ["snake_case concept names evaluated by this item"]
    }
  ]
}

Rules:
- Produce exactly one exercise per requested slot, in the same order, using that slot's skillKey
  and one of its allowed types.
- fill_blank: the question contains "___" exactly once; acceptedAnswers are ONLY the words that
  fill the blank. If the verb is given, put it in brackets after the blank: "___ (watch)".
- multiple_choice / reading_multiple_choice: acceptedAnswers contains exactly one option, copied verbatim.
- rewrite: acceptedAnswers are full sentences; include contracted and full forms
  (e.g. "doesn't" and "does not").
- short_writing: acceptedAnswers is []; the question is an open prompt for 2-3 sentences.
- Each slot has a "presentation" and a "response". The exercise TYPE rules above never change;
  only how the student receives it changes:
  - READ: normal written exercise (no "stimulus").
  - LISTEN: the student HEARS "stimulus" (read aloud by a text-to-speech voice) and does NOT
    see it written. "stimulus" is 1-4 short sentences at the level, natural spoken English, no
    speaker labels or stage directions. The exercise must require listening:
      * fill_blank: "stimulus" is the full sentence; "question" is the same sentence with the
        key word replaced by "___" (the answer is the word heard);
      * multiple_choice / reading_multiple_choice: "question" asks about what was heard; the
        options must not copy the stimulus sentence;
      * rewrite: the instruction says what to do with the sentence heard (e.g. "Write the
        sentence you hear in the negative form"); never write the stimulus in the question;
      * short_writing: "stimulus" is a spoken question or situation; the student answers in writing.
    For numbers and times list digit and word forms in acceptedAnswers (e.g. "26",
    "twenty-six"; "8:30", "half past eight").
- acceptedAnswers must be exhaustive for closed items: list every grammatically correct variant.
- commonErrors: 0-3 realistic learner mistakes, each with feedback in Spanish.
- Use varied, everyday contexts and names; vocabulary appropriate for the level.
- Do not repeat the example items literally; create new ones.
"""

EVALUATION_SYSTEM = """You evaluate a student's answer to an English exercise in a structured learning app.
You receive the level, the exercise, the objectives, the reference answers and the student answer.

Return ONLY a JSON object:
{
  "result": "correct | partially_correct | incorrect",
  "scoreSuggested": 0-100,
  "conceptResults": [{"concept": "<expected concept>", "status": "correct|partially_correct|incorrect", "score": 0-100}],
  "errors": [{"type": "GRAMMAR_ERROR|VOCABULARY_ERROR|SPELLING_ERROR|WORD_ORDER_ERROR",
              "fragment": "wrong part", "correction": "fix", "explanation": "en español"}],
  "correctAnswer": "a correct version of the answer, or null for open writing",
  "feedback": "1-2 frases en español, dirigidas al alumno",
  "suggestions": [{"type": "STYLE_SUGGESTION|NATURALNESS_SUGGESTION|SHORTER_ALTERNATIVE", "text": "en español"}]
}

Rules:
- Evaluate ONLY what the objectives and expected concepts target, at the given level.
- The reference answers are examples, not an exhaustive list: a different answer that is
  grammatically correct and fulfils the task IS correct.
- Never mark an answer incorrect only because a more natural alternative exists:
  put that in "suggestions", not in "errors".
- Report one conceptResult per expected concept.
- For open writing, evaluate grammar, vocabulary and task completion at the given level.
"""


EXAM_NOTE = (
    "This is a LEVEL EXAM, not a practice class. Every item must have exactly one defensible "
    "answer, test the language (not general knowledge), be clearly worded for the level, and "
    "all items must be different from each other and from the examples."
)


def generation_user_prompt(level: str, slots: list[dict], purpose: str = "class") -> str:
    header = "Generate a class.\n" if purpose != "exam" else f"Generate a level exam.\n{EXAM_NOTE}\n"
    return header + json.dumps({"level": level, "slots": slots}, ensure_ascii=False, indent=2)


def evaluation_user_prompt(payload: dict) -> str:
    return "Evaluate this answer.\n" + json.dumps(payload, ensure_ascii=False, indent=2)
