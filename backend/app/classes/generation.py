"""Generación de clases.

1. El motor elige skills (prioriza débiles y no practicadas).
2. Se persiste la solicitud (GENERATING) ANTES de llamar a la IA.
3. La IA rellena el contenido; el backend valida y guarda en formato propio.
"""

import random

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import utcnow
from app.ai.service import (
    AIResult,
    NoAIAvailable,
    connection_snapshot,
    has_audio_connection,
    run_json_task,
)
from app.ai.usage import AIUsageContext
from app.core.config import settings
from app.classes.normalize import BLANK, normalize_answer, normalize_blank
from app.classes.types import (
    CASE_SENSITIVE_TYPES,
    CHOICE_TYPES,
    PAIRS_MAX,
    PAIRS_MIN,
    FIELDS_MAX,
    FIELDS_MIN,
    GAPS_MAX,
    GAPS_MIN,
    READ_ONLY_TYPES,
    SPEAK_ONLY_TYPES,
    STIMULUS_MAY_REPEAT,
    WORD_ORDER_MAX,
    WORD_ORDER_MIN,
    fixed_presentation,
    same_words,
    sentence_words,
    shuffled,
    type_weight,
    word_tiles,
)
from app.classes.prompts import GENERATION_SCHEMA, GENERATION_SYSTEM, generation_user_prompt
from app.core.deps import StudyContext
from app.curriculum.service import Skill, get_level
from app.learning.models import (
    ClassSession,
    ClassSessionStatus,
    EvaluationMode,
    Exercise,
    PresentationMode,
    ResponseMode,
    SessionKind,
    default_response_mode,
)
from app.progress.service import ability_progress, progress_by_skill

EXERCISES_PER_CLASS = 6

EVALUATION_MODE_BY_TYPE = {
    "multiple_choice": EvaluationMode.DETERMINISTIC,
    "reading_multiple_choice": EvaluationMode.DETERMINISTIC,
    "fill_blank": EvaluationMode.HYBRID,
    "rewrite": EvaluationMode.HYBRID,
    "short_writing": EvaluationMode.AI,
    "conversation": EvaluationMode.AI,
    # T-183: los tipos nuevos se corrigen por regla; error_correction como rewrite.
    "dictation": EvaluationMode.DETERMINISTIC,
    "word_order": EvaluationMode.DETERMINISTIC,
    "dialogue_choice": EvaluationMode.DETERMINISTIC,
    "read_aloud": EvaluationMode.DETERMINISTIC,
    "minimal_pairs": EvaluationMode.DETERMINISTIC,
    "match_pairs": EvaluationMode.DETERMINISTIC,
    "listen_form": EvaluationMode.DETERMINISTIC,
    "gap_text": EvaluationMode.DETERMINISTIC,
    "error_correction": EvaluationMode.HYBRID,
    "word_stress": EvaluationMode.DETERMINISTIC,
}

# Velocidad sugerida de la voz por nivel (1.0 = normal del navegador).
AUDIO_RATE_BY_LEVEL = {"A1": 0.85, "A2": 0.9, "B1": 0.95}
STIMULUS_MAX = 600
# Porción de ejercicios que se presentan escuchando (si la skill lo admite).
LISTEN_SHARE = 0.3
# Respuestas habladas: solo sobre tipos que normalmente se escriben.
SPEAK_SHARE = 0.3
# Tipos que se pueden responder hablando. T-207: fill_blank (completar UNA palabra) queda afuera:
# transcribir + corregir + pronunciación por una sola palabra no vale el gasto; va por texto.
SPEAK_TYPES = {"rewrite", "short_writing", "conversation"}
# Tipos de producción propia (escritos): se usan para mantener escrita la Writing reforzada.
PRODUCTIVE_TYPES = SPEAK_TYPES | {"fill_blank"}


class GenerationFailed(Exception):
    pass


# Consumo: los intentos de una clase/examen que no llegó a generarse quedan sin referencia a una clase.
NOT_GENERATED = {"CLASS": "CLASS_NOT_GENERATED", "EXAM": "EXAM_NOT_GENERATED"}


def discard_failed_session(db: Session, session: ClassSession, message: str) -> None:
    """Si la IA no pudo generar la clase/examen, no queda nada guardado a la vista del alumno.

    El registro solo existía para referenciar los intentos de IA; esos intentos siguen en Consumo
    (gastaron IA) pero sin número de clase. Lanza GenerationFailed con el motivo.
    """
    from app.ai.models import AIUsageEvent

    db.flush()  # los intentos recién registrados todavía pueden no estar en la base (autoflush=False)
    kind = session.kind.value
    label = "Examen · no generado" if session.kind == SessionKind.EXAM else "Clase · no generada"
    events = db.scalars(
        select(AIUsageEvent).where(AIUsageEvent.subject_type == kind, AIUsageEvent.subject_id == session.id)
    ).all()
    for event in events:
        event.subject_type = NOT_GENERATED.get(kind, kind)
        event.subject_id = None
        event.subject_label = label
        event.subject_route = None
    db.delete(session)
    db.commit()
    raise GenerationFailed(message)


# ---------------------------------------------------------------- balanceo por habilidad (T-034)

