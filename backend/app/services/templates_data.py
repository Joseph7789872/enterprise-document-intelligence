"""Starter-template content (in-repo constants).

A manager can apply one of these to a fresh tenant so the team isn't staring at an empty
box on day one: it seeds segments, ramp-checklist topics, and a saved-objection library
(objections tagged by segment name). Pure data — :mod:`app.services.template_service`
turns it into rows. Keep it small and realistic; these are starting points teams edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TemplateObjection:
    label: str
    prompt: str
    # Segment names (must appear in the template's ``segments``) to tag this objection.
    segments: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    description: str
    segments: list[str]
    # (title, suggested_question) pairs for the ramp checklist.
    ramp_topics: list[tuple[str, str]]
    objections: list[TemplateObjection]


_B2B_SAAS = Template(
    key="b2b_saas",
    name="B2B SaaS Sales",
    description="Segments, ramp checklist, and an objection library for a horizontal B2B "
    "SaaS team selling to Enterprise and SMB buyers.",
    segments=["Enterprise", "Mid-Market", "SMB"],
    ramp_topics=[
        ("Product overview", "What does our product do and what core problem does it solve?"),
        ("Pricing & packaging", "How is our product priced and packaged?"),
        ("Ideal customer profile", "Who is our ICP and which segments do we sell to?"),
        ("Competitive positioning", "How do we position against our main competitors?"),
        ("Discovery questions", "What discovery questions should I ask on a first call?"),
        ("Demo flow", "What is the recommended demo flow and which features matter most?"),
        ("Security & compliance", "What security and compliance assurances can I share?"),
    ],
    objections=[
        TemplateObjection(
            "Too expensive",
            "How do I handle the objection that our product is too expensive?",
            ["Enterprise", "Mid-Market", "SMB"],
        ),
        TemplateObjection(
            "Already using a competitor",
            "How do I handle a prospect who is already using a competitor?",
            ["Enterprise", "Mid-Market"],
        ),
        TemplateObjection(
            "No budget right now",
            "How do I handle 'we have no budget right now'?",
            ["SMB", "Mid-Market"],
        ),
        TemplateObjection(
            "Need to involve security/IT",
            "How do I handle a deal that stalls on a security or IT review?",
            ["Enterprise"],
        ),
        TemplateObjection(
            "Happy with the status quo",
            "How do I handle a prospect who says they're happy with the status quo?",
            ["Enterprise", "Mid-Market", "SMB"],
        ),
    ],
)

_SMB_FOCUSED = Template(
    key="smb_velocity",
    name="SMB High-Velocity",
    description="A lean template for a high-velocity SMB motion: one segment, a short ramp "
    "checklist, and the objections that come up most in fast self-serve-adjacent deals.",
    segments=["SMB"],
    ramp_topics=[
        ("Product in one sentence", "How do I describe our product in one sentence?"),
        ("Pricing", "What are our plans and prices?"),
        ("Top use cases", "What are the top use cases buyers adopt us for?"),
        ("Fast objection handling", "What are the most common objections and quick responses?"),
    ],
    objections=[
        TemplateObjection("Too expensive", "How do I handle 'it's too expensive'?", ["SMB"]),
        TemplateObjection("I'll think about it", "How do I handle 'let me think on it'?", ["SMB"]),
        TemplateObjection(
            "Does it integrate with X?",
            "How do I handle 'does it integrate with the tools we already use?'",
            ["SMB"],
        ),
    ],
)


TEMPLATES: dict[str, Template] = {t.key: t for t in (_B2B_SAAS, _SMB_FOCUSED)}
