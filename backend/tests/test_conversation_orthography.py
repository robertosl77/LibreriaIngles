"""T-048: Conversation curricular + Ortografía dentro de Writing."""

import random
from types import SimpleNamespace as NS

from app.classes.evaluation import _add_mechanics_evidence, evaluate
from app.classes.generation import _validate_exercise, pair_conversation_slots
from app.curriculum.service import get_level
from app.exams.service import exam_slots
from app.learning.models import Attempt, EvaluationMode, Exercise, PresentationMode, ResponseMode
from app.db import SessionLocal
from app.progress.service import recompute_skill
from conftest import login
from sqlalchemy import select

API = "/api/v1"


def _orthography_exercise(skill_key: str, answer: str):
    skill = get_level("A1").skill(skill_key)
    example = skill.examples[0]
    return NS(
        id=1,
        level="A1",
        area="writing",
        skill_key=skill_key,
        exercise_type=example["type"],
        prompt=example["question"],
        content={},
        presentation_mode=PresentationMode.READ,
        response_mode=ResponseMode.WRITE,
        evaluation_mode=EvaluationMode.HYBRID,
        answer_key={"acceptedAnswers": example["acceptedAnswers"], "commonErrors": []},
        expected_concepts=example["expectedConcepts"],
    ), answer


def test_a1_has_conversation_and_orthography_curriculum() -> None:
    keys = {s.key for s in get_level("A1").skills}
    assert {
        "a1.conversation.social_basics.greetings",
        "a1.conversation.social_basics.introductions",
        "a1.conversation.personal_information.basic_details",
        "a1.conversation.everyday_exchanges.simple_requests",
        "a1.conversation.everyday_exchanges.farewells",
        "a1.writing.orthography.capitalization",
        "a1.writing.orthography.basic_spelling",
        "a1.writing.orthography.punctuation",
        "a1.writing.orthography.apostrophes",
    } <= keys


def test_conversation_is_open_ai_evaluated_item() -> None:
    slot = {
        "skillKey": "a1.conversation.social_basics.introductions",
        "allowedTypes": ["conversation"],
        "presentation": "READ",
    }
    item = _validate_exercise(
        {
            "skillKey": slot["skillKey"],
            "type": "conversation",
            "instruction": "Reply naturally.",
            "question": "Hi, I'm Emma. What's your name?",
            "acceptedAnswers": ["My name is Ana."],
            "expectedConcepts": ["give_name"],
        },
        slot,
    )
    assert item is not None
    assert item.acceptedAnswers == []


def test_conversation_pair_shares_modalities_and_turn_numbers() -> None:
    slots = [
        {
            "skillKey": "a1.conversation.social_basics.greetings",
            "allowedTypes": ["conversation"],
            "presentation": "READ",
            "response": "WRITE",
        },
        {
            "skillKey": "a1.conversation.social_basics.introductions",
            "allowedTypes": ["conversation"],
            "presentation": "LISTEN",
            "response": "SPEAK",
        },
    ]
    pair_conversation_slots(slots)
    assert [s["conversationTurn"] for s in slots] == [1, 2]
    assert slots[0]["conversationGroup"] == slots[1]["conversationGroup"]
    assert all(s["presentation"] == "LISTEN" for s in slots)
    assert all(s["response"] == "SPEAK" for s in slots)


def test_written_conversation_leaves_orthography_evidence_without_changing_primary_score() -> None:
    exercise = NS(
        level="A1",
        area="conversation",
        skill_key="a1.conversation.social_basics.introductions",
        exercise_type="conversation",
        response_mode=ResponseMode.WRITE,
    )
    primary = {
        "result": "correct",
        "errors": [],
        "secondarySkillResults": [],
    }
    result = _add_mechanics_evidence(exercise, "i am robert", primary, spoken=False)
    secondary = {item["skillKey"]: item for item in result["secondarySkillResults"]}
    assert secondary["a1.writing.orthography.capitalization"]["score"] == 60
    assert secondary["a1.writing.orthography.punctuation"]["score"] == 60
    assert result["result"] == "correct"


