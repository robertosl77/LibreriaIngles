"""Prompts de generación y evaluación.

La aplicación decide nivel, skills y tipos; la IA solo rellena contenido
dentro de ese marco (documento funcional §2.1) y devuelve JSON validable (§31).
"""

import json
from functools import lru_cache

from app.curriculum.service import get_level

GENERATION_SYSTEM = """You generate English-learning exercises for a structured learning app.
The app owns the curriculum: you MUST stay within the requested CEFR level, skills,
objectives and exercise types. Never add skills that were not requested.

Return ONLY a JSON object with this shape:
{
  "title": "short class title in Spanish",
  "exercises": [
    {
      "skillKey": "<one of the requested skill keys>",
      "type": "fill_blank | multiple_choice | reading_multiple_choice | rewrite | short_writing | conversation",
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
      "expectedConcepts": ["snake_case concept names evaluated by this item"],
      "closing": "only for the final turn of a conversation pair: short partner farewell/closure"
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
- conversation: acceptedAnswers is []; the learner must produce a natural open reply. The "question"
  is the partner's turn when presentation is READ. When presentation is LISTEN, put the partner's
  actual turn in "stimulus" and use a neutral question such as "Reply naturally.".
- Conversation slots may contain conversationGroup/conversationTurn/conversationTotal. Slots with the
  same group form ONE microconversation and must be coherent in order. For A1, make two simple learner
  turns. Turn 2 must continue naturally from a plausible correct reply to turn 1, but must NOT depend
  on one exact wording from the learner. On the last turn, include a short "closing" line from the
  partner so the exchange visibly ends after correction.
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
      * conversation: "stimulus" is exactly the partner's conversational turn; "question" only tells
        the learner to reply naturally and must not reveal the stimulus text.
    For numbers and times list digit and word forms in acceptedAnswers (e.g. "26",
    "twenty-six"; "8:30", "half past eight").
- The slot "response" controls HOW the same exercise is answered:
  - WRITE: normal typed response.
  - SELECT: choose one option.
  - SPEAK: the learner answers aloud. Do not create a new exercise type and do not tell the
    learner to "write" or "type"; use wording such as "Say..." or "Answer aloud...".
    For rewrite, the learner says the complete transformed sentence. For short_writing, the
    learner gives the same 2-3 sentence content orally.
  LISTEN + SPEAK is valid: hear the stimulus, then answer aloud.
- acceptedAnswers must be exhaustive for closed items: list every grammatically correct variant.
- commonErrors: 0-3 realistic learner mistakes, each with feedback in Spanish.
- Use varied, everyday contexts and names; vocabulary appropriate for the level.
- Every closed item must have exactly one defensible answer and test the language, not general
  knowledge or logic. Never use "odd one out" / "word that does not belong" items: state the
  criterion explicitly instead (e.g. "Which one is a drink?").
- Do not repeat the example items literally; create new ones.
"""

