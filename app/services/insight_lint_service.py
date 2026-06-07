from __future__ import annotations

import re


NEGATION_CUES = [
    "bukan",
    "tidak",
    "tidak boleh",
    "belum",
    "belum cukup",
    "belum menjadi",
    "bukan sebagai",
    "tidak digunakan sebagai",
    "tidak boleh digunakan sebagai",
    "belum boleh",
    "belum boleh diperlakukan sebagai",
]


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _remove_required_disclaimer(normalized_text: str, required_disclaimer: str) -> str:
    """
    Agar frasa yang muncul di dalam disclaimer wajib tidak dihitung sebagai pelanggaran.
    """
    if not required_disclaimer:
        return normalized_text

    normalized_disclaimer = _normalize_text(required_disclaimer)

    if normalized_disclaimer in normalized_text:
        return normalized_text.replace(normalized_disclaimer, " ")

    return normalized_text


def _occurrences_are_negated(text: str, phrase: str, window: int = 80) -> bool:
    """
    Mengembalikan True jika semua kemunculan phrase berada dalam konteks negasi.
    Contoh aman:
    - bukan advisory operasional
    - tidak boleh digunakan sebagai advisory operasional
    - belum menjadi advisory operasional penuh
    """
    positions = [m.start() for m in re.finditer(re.escape(phrase), text)]

    if not positions:
        return False

    for pos in positions:
        left = text[max(0, pos - window):pos]
        if not any(cue in left for cue in NEGATION_CUES):
            return False

    return True


def lint_insight_text(text: str, guardrail_payload: dict) -> dict:
    guardrail = guardrail_payload.get("guardrail", {})

    forbidden_phrases = guardrail.get("forbidden_phrases", [])
    allowed_phrases = guardrail.get("allowed_phrases", [])
    required_disclaimer = guardrail.get("required_disclaimer", "")

    readiness_level = guardrail.get("readiness_level")
    advisory_allowed = guardrail.get("advisory_allowed", False)
    allowed_claim_level = guardrail.get("allowed_claim_level")

    normalized = _normalize_text(text)
    normalized_for_forbidden = _remove_required_disclaimer(normalized, required_disclaimer)

    violations = []
    matched_forbidden = []

    disclaimer_present = True
    if required_disclaimer:
        disclaimer_present = _normalize_text(required_disclaimer) in normalized

        if not disclaimer_present:
            violations.append({
                "type": "missing_required_disclaimer",
                "phrase": required_disclaimer,
                "message": "Disclaimer wajib belum ditemukan dalam teks insight.",
            })

    for phrase in forbidden_phrases:
        phrase_norm = _normalize_text(phrase)

        if phrase_norm in normalized_for_forbidden:
            # Jika phrase muncul dalam konteks negasi, jangan dianggap pelanggaran.
            if _occurrences_are_negated(normalized_for_forbidden, phrase_norm):
                continue

            matched_forbidden.append(phrase)
            violations.append({
                "type": "forbidden_phrase",
                "phrase": phrase,
                "message": f"Frasa '{phrase}' tidak boleh digunakan pada readiness level {readiness_level}.",
            })

    risky_patterns = [
        "disarankan",
        "wajib melaut",
        "pasti",
        "jaminan",
        "lokasi terbaik",
        "zona utama",
        "tangkap utama",
    ]

    matched_risky = []

    if not advisory_allowed:
        for pattern in risky_patterns:
            if pattern in normalized_for_forbidden:
                # Contoh "tidak disarankan" jangan dianggap terlalu operasional.
                if _occurrences_are_negated(normalized_for_forbidden, pattern):
                    continue

                matched_risky.append(pattern)
                violations.append({
                    "type": "risky_operational_language",
                    "phrase": pattern,
                    "message": (
                        f"Bahasa '{pattern}' terlalu operasional untuk status "
                        f"{readiness_level}."
                    ),
                })

    matched_allowed = [
        phrase for phrase in allowed_phrases
        if _normalize_text(phrase) in normalized
    ]

    passed = len(violations) == 0

    if passed:
        verdict = "passed"
        message = "Teks insight sesuai dengan guardrail."
    else:
        verdict = "failed"
        message = "Teks insight mengandung klaim atau kekurangan disclaimer yang perlu diperbaiki."

    return {
        "module": "insight_lint",
        "version": "0.1.2",
        "snapshot_date": guardrail_payload.get("snapshot_date"),
        "result": {
            "passed": passed,
            "verdict": verdict,
            "message": message,
            "readiness_level": readiness_level,
            "advisory_allowed": advisory_allowed,
            "allowed_claim_level": allowed_claim_level,
            "violations_count": len(violations),
            "violations": violations,
            "matched_forbidden_phrases": matched_forbidden,
            "matched_risky_patterns": matched_risky,
            "matched_allowed_phrases": matched_allowed,
            "required_disclaimer_present": disclaimer_present,
        },
        "guardrail_summary": {
            "required_disclaimer": required_disclaimer,
            "forbidden_phrases": forbidden_phrases,
            "allowed_phrases": allowed_phrases,
        },
    }