# Una habilidad se refuerza si va mal o si viene necesitando ayuda (lección, escuchar
# varias veces, practicar mucho): pedir ayuda es señal de debilidad aunque acierte.
WEAK_SCORE = 70
WEAK_MIN_EVIDENCE = 2
WEAK_ASSISTED_RECENT = 2
FOCUS_MAX = 2  # no más de 2 habilidades reforzadas por clase: el resto sigue variado
FOCUS_SKILL_BOOST = 2.0
ABILITY_AREA = {
    "GRAMMAR": "grammar",
    "VOCABULARY": "vocabulary",
    "LISTENING": "listening",
    "READING": "reading",
    "WRITING": "writing",
}
SPEECH_ABILITIES = {"SPEAKING", "PRONUNCIATION"}


def weak_abilities(abilities: list[dict], *, allow_speaking: bool = False) -> list[dict]:
    """Habilidades a reforzar en la próxima clase (la más necesitada primero), con el motivo."""
    found = []
    for ab in abilities:
        if ab.get("score") is None:
            continue
        if ab["key"] in SPEECH_ABILITIES and not allow_speaking:
            continue  # sin IA con audio no hay ejercicios hablados para reforzar
        low = ab["status"] == "NEEDS_REVIEW" or (
            ab["score"] < WEAK_SCORE and ab["evidenceCount"] >= WEAK_MIN_EVIDENCE
        )
        helped = (ab.get("assistedRecent") or 0) >= WEAK_ASSISTED_RECENT
        if not (low or helped):
            continue
        reasons = []
        if low:
            reasons.append(f"vas {ab['score']:g}%")
        if helped:
            reasons.append(f"necesitaste ayuda en {ab['assistedRecent']} de los últimos ejercicios")
        need = (100 - ab["score"]) / 100 + 0.25 * (ab.get("assistedRecent") or 0)
        found.append(
            {"key": ab["key"], "kind": "ability", "name": ab["name"], "reason": " y ".join(reasons), "_need": need}
        )
    found.sort(key=lambda f: f["_need"], reverse=True)
    return [{k: v for k, v in f.items() if k != "_need"} for f in found[:FOCUS_MAX]]


WEAK_TOPICS_MAX = 2


def weak_topics_in(slots: list[dict], progress) -> list[dict]:
    """Temas flojos que entraron en la clase (para "Esta clase refuerza…")."""
    found = []
    for key in dict.fromkeys(slot["skillKey"] for slot in slots):
        row = progress.get(key)
        if row is None or not row.attempt_count:
            continue
        reasons = []
        if row.status == "NEEDS_REVIEW" or row.score < WEAK_SCORE:
            reasons.append(f"vas {row.score:g}%")
        if row.assisted_recent:
            reasons.append("usaste la lección hace poco")
        if reasons:
            slot = next(s for s in slots if s["skillKey"] == key)
            found.append({
                "key": key,
                "kind": "topic",
                "name": f'{slot["topic"]} · {slot["skill"]}',
                "reason": " y ".join(reasons),
                "_score": row.score,
            })
    found.sort(key=lambda f: f["_score"])
    return [{k: v for k, v in f.items() if k != "_score"} for f in found[:WEAK_TOPICS_MAX]]


def _force_area(chosen: list[Skill], skills: list[Skill], area: str, keep: set[str], progress, rng) -> None:
    """Si ninguna skill elegida es del área, reemplaza una del área más repetida (que no se refuerce)."""
    if any(s.area_key == area for s in chosen):
        return
    candidates = [s for s in skills if s.area_key == area]
    if not candidates:
        return
    counts: dict[str, int] = {}
    for s in chosen:
        counts[s.area_key] = counts.get(s.area_key, 0) + 1
    replaceable = [i for i, s in enumerate(chosen) if s.area_key not in keep]
    if not replaceable:
        return
    index = max(replaceable, key=lambda i: counts[chosen[i].area_key])
    chosen[index] = rng.choices(candidates, weights=[_weight(c, progress) for c in candidates])[0]


# ---------------------------------------------------------------- selección


def _weight(skill: Skill, progress) -> float:
    row = progress.get(skill.key)
    if row is None or row.attempt_count == 0:
        return 3.0
    if row.status == "MASTERED":
        return 0.4
    # Skills que el alumno viene resolviendo con lección/pista: reforzar (T-020).
    assisted_boost = min(1.5, 0.5 * (row.assisted_recent or 0))
    if row.status == "NEEDS_REVIEW":
        return 3.5 + assisted_boost
    return 0.5 + (100 - row.score) / 100 * 2.5 + assisted_boost