EVALUATION_SYSTEM = """You evaluate a student's answer to an English exercise in a structured learning app.
You receive the level, the exercise, the objectives, the reference answers and the student answer.

Return ONLY a JSON object:
{
  "result": "correct | partially_correct | incorrect",
  "conceptResults": [{"concept": "<expected concept>", "status": "correct|partially_correct|incorrect", "score": 0-100}],
  "errors": [{"type": "GRAMMAR_ERROR|VOCABULARY_ERROR|SPELLING_ERROR|WORD_ORDER_ERROR|PRONUNCIATION_ERROR",
              "fragment": "wrong part", "correction": "fix", "explanation": "en español, máximo 15 palabras"}],
  "correctAnswer": "a correct version of the answer, or null for open writing",
  "feedback": "1-2 frases cortas en español, dirigidas al alumno",
  "suggestions": [{"type": "STYLE_SUGGESTION|NATURALNESS_SUGGESTION|SHORTER_ALTERNATIVE|MECHANICS_NOTE", "text": "en español, máximo 15 palabras"}],
  "secondarySkillResults": [
    {"skillKey": "<a key from the skill catalog>", "status": "correct|partially_correct|incorrect",
     "score": 0-100, "reason": "brief evidence in Spanish"}
  ]
}

Rules:
- Be brief: at most 2 suggestions; each explanation, suggestion and reason short; do not repeat in "feedback" what "errors" already says.
- Evaluate the PRIMARY result ONLY on what the objectives and expected concepts target, at the given level.
- The SKILL CATALOG at the end lists the curricular skills of the level. "secondaryAreas" says which
  catalog areas may receive incidental evidence from what the learner actually produced. Return
  secondarySkillResults ONLY for catalog skills of those areas (never the primary "skillKey") that are
  directly evidenced by this answer, at most 3, using the catalog key exactly. If "secondaryAreas" is
  empty, return []. Do not invent evidence. A secondary error must never reduce the primary
  Conversation/task score unless it also makes the conversational objective fail.
- The reference answers are examples, not an exhaustive list: a different answer that is
  grammatically correct and fulfils the task IS correct.
- Never mark an answer incorrect only because a more natural alternative exists:
  put that in "suggestions", not in "errors".
- Report one conceptResult per expected concept, with "score" 0-100 reflecting HOW MUCH of
  that concept the student controls: correct 85-100, partially_correct 35-84, incorrect 0-34.
  One small slip in otherwise good use is partially_correct with a high score (70-84), not incorrect.
- Grade each concept ONLY on mistakes about that concept. A preposition, vocabulary or
  verb-pattern mistake (e.g. "at the morning", "like play") does not lower "present_simple_use"
  if the present simple itself is used correctly.
- Calibrate to the level. At A1-A2 penalize only what a learner of that level is expected to
  control (to be, present simple forms, do/does, basic word order, a/an, plurals, basic
  prepositions, like + -ing/to). Expressions beyond the level (idioms, phrasal verbs, more
  natural wording) are "suggestions", never "errors".
- Capitalization and punctuation in open writing ("i" for "I", missing final period) are NOT
  grammar errors: add at most ONE suggestion of type MECHANICS_NOTE; never list each one.
- Report each mistake pattern ONCE (if "like play", "like drink" and "like read" share the
  same mistake, one error listing the fragments).
- For open writing, evaluate grammar, vocabulary and task completion at the given level.
- For type "conversation", first judge communicative success: did the learner understand the partner's
  turn, answer something relevant, preserve the interaction and remain understandable at the requested
  level? There is usually more than one valid reply. Grammar/vocabulary mistakes may be reported and
  may feed secondarySkillResults while the Conversation objective can still be correct or partial.
  Use conversationContext when supplied to check continuity with earlier turns.
- If "response" is SPEAK, "studentAnswer" is a literal speech-to-text transcript: never penalize
  punctuation or capitalization; evaluate the spoken words, grammar, vocabulary and task completion.
  If it differs from a correct answer only by a word that SOUNDS almost the same (e.g. "sink" for
  "think", "berry" for "very", "ship" for "sheep"), treat it as a pronunciation slip, not a
  grammar/vocabulary error: mark the concepts as correct and add one error of type
  PRONUNCIATION_ERROR with that word.
- Minor spelling (1-2 letters wrong in a recognizable word, e.g. "taxy" for "taxi", "freind"
  for "friend") is NOT a concept error when the intended word is clear and is the right one:
  keep the concept as correct and add one error of type SPELLING_ERROR with the fix. If the
  student wrote a different real word ("on" for "in", "sleep" for "sheep"), that is a real
  error, not spelling. Keep "feedback" consistent with the result: never call an answer
  "almost correct" while marking its concepts incorrect.
"""


EXAM_NOTE = (
    "This is a LEVEL EXAM, not a practice class. Every item must have exactly one defensible "
    "answer, test the language (not general knowledge), be clearly worded for the level, and "
    "all items must be different from each other and from the examples."
)


