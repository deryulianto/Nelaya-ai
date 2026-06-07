from __future__ import annotations

from app.services.insight_lint_service import lint_insight_text


def build_safe_insight_pipeline(guarded_payload: dict) -> dict:
    guarded = guarded_payload.get("guarded_insight", {})
    guardrail = guarded_payload.get("guardrail", {})

    full_text = guarded.get("full_text", "")

    guardrail_payload = {
        "snapshot_date": guarded_payload.get("snapshot_date"),
        "guardrail": guardrail,
    }

    lint_result = lint_insight_text(full_text, guardrail_payload)

    lint_passed = lint_result.get("result", {}).get("passed", False)
    advisory_allowed = guarded.get("advisory_allowed", False)

    if lint_passed:
        publish_allowed = True
        publish_status = "safe_to_publish_as_limited_insight"
        publish_message = (
            "Narasi aman dipublish sesuai guardrail. Namun status advisory tetap mengikuti readiness."
        )
    else:
        publish_allowed = False
        publish_status = "needs_revision"
        publish_message = (
            "Narasi belum aman dipublish karena masih melanggar guardrail."
        )

    if advisory_allowed:
        content_role = "decision_support_insight"
    else:
        content_role = "public_ocean_insight_only"

    return {
        "module": "safe_insight_pipeline",
        "version": "0.1.0",
        "snapshot_date": guarded_payload.get("snapshot_date"),
        "publish_decision": {
            "publish_allowed": publish_allowed,
            "publish_status": publish_status,
            "publish_message": publish_message,
            "advisory_allowed": advisory_allowed,
            "content_role": content_role,
        },
        "final_insight": guarded,
        "lint": {
            "module": lint_result.get("module"),
            "version": lint_result.get("version"),
            **lint_result.get("result", {}),
        },
        "guardrail": guardrail,
        "source_confidence": guarded_payload.get("source_confidence", {}),
    }
