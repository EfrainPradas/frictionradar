"""
Friction Radar — Prompt Builders

Separates prompt/text construction from the hypothesis engine.
Designed to be swappable: replace the template builder with an LLM call later.
"""

from typing import List, Dict, Any
from app.core.friction_categories import FRICTION_CATEGORY_LABELS


def build_hypothesis_from_template(
    company_name: str,
    dominant_friction_type: str,
    top_signals: List[str],
    top_categories: List[str],
) -> Dict[str, str]:
    """
    Deterministic, template-based hypothesis generator.
    Returns a dict with: summary, suggested_opportunity.
    Returns a no-diagnosis result when dominant_friction_type is 'no_signal'.
    """
    # Guard: insufficient evidence — no diagnosis to generate
    if dominant_friction_type == "no_signal":
        return {
            "summary": (
                f"{company_name} does not yet have enough qualifying signals "
                f"to determine a dominant friction type."
            ),
            "suggested_opportunity": (
                "Collect more signals from the careers page, about page, "
                "and other sources before generating a hypothesis."
            ),
        }

    label = FRICTION_CATEGORY_LABELS.get(dominant_friction_type, dominant_friction_type)

    # Signal-aware language inserts
    signals_text = " and ".join(
        s.replace("_", " ") for s in top_signals[:3]
    ) if top_signals else "multiple operational signals"

    category_text = ", ".join(
        FRICTION_CATEGORY_LABELS.get(c, c) for c in top_categories[:2]
    ) if top_categories else label

    # Templates keyed by friction type
    templates = {
        "reporting_fragmentation": {
            "summary": (
                f"{company_name} likely has fragmented reporting visibility driven by "
                f"{signals_text}. Evidence suggests growing demand for analytics and "
                f"structured data access across functions."
            ),
            "suggested_opportunity": (
                f"Opportunity to introduce a unified reporting layer that improves visibility "
                f"across departments, reducing reliance on siloed tools and ad-hoc exports."
            ),
        },
        "process_inefficiency": {
            "summary": (
                f"{company_name} shows signs of process inefficiency, indicated by "
                f"{signals_text}. Revenue operations and workflow coordination appear strained."
            ),
            "suggested_opportunity": (
                f"Opportunity to streamline workflows and reduce manual handoffs, enabling "
                f"faster cross-team execution and freeing up RevOps bandwidth."
            ),
        },
        "tooling_inconsistency": {
            "summary": (
                f"{company_name} appears to be operating with an inconsistent tool stack. "
                f"Multiple platform references and {signals_text} suggest integration debt."
            ),
            "suggested_opportunity": (
                f"Opportunity to consolidate tooling or introduce integration middleware "
                f"to reduce context-switching and data fragmentation across systems."
            ),
        },
        "scaling_strain": {
            "summary": (
                f"{company_name} is actively scaling, as evidenced by {signals_text}. "
                f"Fast growth often introduces operational strain before infrastructure catches up."
            ),
            "suggested_opportunity": (
                f"Opportunity to support scaling teams with structured onboarding, process "
                f"documentation, and operational frameworks before friction compounds."
            ),
        },
        "customer_experience_friction": {
            "summary": (
                f"{company_name} displays signals of customer-facing friction, including "
                f"{signals_text}. Product or support pain points may be impacting retention."
            ),
            "suggested_opportunity": (
                f"Opportunity to investigate CX pain points and introduce feedback loops, "
                f"improved self-serve options, or customer journey redesign."
            ),
        },
    }

    # Fallback for unknown category
    default_template = {
        "summary": (
            f"{company_name} shows operational friction signals in the area of {label}. "
            f"Detected signals include: {signals_text}."
        ),
        "suggested_opportunity": (
            f"Opportunity to diagnose and reduce {label} friction through targeted operational improvements."
        ),
    }

    return templates.get(dominant_friction_type, default_template)


def build_llm_prompt(
    company_name: str,
    dominant_friction_type: str,
    breakdown: Dict[str, Any],
    top_signals: List[str],
) -> str:
    """
    Constructs a structured prompt for future LLM integration.
    Use this when wiring in OpenAI, Anthropic, or Gemini.
    """
    signals_display = "\n".join(f"  - {s}" for s in top_signals)
    breakdown_display = "\n".join(
        f"  {cat}: {data['score']} ({', '.join(data['matched_signals']) or 'none'})"
        for cat, data in breakdown.items()
    )

    return (
        f"You are a senior operations analyst. A company called '{company_name}' "
        f"has been analyzed for operational friction.\n\n"
        f"Dominant friction type: {dominant_friction_type}\n\n"
        f"Scoring breakdown:\n{breakdown_display}\n\n"
        f"Top matched signals:\n{signals_display}\n\n"
        f"Generate a short executive summary (2-3 sentences) and a specific opportunity statement "
        f"that a consulting or SaaS company could act on. Be concise and business-focused."
    )