def compact_json(value) -> str:
    """T-174: el modelo lee igual el JSON sin sangrías; se ahorra ≈35 % de caracteres."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def generation_user_prompt(level: str, slots: list[dict], purpose: str = "class") -> str:
    header = "Generate a class.\n" if purpose != "exam" else f"Generate a level exam.\n{EXAM_NOTE}\n"
    return header + compact_json({"level": level, "slots": slots})


def evaluation_user_prompt(payload: dict) -> str:
    return "Evaluate this answer.\n" + compact_json(payload)


# T-171: varias respuestas de la misma clase en una sola llamada.
BATCH_EVALUATION_NOTE = """
BATCH MODE: "items" contains several answers from the same class. Evaluate EACH item independently,
applying every rule above to that item only (its own type, objectives, references, secondaryAreas and
conversationContext). Return ONLY {"results": [ {"id": <the item id>, ...the evaluation object...} ]}
with exactly one result per item and the same ids.
"""


def evaluation_batch_user_prompt(level: str | None, items: list[dict]) -> str:
    return "Evaluate these answers.\n" + compact_json({"level": level, "items": items})


# ---------------------------------------------------------------- T-170 catálogo compacto por nivel

# Áreas que pueden recibir evidencia secundaria (T-048). Writing solo en respuestas escritas.
SECONDARY_AREAS = ("grammar", "vocabulary", "writing")


def short_skill_key(skill_key: str) -> str:
    """a1.grammar.to_be.negative → grammar.to_be.negative (el nivel ya está en el prompt)."""
    return skill_key.split(".", 1)[1] if "." in skill_key else skill_key


@lru_cache
def skill_catalog(level: str | None) -> str:
    """Una línea por skill: clave corta + tema · nombre. Sin objetivos (≈560 tokens en A1 vs ≈2.270)."""
    curriculum = get_level(level) if level else None
    if curriculum is None:
        return ""
    return "\n".join(
        f"{short_skill_key(s.key)}: {s.topic_name} · {s.name}"
        for s in curriculum.skills
        if s.area_key in SECONDARY_AREAS
    )


@lru_cache
def evaluation_system(level: str | None) -> str:
    """System prompt de corrección del nivel: idéntico en cada llamada (prefijo cacheable)."""
    catalog = skill_catalog(level)
    if not catalog:
        return EVALUATION_SYSTEM
    return f"{EVALUATION_SYSTEM}\nSKILL CATALOG (level {level}; use these keys exactly):\n{catalog}\n"


# ---------------------------------------------------------------- T-173 esquemas de respuesta (Gemini)
# Garantizan la FORMA del JSON (no su contenido: el backend sigue validando todo).

def _s(type_: str, **extra) -> dict:
    return {"type": type_, **extra}


_STR = _s("STRING")
_STR_LIST = _s("ARRAY", items=_STR)
_STATUS = _s("STRING", enum=["correct", "partially_correct", "incorrect"])

EXERCISE_SCHEMA = _s(
    "OBJECT",
    properties={
        "skillKey": _STR,
        "type": _s(
            "STRING",
            enum=["fill_blank", "multiple_choice", "reading_multiple_choice", "rewrite", "short_writing", "conversation"],
        ),
        "instruction": _STR,
        "question": _STR,
        "passage": _s("STRING", nullable=True),
        "stimulus": _s("STRING", nullable=True),
        "options": _s("ARRAY", items=_STR, nullable=True),
        "acceptedAnswers": _STR_LIST,
        "commonErrors": _s(
            "ARRAY",
            items=_s(
                "OBJECT",
                properties={
                    "answer": _STR,
                    "feedback": _STR,
                    "conceptResults": _s(
                        "ARRAY", items=_s("OBJECT", properties={"concept": _STR, "status": _STATUS})
                    ),
                },
                required=["answer", "feedback"],
            ),
        ),
        "expectedConcepts": _STR_LIST,
        "closing": _s("STRING", nullable=True),
    },
    required=["skillKey", "type", "instruction", "question", "acceptedAnswers", "expectedConcepts"],
)

GENERATION_SCHEMA = _s(
    "OBJECT",
    properties={"title": _STR, "exercises": _s("ARRAY", items=EXERCISE_SCHEMA)},
    required=["title", "exercises"],
)

_EVALUATION_PROPERTIES = {
    "result": _STATUS,
    "conceptResults": _s(
        "ARRAY",
        items=_s("OBJECT", properties={"concept": _STR, "status": _STATUS, "score": _s("NUMBER")},
                 required=["concept", "status"]),
    ),
    "errors": _s(
        "ARRAY",
        items=_s(
            "OBJECT",
            properties={
                "type": _s(
                    "STRING",
                    enum=["GRAMMAR_ERROR", "VOCABULARY_ERROR", "SPELLING_ERROR", "WORD_ORDER_ERROR", "PRONUNCIATION_ERROR"],
                ),
                "fragment": _STR,
                "correction": _STR,
                "explanation": _STR,
            },
            required=["type", "explanation"],
        ),
    ),
    "correctAnswer": _s("STRING", nullable=True),
    "feedback": _STR,
    "suggestions": _s(
        "ARRAY",
        items=_s(
            "OBJECT",
            properties={
                "type": _s(
                    "STRING",
                    enum=["STYLE_SUGGESTION", "NATURALNESS_SUGGESTION", "SHORTER_ALTERNATIVE", "MECHANICS_NOTE"],
                ),
                "text": _STR,
            },
            required=["type", "text"],
        ),
    ),
    "secondarySkillResults": _s(
        "ARRAY",
        items=_s(
            "OBJECT",
            properties={"skillKey": _STR, "status": _STATUS, "score": _s("NUMBER"), "reason": _STR},
            required=["skillKey", "status"],
        ),
    ),
}
_EVALUATION_REQUIRED = ["result", "conceptResults", "errors", "feedback"]

EVALUATION_SCHEMA = _s("OBJECT", properties=_EVALUATION_PROPERTIES, required=_EVALUATION_REQUIRED)

EVALUATION_BATCH_SCHEMA = _s(
    "OBJECT",
    properties={
        "results": _s(
            "ARRAY",
            items=_s(
                "OBJECT",
                properties={"id": _s("INTEGER"), **_EVALUATION_PROPERTIES},
                required=["id", *_EVALUATION_REQUIRED],
            ),
        )
    },
    required=["results"],
)