def select_slots(
    skills: list[Skill],
    progress: dict,
    count: int = EXERCISES_PER_CLASS,
    rng=None,
    *,
    allow_speaking: bool = False,
    focus: list[dict] | None = None,
) -> list[dict]:
    rng = rng or random.Random()
    focus_keys = {f["key"] for f in focus or []}
    focus_areas = {ABILITY_AREA[k] for k in focus_keys if k in ABILITY_AREA}

    def weight(skill: Skill) -> float:
        boost = FOCUS_SKILL_BOOST if skill.area_key in focus_areas else 1.0
        return _weight(skill, progress) * boost

    pool = list(skills)
    chosen: list[Skill] = []
    while pool and len(chosen) < count:
        weights = [weight(s) for s in pool]
        pick = rng.choices(pool, weights=weights, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    # Si la currícula tiene menos skills que ejercicios, se repiten las más débiles.
    while len(chosen) < count and skills:
        chosen.append(rng.choices(skills, weights=[weight(s) for s in skills])[0])

    # Balance mínimo: no todo gramática si existen otras áreas.
    areas = {s.area_key for s in skills}
    if len(areas) > 1 and all(s.area_key == "grammar" for s in chosen):
        others = [s for s in skills if s.area_key != "grammar"]
        chosen[-1] = rng.choices(others, weights=[weight(s) for s in others])[0]

    # Cada habilidad a reforzar tiene al menos un ejercicio de su área (Writing = escribir oraciones).
    for area in sorted(focus_areas):
        _force_area(chosen, skills, area, focus_areas, progress, rng)

    # Conversation funciona mejor como microintercambio: si entró una sola skill de conversación,
    # se reserva un segundo slot con otra skill conversacional para formar dos turnos.
    conversation_indexes = [i for i, s in enumerate(chosen) if s.area_key == "conversation"]
    if len(conversation_indexes) % 2 == 1 and len(chosen) >= 2:
        used = {s.key for s in chosen}
        candidates = [s for s in skills if s.area_key == "conversation" and s.key not in used]
        replaceable = [
            i for i, s in enumerate(chosen)
            if s.area_key != "conversation" and s.area_key not in focus_areas
        ]
        if candidates and replaceable:
            chosen[replaceable[-1]] = rng.choices(
                candidates, weights=[weight(s) for s in candidates], k=1
            )[0]

    # Orden pedagógico: gramática y vocabulario primero; conversación y escritura hacia el final.
    area_order = {
        "grammar": 0,
        "vocabulary": 1,
        "listening": 2,
        "reading": 3,
        "conversation": 4,
        "writing": 5,
    }
    chosen.sort(key=lambda s: area_order.get(s.area_key, 9))

    # Si se refuerza Writing, la escritura no se pasa a hablada (lo hablado no es Writing).
    keep_written = {s.key for s in chosen if "WRITING" in focus_keys and s.area_key == "writing"}
    slots = [
        slot_for(
            skill,
            rng,
            allow_speaking=allow_speaking and skill.key not in keep_written,
            types=PRODUCTIVE_TYPES if skill.key in keep_written else None,
        )
        for skill in chosen
    ]
    _resolve_lone_conversation(slots, chosen, rng)
    ensure_listening(slots, skills, 2 if "LISTENING" in focus_keys else 1, rng)
    if allow_speaking:
        speak_min = 2 if focus_keys & SPEECH_ABILITIES else 1
        # T-207: sin fill_blank hablado, a veces no queda ningún tipo hablable: se cambia el tipo de
        # alguna skill que admita uno (reescritura, escritura corta, lectura en voz alta).
        _make_speakable(slots, chosen, speak_min, rng, exclude=keep_written)
        _add_speakable_skill(slots, chosen, skills, speak_min, rng, exclude=keep_written, focus=focus or [])
        ensure_speaking(slots, speak_min, rng, exclude=keep_written)
    pair_conversation_slots(slots)
    return slots


def _resolve_lone_conversation(slots: list[dict], chosen: list[Skill], rng) -> None:
    """T-183: si una skill de conversación salió con otro tipo (dialogue_choice, read_aloud), puede
    quedar un turno de conversación abierta sin pareja. Ese turno pasa a dialogue_choice."""
    lone = [i for i, s in enumerate(slots) if s.get("allowedTypes") == ["conversation"]]
    if len(lone) % 2 == 0:
        return
    # 1) Completar el par: otra skill de conversación que salió con otro tipo pasa a conversación.
    for i, skill in enumerate(chosen):
        if i not in lone and skill.area_key == "conversation" and "conversation" in skill.exercise_types:
            slots[i] = slot_for(skill, rng, types={"conversation"})
            return
    # 2) Sin pareja posible: el turno suelto pasa a "elegir la respuesta".
    index = lone[-1]
    skill = chosen[index]
    if "dialogue_choice" in skill.exercise_types:
        slots[index] = slot_for(skill, rng, types={"dialogue_choice"})


def pair_conversation_slots(slots: list[dict]) -> None:
    """Agrupa los slots Conversation de a dos y sincroniza modalidad para mostrarlos como chat."""
    conversation = [
        slot for slot in slots
        if slot.get("skillKey", "").split(".")[1:2] == ["conversation"]
        and slot.get("allowedTypes") == ["conversation"]
    ]
    for pair_index in range(0, len(conversation) - 1, 2):
        pair = conversation[pair_index:pair_index + 2]
        group = f"conversation-{pair_index // 2 + 1}"
        presentation = "LISTEN" if any(s.get("presentation") == "LISTEN" for s in pair) else "READ"
        response = "SPEAK" if any(s.get("response") == "SPEAK" for s in pair) else "WRITE"
        for turn, slot in enumerate(pair, start=1):
            slot["conversationGroup"] = group
            slot["conversationTurn"] = turn
            slot["conversationTotal"] = 2
            slot["presentation"] = presentation
            slot["response"] = response


def _make_speakable(
    slots: list[dict], chosen: list[Skill], minimum: int, rng, *, exclude: set[str]
) -> None:
    """Para reforzar Speaking/Pronunciation: si faltan ejercicios que se puedan hablar,
    cambia el tipo de alguno cuya skill admita un tipo hablable (ej.: elección → completar)."""
    speakable = sum(
        1 for s in slots if s["response"] == "SPEAK" or s["allowedTypes"][0] in SPEAK_TYPES
    )
    # La conversación no se crea acá (dejaría un turno sin pareja); read_aloud ya es hablado.
    targets = (SPEAK_TYPES - {"conversation"}) | SPEAK_ONLY_TYPES
    for i in rng.sample(range(len(slots)), len(slots)):
        if speakable >= minimum:
            return
        skill, slot = chosen[i], slots[i]
        if slot["allowedTypes"][0] in SPEAK_TYPES or slot["response"] == "SPEAK" or skill.key in exclude:
            continue
        if slot.get("allowedTypes") == ["conversation"] or not set(skill.exercise_types) & targets:
            continue
        presentation = slot["presentation"]
        slots[i] = slot_for(skill, rng, allow_speaking=True, types=targets)
        if slots[i]["allowedTypes"][0] in SPEAK_ONLY_TYPES or "READ" in skill.presentations:
            slots[i]["presentation"] = presentation if presentation in skill.presentations else slots[i]["presentation"]
        speakable += 1


def _add_speakable_skill(
    slots: list[dict], chosen: list[Skill], skills: list[Skill], minimum: int, rng, *, exclude: set[str],
    focus: list[dict],
) -> None:
    """T-207: si no alcanzan los ejercicios hablables, se reemplazan ejercicios del área más repetida
    (nunca foco, conversación ni escucha) por skills que admitan un tipo hablable."""
    def speakable() -> int:
        return sum(1 for s in slots if s["response"] == "SPEAK" or s["allowedTypes"][0] in SPEAK_TYPES | SPEAK_ONLY_TYPES)

    targets = (SPEAK_TYPES - {"conversation"}) | SPEAK_ONLY_TYPES
    while speakable() < minimum:
        taken = {s.key for s in chosen}
        candidates = [s for s in skills if s.key not in taken and set(s.exercise_types) & targets]
        counts: dict[str, int] = {}
        for skill in chosen:
            counts[skill.area_key] = counts.get(skill.area_key, 0) + 1
        replaceable = [
            i for i, (skill, slot) in enumerate(zip(chosen, slots))
            if skill.key not in exclude and slot.get("allowedTypes") != ["conversation"]
            and not _is_focus(slot, focus)
            and slot["allowedTypes"][0] not in SPEAK_TYPES | SPEAK_ONLY_TYPES
        ]
        if not candidates or not replaceable:
            return
        # Primero los que no son escucha (la escucha mínima ya se garantizó antes).
        index = max(replaceable, key=lambda i: (slots[i].get("presentation") != "LISTEN", counts[chosen[i].area_key], i))
        presentation = slots[index].get("presentation")
        skill = rng.choice(candidates)
        chosen[index] = skill
        slots[index] = slot_for(skill, rng, allow_speaking=True, types=targets)
        if presentation in skill.presentations and slots[index]["allowedTypes"][0] not in READ_ONLY_TYPES:
            slots[index]["presentation"] = presentation


def _presentation_for(skill: Skill, rng) -> str:
    if "READ" not in skill.presentations:
        return "LISTEN"
    if "LISTEN" in skill.presentations and rng.random() < LISTEN_SHARE:
        return "LISTEN"
    return "READ"


def ensure_listening(slots: list[dict], skills: list[Skill], minimum: int, rng) -> None:
    """Garantiza al menos `minimum` ejercicios escuchados, pasando a LISTEN slots que lo admitan."""
    by_key = {s.key: s for s in skills}
    missing = minimum - sum(1 for s in slots if s["presentation"] == "LISTEN")
    candidates = [
        s for s in slots
        if s["presentation"] == "READ"
        and "LISTEN" in by_key[s["skillKey"]].presentations
        and s["allowedTypes"][0] not in READ_ONLY_TYPES
    ]
    rng.shuffle(candidates)
    for slot in candidates[: max(0, missing)]:
        slot["presentation"] = "LISTEN"


def ensure_speaking(slots: list[dict], minimum: int, rng, exclude: set[str] | None = None) -> None:
    """Garantiza habla si entre los slots elegidos hay un tipo compatible."""
    missing = minimum - sum(1 for slot in slots if slot["response"] == "SPEAK")
    candidates = [
        slot
        for slot in slots
        if slot["response"] == "WRITE"
        and slot["allowedTypes"][0] in SPEAK_TYPES
        and slot.get("skillKey") not in (exclude or set())
    ]
    rng.shuffle(candidates)
    for slot in candidates[: max(0, missing)]:
        slot["response"] = "SPEAK"


def slot_for(
    skill: Skill, rng, *, allow_speaking: bool = False, types: set[str] | None = None
) -> dict:
    """Pedido de un ejercicio para una skill (lo que la IA debe generar).

    `types` restringe los tipos posibles (ej.: los que admiten respuesta hablada).
    """
    # Preferir tipos con ejemplo semilla: sirve de guía a la IA (y al simulado).
    # read_aloud solo existe hablado: sin conexión con audio no se ofrece (T-183).
    allowed = [
        t for t in skill.exercise_types
        if (types is None or t in types) and (allow_speaking or t not in SPEAK_ONLY_TYPES)
    ]
    seeded = [t for t in allowed if any(e.get("type") == t for e in skill.examples)]
    fallback = [t for t in skill.exercise_types if t not in SPEAK_ONLY_TYPES] or list(skill.exercise_types)
    pool = seeded or allowed or fallback
    exercise_type = rng.choices(pool, weights=[type_weight(t) for t in pool], k=1)[0]
    example = next(
        (e for e in skill.examples if e.get("type") == exercise_type),
        skill.examples[0] if skill.examples else None,
    )
    response = default_response_mode(exercise_type).value
    if allow_speaking and exercise_type in SPEAK_TYPES and rng.random() < SPEAK_SHARE:
        response = ResponseMode.SPEAK.value
    return {
        "skillKey": skill.key,
        "area": skill.area_name,
        "topic": skill.topic_name,
        "skill": skill.name,
        "objectives": list(skill.objectives),
        "allowedTypes": [exercise_type],
        # Modalidades (T-025): el tipo no cambia; cambia cómo se presenta y se responde.
        # Algunos tipos tienen presentación fija (dictado = escucha, ordenar fichas = lectura).
        "presentation": fixed_presentation(exercise_type) or _presentation_for(skill, rng),
        "response": response,
        "example": example,
        # Solo para el proveedor simulado.
        "examples": [e for e in skill.examples if e.get("type") == exercise_type]
        or list(skill.examples),
    }


# ---------------------------------------------------------------- validación


class CommonErrorOut(BaseModel):
    answer: str
    feedback: str = ""
    conceptResults: list[dict] = []


class ExerciseOut(BaseModel):
    skillKey: str
    type: str
    instruction: str = ""
    question: str
    passage: str | None = None
    stimulus: str | None = None
    options: list[str] | None = None
    acceptedAnswers: list[str] = []
    commonErrors: list[CommonErrorOut] = []
    expectedConcepts: list[str] = []
    closing: str | None = None
    # T-183: datos de los tipos con varias partes.
    pairs: list[list[str]] | None = None  # match_pairs: [["kitchen", "cocina"], ...]
    fields: list[dict] | None = None  # listen_form: [{"label": "Name", "acceptedAnswers": ["Anna"]}]
    gaps: list[list[str]] | None = None  # gap_text: respuestas aceptadas por hueco, en orden

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        value = normalize_blank(value.strip())
        if not value:
            raise ValueError("pregunta vacía")
        return value


def _validate_exercise(raw: dict, slot: dict) -> ExerciseOut | None:
    try:
        item = ExerciseOut.model_validate(raw)
    except ValidationError:
        return None
    if item.skillKey != slot["skillKey"] or item.type not in slot["allowedTypes"]:
        return None
    item.acceptedAnswers = [a.strip() for a in item.acceptedAnswers if a and a.strip()]
    if slot.get("presentation") == "LISTEN":
        # El estímulo se escucha: es obligatorio y no puede aparecer escrito en la consigna.
        stimulus = (item.stimulus or item.passage or "").strip()
        if not stimulus or len(stimulus) > STIMULUS_MAX:
            return None
        if item.type not in STIMULUS_MAY_REPEAT and normalize_answer(stimulus) in normalize_answer(
            f"{item.instruction} {item.question} {' '.join(item.options or [])}"
        ):
            return None
        item.stimulus, item.passage = stimulus, None
    else:
        item.stimulus = None
    if item.type in CHOICE_TYPES:
        options = [o.strip() for o in item.options or [] if o and o.strip()]
        if len(options) < 2:
            return None
        # word_stress distingue mayúsculas (ba-NA-na): no se normaliza.
        norm = (lambda v: (v or "").strip()) if item.type in CASE_SENSITIVE_TYPES else normalize_answer
        normalized = {norm(o): o for o in options}
        if len(normalized) != len(options):
            return None  # opciones repetidas
        correct = [normalized.get(norm(a)) for a in item.acceptedAnswers]
        correct = [c for c in correct if c]
        if len(correct) != 1:
            return None
        item.options, item.acceptedAnswers = options, correct
        if (
            item.type == "reading_multiple_choice"
            and slot.get("presentation") != "LISTEN"
            and not (item.passage or "").strip()
        ):
            return None
    elif item.type == "fill_blank":
        if item.question.count(BLANK) != 1 or not item.acceptedAnswers:
            return None
    elif item.type == "rewrite":
        if not item.acceptedAnswers:
            return None
    elif item.type == "short_writing":
        item.acceptedAnswers = []
    elif item.type == "conversation":
        item.acceptedAnswers = []
        item.options = None
        if not item.instruction:
            item.instruction = "Reply naturally."
    elif not _valid_new_type(item, slot):
        return None
    if not item.expectedConcepts:
        item.expectedConcepts = ["task_completion"]
    return item


def _valid_new_type(item: ExerciseOut, slot: dict) -> bool:
    """Reglas de forma de los tipos de T-183 (lo que no cumple, se descarta)."""
    kind = item.type
    if kind == "dictation":
        if slot.get("presentation") != "LISTEN" or not item.acceptedAnswers:
            return False
        item.options = None
        return True
    if kind == "word_order":
        if not item.acceptedAnswers:
            return False
        first = item.acceptedAnswers[0]
        if not WORD_ORDER_MIN <= len(sentence_words(first)) <= WORD_ORDER_MAX:
            return False
        # Todas las variantes tienen que usar las mismas fichas.
        item.acceptedAnswers = [a for a in item.acceptedAnswers if same_words(a, first)]
        item.options = None
        return True
    if kind == "read_aloud":
        target = (item.acceptedAnswers or [item.question])[0].strip()
        if not 2 <= len(sentence_words(target)) <= 20:
            return False
        item.acceptedAnswers = [target]
        item.options = None
        return True
    if kind == "match_pairs":
        pairs = [
            [str(p[0]).strip(), str(p[1]).strip()]
            for p in item.pairs or []
            if isinstance(p, list) and len(p) == 2 and str(p[0]).strip() and str(p[1]).strip()
        ]
        lefts = {normalize_answer(p[0]) for p in pairs}
        rights = {normalize_answer(p[1]) for p in pairs}
        if not PAIRS_MIN <= len(pairs) <= PAIRS_MAX or len(lefts) != len(pairs) or len(rights) != len(pairs):
            return False
        item.pairs, item.acceptedAnswers, item.options = pairs, [], None
        return True
    if kind == "listen_form":
        fields = []
        for field in item.fields or []:
            if not isinstance(field, dict):
                continue
            label = str(field.get("label") or "").strip()
            answers = [str(a).strip() for a in field.get("acceptedAnswers") or [] if str(a).strip()]
            if label and answers:
                fields.append({"label": label, "acceptedAnswers": answers})
        labels = {f["label"].lower() for f in fields}
        if slot.get("presentation") != "LISTEN" or not FIELDS_MIN <= len(fields) <= FIELDS_MAX or len(labels) != len(fields):
            return False
        item.fields, item.acceptedAnswers, item.options = fields, [], None
        return True
    if kind == "gap_text":
        passage = normalize_blank((item.passage or "").strip())
        gaps = [[str(a).strip() for a in g if str(a).strip()] for g in item.gaps or [] if isinstance(g, list)]
        if not passage or passage.count(BLANK) != len(gaps) or not GAPS_MIN <= len(gaps) <= GAPS_MAX:
            return False
        if any(not g for g in gaps):
            return False
        bank = [o.strip() for o in item.options or [] if o and o.strip()]
        if bank and not all(normalize_answer(g[0]) in {normalize_answer(b) for b in bank} for g in gaps):
            return False
        item.passage, item.gaps, item.options, item.acceptedAnswers = passage, gaps, bank or None, []
        return True
    if kind == "error_correction":
        if not item.acceptedAnswers:
            return False
        # La oración dada tiene que estar MAL: si ya es una respuesta aceptada, no hay nada que corregir.
        if normalize_answer(item.question) in {normalize_answer(a) for a in item.acceptedAnswers}:
            return False
        item.options = None
        return True
    return False


def _match_slots(exercises: list, slots: list[dict]) -> list[tuple[dict, ExerciseOut]]:
    """Empareja cada slot con un ejercicio válido de su skill (en orden)."""
    remaining = [e for e in exercises if isinstance(e, dict)]
    matched = []
    for slot in slots:
        for index, raw in enumerate(remaining):
            item = _validate_exercise(raw, slot)
            if item is not None:
                matched.append((slot, item))
                remaining.pop(index)
                break
    return matched


# ---------------------------------------------------------------- flujo


def _content(item: ExerciseOut, level: str | None, slot: dict | None = None) -> dict:
    content = {"options": item.options, "passage": item.passage}
    slot = slot or {}
    if slot.get("conversationGroup"):
        content["conversation"] = {
            "group": slot["conversationGroup"],
            "turn": slot.get("conversationTurn", 1),
            "total": slot.get("conversationTotal", 2),
            "closing": item.closing if slot.get("conversationTurn") == slot.get("conversationTotal") else None,
        }
    if item.type == "word_order" and item.acceptedAnswers:
        content["tiles"] = word_tiles(item.acceptedAnswers[0])
    if item.type == "match_pairs" and item.pairs:
        rights = [p[1] for p in item.pairs]
        content["pairs"] = {"left": [p[0] for p in item.pairs], "right": shuffled(rights, "".join(rights))}
    if item.type == "listen_form" and item.fields:
        content["fields"] = [f["label"] for f in item.fields]
    if item.stimulus:
        # LISTEN: se guarda el texto y la reproducción; el audio se regenera (documento funcional §15).
        content.update(
            stimulus=item.stimulus,
            stimulusLang="en-US",
            stimulusRate=AUDIO_RATE_BY_LEVEL.get(level or "", 1.0),
        )
    return {k: v for k, v in content.items() if v}


def _answer_key(item: ExerciseOut) -> dict:
    key = {
        "acceptedAnswers": item.acceptedAnswers,
        "commonErrors": [e.model_dump() for e in item.commonErrors],
    }
    if item.type == "match_pairs" and item.pairs:
        key["pairs"] = {left: right for left, right in item.pairs}
    if item.type == "listen_form" and item.fields:
        key["fields"] = {f["label"]: f["acceptedAnswers"] for f in item.fields}
    if item.type == "gap_text" and item.gaps:
        key["gaps"] = item.gaps
    return key


def _enough(session: ClassSession, slots: list[dict], matched: list) -> bool:
    """Una clase sirve con la mitad; un examen necesita casi todo y todas las áreas."""
    if session.kind != SessionKind.EXAM:
        return len(matched) >= max(1, len(slots) // 2)
    areas_requested = {s["skillKey"].split(".")[1] for s in slots}
    areas_matched = {slot["skillKey"].split(".")[1] for slot, _ in matched}
    return len(matched) * 4 >= len(slots) * 3 and areas_requested <= areas_matched


def create_class(
    db: Session, study: StudyContext
) -> tuple[ClassSession, AIResult | None]:
    level = study.profile.operational_level or study.profile.selected_level
    curriculum = get_level(level) if level else None
    if curriculum is None:
        raise GenerationFailed("Elegí un nivel disponible antes de pedir una clase.")

    allow_speaking = has_audio_connection(db, study.account)
    focus = weak_abilities(
        ability_progress(db, study.profile.id, curriculum.level), allow_speaking=allow_speaking
    )
    progress = progress_by_skill(db, study.profile.id)
    slots = select_slots(
        list(curriculum.skills),
        progress,
        allow_speaking=allow_speaking,
        focus=focus,
    )
    focus = focus + weak_topics_in(slots, progress)
    # T-191: si el cupo aprendido de la IA no alcanza, la clase sale con menos ejercicios,
    # conservando los que refuerzan lo que más le cuesta al alumno.
    requested = len(slots)
    slots = fit_slots_to_quota(db, study.account, curriculum.level, slots, focus)
    generation_request = {"level": curriculum.level, "slots": slots, "focus": focus}
    if len(slots) < requested:
        generation_request["reducedFrom"] = requested
    session = ClassSession(
        study_profile_id=study.profile.id,
        account_id=study.account.id,
        organization_id=study.organization_id,
        membership_id=study.membership_id,
        status=ClassSessionStatus.GENERATING,
        target_level=curriculum.level,
        generation_request=generation_request,
    )
    db.add(session)
    db.commit()  # persistir la solicitud antes de llamar a la IA
    result = generate_content(db, study, session)
    return session, result


# ---------------------------------------------------------------- T-191 armar según el cupo


def generation_chars(level: str, slots: list[dict], purpose: str = "class") -> int:
    """Tamaño del pedido de generación tal como viajaría a la IA (para estimar tokens)."""
    public = [_public_slot(s) for s in slots]
    return len(GENERATION_SYSTEM) + len(generation_user_prompt(level, public, purpose=purpose))


def _is_focus(slot: dict, focus: list[dict]) -> bool:
    keys = {f.get("key") for f in focus or []}
    area = slot.get("skillKey", "").split(".")[1:2]
    focus_areas = {ABILITY_AREA[k] for k in keys if k in ABILITY_AREA}
    if slot.get("skillKey") in keys or (area and area[0] in focus_areas):
        return True
    return slot.get("response") == "SPEAK" and bool(keys & SPEECH_ABILITIES)


def _drop_one(slots: list[dict], focus: list[dict], minimum: int) -> list[dict] | None:
    """Saca el último ejercicio que no es foco (una conversación sale con sus dos turnos)."""
    for index in range(len(slots) - 1, -1, -1):
        slot = slots[index]
        if _is_focus(slot, focus):
            continue
        group = slot.get("conversationGroup")
        drop = {i for i, s in enumerate(slots) if group and s.get("conversationGroup") == group} or {index}
        if len(slots) - len(drop) < minimum:
            continue
        return [s for i, s in enumerate(slots) if i not in drop]
    return None


def fit_slots_to_quota(db: Session, account, level: str, slots: list[dict], focus: list[dict]) -> list[dict]:
    """Reduce la clase hasta que el pedido entre en el cupo de TOKENS aprendido.
    Si lo que aprieta son los PEDIDOS (por minuto/día), reducir no sirve: se deja igual y el
    router informa hasta cuándo no hay cupo."""
    if not settings.ai_quota_control:
        return slots
    from app.ai.limits import can_run

    def decide(current):
        return can_run(db, account, "generate_class", chars=generation_chars(level, current), items=len(current))

    current = list(slots)
    decision = decide(current)
    while not decision.ok and "TOKENS" in (decision.blocked_by or ""):
        smaller = _drop_one(current, focus, settings.ai_class_min_exercises)
        if smaller is None:
            break
        current = smaller
        decision = decide(current)
    return current if decision.ok else slots


def _generation_diagnostic(slots: list[dict]) -> dict:
    """Composición pedida a la IA; no guarda ejemplos ni contenido curricular."""
    type_counts: dict[str, int] = {}
    presentation_counts: dict[str, int] = {}
    response_counts: dict[str, int] = {}
    conversation_slots = 0
    for slot in slots:
        for exercise_type in slot.get("allowedTypes") or []:
            key = str(exercise_type)
            type_counts[key] = type_counts.get(key, 0) + 1
        presentation = str(slot.get("presentation") or "READ")
        response = str(slot.get("response") or "WRITE")
        presentation_counts[presentation] = presentation_counts.get(presentation, 0) + 1
        response_counts[response] = response_counts.get(response, 0) + 1
        if slot.get("conversationGroup"):
            conversation_slots += 1
    return {
        "slotCount": len(slots),
        "itemCount": len(slots),
        "conversationSlots": conversation_slots,
        "typeCounts": type_counts,
        "presentationCounts": presentation_counts,
        "responseCounts": response_counts,
    }


PROMPT_EXAMPLE_KEYS = ("type", "instruction", "question", "options", "acceptedAnswers", "expectedConcepts")
PROMPT_EXAMPLE_MAX_ANSWERS = 3


def _prompt_example(example: dict | None) -> dict | None:
    """T-178: ejemplo semilla compacto para la IA (formato y nivel, sin pasaje ni conceptResults).

    Conserva un error común de muestra (respuesta + feedback) para que la IA siga generándolos:
    cada error común ahorra después una corrección con IA.
    """
    if not example or not settings.ai_compact_examples:
        return example
    compact = {k: example[k] for k in PROMPT_EXAMPLE_KEYS if example.get(k) not in (None, [], "")}
    if compact.get("acceptedAnswers"):
        compact["acceptedAnswers"] = compact["acceptedAnswers"][:PROMPT_EXAMPLE_MAX_ANSWERS]
    first_error = next(
        (e for e in example.get("commonErrors") or [] if isinstance(e, dict) and e.get("answer")), None
    )
    if first_error:
        compact["commonErrors"] = [
            {"answer": first_error["answer"], "feedback": first_error.get("feedback", "")}
        ]
    return compact


def _public_slot(slot: dict) -> dict:
    """Lo que viaja a la IA: sin `examples` (solo para el simulado) y con el ejemplo compacto."""
    public = {k: v for k, v in slot.items() if k != "examples"}
    if "example" in public:
        public["example"] = _prompt_example(public["example"])
    return public


def generate_content(
    db: Session, study: StudyContext, session: ClassSession
) -> AIResult | None:
    request = session.generation_request or {}
    slots = request.get("slots") or []
    public_slots = [_public_slot(s) for s in slots]
    try:
        result = run_json_task(
            db,
            study.account,
            system=GENERATION_SYSTEM,
            user=generation_user_prompt(
                request.get("level", ""), public_slots, purpose=request.get("purpose", "class")
            ),
            task={
                "kind": "generate_class",
                "level": request.get("level"),
                "slots": slots,
                "schema": GENERATION_SCHEMA,
            },
            usage_context=AIUsageContext(
                organization_id=session.organization_id,
                membership_id=session.membership_id,
                subject_type=session.kind.value,
                subject_id=session.id,
                subject_label=(
                    f"Examen #{session.id}"
                    if session.kind == SessionKind.EXAM
                    else f"Clase #{session.id}"
                ),
                subject_route=f"/app/clase/{session.id}",
                diagnostic=_generation_diagnostic(public_slots),
            ),
        )
    except NoAIAvailable as exc:
        discard_failed_session(db, session, "No hay conexiones de IA disponibles. " + "; ".join(exc.errors))

    # Snapshot histórico del motor que realmente respondió (T-041).
    request = {**request, "ai": connection_snapshot(result.connection)}
    session.generation_request = request

    matched = _match_slots(result.data.get("exercises") or [], slots)
    if not _enough(session, slots, matched):
        message = f"La IA devolvió {len(matched)} ejercicios válidos de {len(slots)} pedidos."
        if session.kind == SessionKind.EXAM:
            message += " El examen necesita ejercicios de todas las áreas."
        discard_failed_session(db, session, message)

    for position, (slot, item) in enumerate(matched):
        skill_key = slot["skillKey"]
        db.add(
            Exercise(
                class_session_id=session.id,
                study_profile_id=session.study_profile_id,
                organization_id=session.organization_id,
                membership_id=session.membership_id,
                position=position,
                level=request.get("level"),
                area=skill_key.split(".")[1],
                skill_key=skill_key,
                exercise_type=item.type,
                instruction=item.instruction,
                prompt=item.question,
                content=_content(item, request.get("level"), slot),
                presentation_mode=PresentationMode(slot.get("presentation", "READ")),
                response_mode=ResponseMode(
                    slot.get("response", default_response_mode(item.type).value)
                ),
                expected_concepts=item.expectedConcepts,
                answer_key=_answer_key(item),
                evaluation_mode=EVALUATION_MODE_BY_TYPE[item.type],
            )
        )
    title = str(result.data.get("title") or "").strip()[:200]
    if session.kind == SessionKind.EXAM:
        session.title = f"Examen de nivel {request.get('level')}"
    else:
        session.title = title or f"Clase {request.get('level')}"
    session.status = ClassSessionStatus.READY
    session.generation_error = None
    session.generated_at = utcnow()
    session.generated_by_connection_id = result.connection.id
    db.commit()
    return result
