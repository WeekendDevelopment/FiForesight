"""
Tests for AnalystJuryService._parse_analyst_response — the structured-verdict
parser. No network: the parser is a pure staticmethod over the raw model string.

Focus: malformed model output (e.g. GPT-OSS / reasoning models emitting an
unbalanced object) must never leak JSON punctuation like "}}" into the
user-facing note.
"""
from backend.services import AnalystJuryService

parse = AnalystJuryService._parse_analyst_response


def test_parses_clean_json() -> None:
    raw = '{"rating": "Buy", "note": "Momentum is strong.", "confidence": 72}'
    out = parse(raw, persona_id="GPT-OSS-20B", model="openai/gpt-oss-20b")
    assert out["rating"] == "Buy"
    assert out["note"] == "Momentum is strong."
    assert out["confidence"] == 72


def test_trailing_double_brace_does_not_leak() -> None:
    """An unbalanced trailing '}}' must not appear in the salvaged note."""
    # Unbalanced/garbled tail forces the last-resort path.
    raw = 'Accumulate. {"rating": "Accumulate", "note": "RSI 45, MACD turning up.", "confidence": 63}}'
    out = parse(raw, persona_id="GPT-OSS-20B", model="openai/gpt-oss-20b")
    assert "}" not in out["note"] and "{" not in out["note"]
    assert "}}" not in out["note"]


def test_last_resort_salvages_note_field() -> None:
    """When JSON is broken but a note field is present, it should be lifted out."""
    raw = '{"rating": "Hold" "note": "Choppy, no edge here.", "confidence": 50'  # missing comma + unterminated
    out = parse(raw, persona_id="GPT-OSS-20B", model="openai/gpt-oss-20b")
    assert "Choppy, no edge here." in out["note"]
    assert "{" not in out["note"] and "}" not in out["note"]


def test_plain_text_no_brace_leak() -> None:
    raw = "Strong Buy — breakout confirmed on volume. Confidence 80%."
    out = parse(raw, persona_id="GPT-OSS-20B", model="openai/gpt-oss-20b")
    assert out["rating"] == "Strong Buy"
    assert out["confidence"] == 80
    assert "{" not in out["note"] and "}" not in out["note"]


def test_think_block_stripped() -> None:
    raw = '<think>let me reason about this...</think>{"rating": "Sell", "note": "Breaking support.", "confidence": 40}'
    out = parse(raw, persona_id="GPT-OSS-20B", model="openai/gpt-oss-20b")
    assert out["rating"] == "Sell"
    assert "<think>" not in out["note"]


def test_note_never_empty() -> None:
    """Even with unusable content, the note is a non-empty fallback string."""
    raw = "{}{}{}"
    out = parse(raw, persona_id="GPT-OSS-20B", model="openai/gpt-oss-20b")
    assert isinstance(out["note"], str) and out["note"].strip()
    assert "{" not in out["note"] and "}" not in out["note"]
