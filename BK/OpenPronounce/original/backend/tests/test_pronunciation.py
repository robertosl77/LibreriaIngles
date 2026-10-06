"""T-027: adaptación estable de resultados OpenPronounce."""

from app.pronunciation import _normalize_phone_result


def test_openpronounce_result_is_normalized_for_dashboard_contract() -> None:
    raw = {
        "phone_error_rate": 0.24,
        "expected_phones": [["aɪ"], ["d", "oʊ", "n", "t"], ["n", "oʊ"]],
        "heard_phones": ["aɪ", "d", "oʊ", "n", "t", "n", "o"],
        "errors": [
            {
                "word": "unknown",
                "confidence": 0.7,
                "phones": [
                    {"expected": "n", "heard": "m", "confidence": 0.8},
                    {"expected": "oʊ", "heard": "o", "confidence": 0.5},
                ],
            }
        ],
    }

    result = _normalize_phone_result(raw, "I don't know this unknown word")

    assert result is not None
    assert result["score"] == 76
    assert result["provider"] == "OPENPRONOUNCE"
    assert result["fluency"] is None
    unknown = next(item for item in result["words"] if item["word"] == "unknown")
    assert unknown["score"] == 30
    assert result["phonemes"][0] == {"phoneme": "n", "word": "unknown", "score": 20}
    assert result["assessedAt"]