def test_capitalization_and_punctuation_are_not_lost_by_normalization() -> None:
    exercise, _ = _orthography_exercise(
        "a1.writing.orthography.capitalization", "I am Lucas and I live in Rosario."
    )
    correct = evaluate(None, None, exercise, "I am Lucas and I live in Rosario.")
    wrong_case = evaluate(None, None, exercise, "i am lucas and i live in rosario.")
    assert correct.score == 100
    assert wrong_case.score == 60

    punctuation, _ = _orthography_exercise(
        "a1.writing.orthography.punctuation", "Where are you from?"
    )
    assert evaluate(None, None, punctuation, "Where are you from?").score == 100
    assert evaluate(None, None, punctuation, "Where are you from").score == 60


def test_exam_guarantees_conversation_pair_and_orthography() -> None:
    slots = exam_slots("A1", rng=random.Random(7), allow_speaking=True)
    conversation = [s for s in slots if s["skillKey"].startswith("a1.conversation.")]
    assert len(conversation) == 2
    assert conversation[0]["conversationGroup"] == conversation[1]["conversationGroup"]
    assert {s["conversationTurn"] for s in conversation} == {1, 2}
    assert any(".writing.orthography." in s["skillKey"] for s in slots)


def test_secondary_curricular_evidence_reaches_orthography_dashboard(client) -> None:
    headers = login(client, "t048-secondary@example.com")
    client.put(f"{API}/me/level", json={"level": "A1"}, headers=headers)
    client.post(
        f"{API}/ai/connections",
        json={"provider": "MOCK", "name": "Simulado", "model": "mock", "priority": 1},
        headers=headers,
    )
    klass = client.post(f"{API}/classes", headers=headers).json()
    answers = {}
    with SessionLocal() as db:
        exercises = list(
            db.scalars(select(Exercise).where(Exercise.class_session_id == klass["id"])).all()
        )
        used = {e.skill_key for e in exercises}
        target_key = next(
            key for key in (
                "a1.writing.orthography.apostrophes",
                "a1.writing.orthography.basic_spelling",
            )
            if key not in used
        )
        for exercise in exercises:
            accepted = exercise.answer_key.get("acceptedAnswers") or []
            if exercise.exercise_type == "conversation":
                answers[str(exercise.id)] = "Hi! I am Ana."
            elif exercise.exercise_type == "short_writing":
                answers[str(exercise.id)] = "I live in Rosario. I study English every day."
            elif accepted:
                answers[str(exercise.id)] = accepted[0]
            else:
                answers[str(exercise.id)] = "I am Ana."

    submitted = client.post(
        f"{API}/classes/{klass['id']}/submit", json={"answers": answers}, headers=headers
    )
    assert submitted.status_code == 200

    with SessionLocal() as db:
        rows = db.execute(
            select(Attempt, Exercise)
            .join(Exercise, Exercise.id == Attempt.exercise_id)
            .where(Exercise.class_session_id == klass["id"])
        ).all()
        attempt, exercise = next(
            (attempt, exercise)
            for attempt, exercise in rows
            if attempt.response_mode == ResponseMode.WRITE and exercise.skill_key != target_key
        )
        result = dict(attempt.evaluation_result or {})
        result["secondarySkillResults"] = [
            {"skillKey": target_key, "status": "partially_correct", "score": 60, "reason": "evidencia incidental"}
        ]
        attempt.evaluation_result = result
        profile_id = attempt.study_profile_id
        recompute_skill(db, study_profile_id=profile_id, skill_key=target_key)
        db.commit()

    dashboard = client.get(f"{API}/progress", headers=headers).json()
    skill = next(
        s for area in dashboard["areas"] for topic in area["topics"] for s in topic["skills"]
        if s["key"] == target_key
    )
    assert 0 < skill["score"] <= 100
    assert skill["attemptCount"] >= 1
    assert dashboard["orthography"]["skillsPracticed"] >= 1
    assert dashboard["orthography"]["score"] is not None
