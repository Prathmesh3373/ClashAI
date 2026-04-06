from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .planner import AnswerPlan
from .requirements import Obligation, RequirementSpec, tokenize_keywords


@dataclass(slots=True)
class FulfillmentReport:
    answered: list[str] = field(default_factory=list)
    partially_answered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    structure_violations: list[str] = field(default_factory=list)
    format_violations: list[str] = field(default_factory=list)
    repair_needed: bool = False
    fulfillment_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9\s]', ' ', text.lower())).strip()


def _obligation_coverage(obligation: Obligation, answer: str) -> tuple[str, float]:
    answer_tokens = set(_normalize(answer).split())
    obligation_tokens = [token for token in obligation.keywords if token] or tokenize_keywords(obligation.text)
    if not obligation_tokens:
        return 'partial', 0.5

    hits = sum(1 for token in obligation_tokens if token in answer_tokens)
    ratio = hits / max(1, len(obligation_tokens))
    if ratio >= 0.6:
        return 'answered', ratio
    if ratio >= 0.3:
        return 'partial', ratio
    return 'missing', ratio


def _has_step_structure(answer: str) -> bool:
    return bool(re.search(r'(?m)^\s*(?:step\s+\d+|\d+[.)])', answer.lower()))


def _has_example(answer: str) -> bool:
    lowered = answer.lower()
    return 'for example' in lowered or 'example:' in lowered or 'e.g.' in lowered


def check_answer_fulfillment(requirements: RequirementSpec, plan: AnswerPlan, answer: str) -> FulfillmentReport:
    report = FulfillmentReport()

    for obligation in requirements.obligations:
        status, _ratio = _obligation_coverage(obligation, answer)
        if status == 'answered':
            report.answered.append(obligation.id)
        elif status == 'partial':
            report.partially_answered.append(obligation.id)
        else:
            report.missing.append(obligation.id)

    if requirements.grouping:
        lowered = answer.lower()
        for group in requirements.grouping:
            if group.lower() not in lowered:
                report.structure_violations.append(f'Missing required section heading: {group}')

    if requirements.format_constraints.step_by_step and not _has_step_structure(answer):
        report.format_violations.append('Step-by-step structure was requested but not followed.')

    if requirements.format_constraints.examples_required and not _has_example(answer):
        report.format_violations.append('Examples were requested but no explicit example was found.')

    if requirements.format_constraints.list_advantages_disadvantages:
        lowered = answer.lower()
        if 'advantage' not in lowered or 'disadvantage' not in lowered:
            report.format_violations.append('Advantages and disadvantages were requested but not both were clearly covered.')

    answered_count = len(report.answered)
    partial_count = len(report.partially_answered)
    total = max(1, len(requirements.obligations))
    completeness_score = (answered_count + 0.5 * partial_count) / total
    structure_penalty = min(0.25, 0.08 * len(report.structure_violations))
    format_penalty = min(0.25, 0.08 * len(report.format_violations))
    report.fulfillment_score = round(max(0.0, min(1.0, completeness_score - structure_penalty - format_penalty)), 3)
    report.repair_needed = bool(report.missing or report.structure_violations or report.format_violations)
    return report


def build_repair_prompt(requirements: RequirementSpec, plan: AnswerPlan, draft_answer: str, report: FulfillmentReport) -> str:
    missing_obligations = [obligation for obligation in requirements.obligations if obligation.id in report.missing or obligation.id in report.partially_answered]
    missing_lines = '\n'.join(f'- {obligation.id}: {obligation.text}' for obligation in missing_obligations) or '- None'
    section_lines = '\n'.join(f'- {section.title}: {section.guidance}' for section in plan.sections) or '- None'
    structure_lines = '\n'.join(f'- {item}' for item in report.structure_violations) or '- None'
    format_lines = '\n'.join(f'- {item}' for item in report.format_violations) or '- None'

    return f"""
You are repairing an answer, not rewriting it from scratch.
Keep the useful parts of the draft. Only fix the missing, weak, or structurally incorrect parts.

Original user request:
{requirements.raw_request}

Required answer plan:
{section_lines}

Current draft answer:
{draft_answer}

Missing or weak obligations:
{missing_lines}

Structure violations:
{structure_lines}

Format violations:
{format_lines}

Instructions:
- preserve good existing content where possible
- fill the missing obligations explicitly
- restore required structure and formatting
- if step by step was requested, use numbered steps
- if grouped sections were requested, use those headings exactly
- if examples were requested, add at least one concrete example
- return only the repaired final answer
""".strip()
