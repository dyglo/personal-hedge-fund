from __future__ import annotations

import re


ADVANCED_TERMS = (
    "fvg",
    "fair value gap",
    "liquidity sweep",
    "confluence",
    "market structure",
    "hh",
    "hl",
    "lh",
    "ll",
    "fibonacci",
    "retracement",
    "imbalance",
    "inducement",
    "order block",
    "premium",
    "discount",
    "risk-reward",
    "rr",
    "lot size",
    "pip",
    "spread",
    "session high",
    "session low",
)

BEGINNER_PATTERNS = (
    r"\bwhat does .+ mean\b",
    r"\bhow do i\b",
    r"\bi'?m not sure\b",
    r"\bcan you explain\b",
    r"\bis this good\b",
    r"\bwhat should i do\b",
    r"\bwhat is a candle\b",
    r"\bwhat are candles\b",
    r"\bwhat is a trend\b",
    r"\bwhat is trend\b",
    r"\bshould i buy or sell\b",
    r"\bwhen do i buy\b",
    r"\bwhen do i sell\b",
)
TRADING_TERMS = {
    "fvg",
    "bias",
    "liquidity",
    "confluence",
    "trend",
    "support",
    "resistance",
    "candles",
    "candle",
    "buy",
    "sell",
    "entry",
    "stop",
    "risk",
    "reward",
    "pip",
    "rr",
    "fib",
    "fibonacci",
}


def detect_skill_signals(messages: list[str], current_level: str | None = None) -> dict:
    safe_messages = [str(message or "").strip() for message in messages or [] if str(message or "").strip()]
    advanced_signals = 0
    beginner_signals = 0
    observed_advanced_terms: list[str] = []
    observed_beginner_signals: list[str] = []

    for message in safe_messages:
        normalized = _normalize(message)
        if not normalized:
            continue

        for term in ADVANCED_TERMS:
            if _contains_term(normalized, term):
                advanced_signals += 1
                if term not in observed_advanced_terms:
                    observed_advanced_terms.append(term)

        for pattern in BEGINNER_PATTERNS:
            if re.search(pattern, normalized):
                beginner_signals += 1
                matched = re.search(pattern, normalized)
                if matched:
                    signal = matched.group(0)
                    if signal not in observed_beginner_signals:
                        observed_beginner_signals.append(signal)

        if _is_short_beginner_message(normalized):
            beginner_signals += 1
            if "short_basic_message" not in observed_beginner_signals:
                observed_beginner_signals.append("short_basic_message")

        if _asks_basic_concept_question(normalized):
            beginner_signals += 1
            if "basic_concept_question" not in observed_beginner_signals:
                observed_beginner_signals.append("basic_concept_question")

    total_hits = advanced_signals + beginner_signals
    confidence = "low"
    if 2 <= total_hits <= 4:
        confidence = "medium"
    elif total_hits >= 5:
        confidence = "high"

    suggested_level = "intermediate"
    if advanced_signals >= 8 and beginner_signals <= 1:
        suggested_level = "professional"
    elif 5 <= advanced_signals <= 7 and beginner_signals <= 2:
        suggested_level = "experienced"
    elif 2 <= advanced_signals <= 4:
        suggested_level = "intermediate"
    elif advanced_signals <= 1 and beginner_signals >= 3:
        suggested_level = "beginner"

    current = (current_level or "").strip().lower() or None
    should_suggest = (
        len(safe_messages) >= 3
        and confidence == "high"
        and current is not None
        and suggested_level != current
    )

    return {
        "advanced_signals": advanced_signals,
        "beginner_signals": beginner_signals,
        "suggested_level": suggested_level,
        "confidence": confidence,
        "should_suggest": should_suggest,
        "observed_advanced_terms": observed_advanced_terms[:5],
        "observed_beginner_signals": observed_beginner_signals[:5],
    }


def _normalize(message: str) -> str:
    return re.sub(r"\s+", " ", str(message or "").strip().lower())


def _contains_term(message: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    if " " in term or "-" in term:
        return re.search(rf"(?<!\w){escaped}(?!\w)", message) is not None
    return re.search(rf"\b{escaped}\b", message) is not None


def _is_short_beginner_message(message: str) -> bool:
    words = re.findall(r"\b[\w'-]+\b", message)
    return 0 < len(words) <= 4 and not any(term in message for term in TRADING_TERMS)


def _asks_basic_concept_question(message: str) -> bool:
    if "?" not in message:
        return False
    return any(
        phrase in message
        for phrase in (
            "what is a candle",
            "what are candles",
            "what is trend",
            "what is a trend",
            "buy or sell",
            "is this a buy",
            "is this a sell",
        )
    )
