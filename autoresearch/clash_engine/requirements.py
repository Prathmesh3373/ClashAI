from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'do', 'for', 'from', 'how', 'i', 'if', 'in', 'is', 'it',
    'of', 'on', 'or', 'please', 'should', 'show', 'the', 'to', 'use', 'what', 'with', 'write', 'you', 'your'
}
GROUPING_PATTERN = re.compile(r'\b(Unit\s+\d+|Part\s+[A-Z0-9]+|Section\s+\d+|Chapter\s+\d+)\b', re.IGNORECASE)
NUMBERED_ITEM_PATTERN = re.compile(r'(?m)^\s*(\d+)[.)]\s+(.+)$')
BULLET_ITEM_PATTERN = re.compile(r'(?m)^\s*[-*]\s+(.+)$')
QUESTION_SPLIT_PATTERN = re.compile(r'\?+')
KEYWORD_TASK_TYPES = {
    'compare': 'comparison',
    'derive': 'derivation',
    'explain': 'explanation',
    'solve': 'problem_solving',
    'plan': 'planning',
    'recommend': 'decision',
    'advantages': 'analysis',
    'disadvantages': 'analysis',
}


@dataclass(slots=True)
class FormatConstraints:
    step_by_step: bool = False
    detailed: bool = False
    examples_required: bool = False
    compare_required: bool = False
    derivation_required: bool = False
    explain_required: bool = False
    list_advantages_disadvantages: bool = False
    strict_structure: bool = False
    requested_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Obligation:
    id: str
    text: str
    kind: str = 'coverage'
    group: str | None = None
    required: bool = True
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RequirementSpec:
    raw_request: str
    task_type: str
    obligations: list[Obligation]
    format_constraints: FormatConstraints
    subquestions: list[str]
    grouping: list[str]
    completeness_constraints: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            'raw_request': self.raw_request,
            'task_type': self.task_type,
            'obligations': [item.to_dict() for item in self.obligations],
            'format_constraints': self.format_constraints.to_dict(),
            'subquestions': list(self.subquestions),
            'grouping': list(self.grouping),
            'completeness_constraints': list(self.completeness_constraints),
        }


def tokenize_keywords(text: str) -> list[str]:
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    seen: list[str] = []
    for word in words:
        if len(word) <= 2 or word in STOPWORDS:
            continue
        if word not in seen:
            seen.append(word)
    return seen[:10]


def detect_task_type(request: str) -> str:
    lowered = request.lower()
    for key, task_type in KEYWORD_TASK_TYPES.items():
        if key in lowered:
            return task_type
    if '?' in request:
        return 'qa'
    return 'general_reasoning'


def extract_grouping(request: str) -> list[str]:
    seen: list[str] = []
    for match in GROUPING_PATTERN.finditer(request):
        normalized = match.group(1).strip()
        if normalized not in seen:
            seen.append(normalized)
    return seen


def extract_subquestions(request: str) -> list[str]:
    numbered = [match.group(2).strip() for match in NUMBERED_ITEM_PATTERN.finditer(request)]
    if numbered:
        return numbered

    bullets = [match.group(1).strip() for match in BULLET_ITEM_PATTERN.finditer(request)]
    if bullets:
        return bullets

    pieces = [piece.strip(' .:-') for piece in QUESTION_SPLIT_PATTERN.split(request) if piece.strip()]
    question_like = [piece for piece in pieces if len(piece.split()) >= 3]
    if len(question_like) > 1:
        return question_like

    clauses = re.split(r'\b(?:also|and|plus)\b', request)
    clause_items = [clause.strip(' .:-') for clause in clauses if len(clause.strip().split()) >= 4]
    if len(clause_items) > 1:
        return clause_items

    return []


def _extract_group_text(request: str, grouping: list[str], index: int, group: str) -> str:
    start_match = re.search(rf'{re.escape(group)}\s*[:\-]?', request, re.IGNORECASE)
    if not start_match:
        return group
    start = start_match.end()
    if index + 1 < len(grouping):
        next_group = grouping[index + 1]
        next_match = re.search(rf'{re.escape(next_group)}\s*[:\-]?', request[start:], re.IGNORECASE)
        end = start + next_match.start() if next_match else len(request)
    else:
        end = len(request)
    return request[start:end].strip(' .:-\n')


def build_obligations(request: str, grouping: list[str], subquestions: list[str]) -> list[Obligation]:
    obligations: list[Obligation] = []

    if grouping:
        for index, group in enumerate(grouping):
            text = _extract_group_text(request, grouping, index, group)
            obligation_text = f'{group}: {text}'.strip()
            obligations.append(Obligation(
                id=f'obligation_{index + 1}',
                text=obligation_text,
                kind='grouped_section',
                group=group,
                keywords=tokenize_keywords(obligation_text),
            ))
        return obligations

    if subquestions:
        for index, question in enumerate(subquestions, start=1):
            obligations.append(Obligation(
                id=f'obligation_{index}',
                text=question,
                kind='subquestion',
                keywords=tokenize_keywords(question),
            ))
        return obligations

    return [
        Obligation(
            id='obligation_1',
            text=request.strip(),
            kind='primary_request',
            keywords=tokenize_keywords(request),
        )
    ]


def extract_requirements(request: str) -> RequirementSpec:
    grouping = extract_grouping(request)
    subquestions = [] if grouping else extract_subquestions(request)
    lowered = request.lower()

    format_constraints = FormatConstraints(
        step_by_step=bool(re.search(r'step\s*by\s*step', lowered)),
        detailed=bool(re.search(r'\bin detail\b|\bdetailed\b|\bdeeply\b', lowered)),
        examples_required=bool(re.search(r'\bexample\b|\bexamples\b|\bfor example\b', lowered)),
        compare_required='compare' in lowered or 'comparison' in lowered,
        derivation_required='derive' in lowered or 'derivation' in lowered,
        explain_required='explain' in lowered or 'why' in lowered,
        list_advantages_disadvantages=('advantages' in lowered and 'disadvantages' in lowered),
        strict_structure=bool(grouping) or bool(re.search(r'follow this structure|same structure|under each|section wise|unit wise', lowered)),
        requested_sections=grouping,
    )

    completeness_constraints: list[str] = []
    if re.search(r'\bsolve all\b|\banswer all\b|\bcover all\b|\ball parts\b', lowered):
        completeness_constraints.append('cover_all_parts')
    if subquestions and len(subquestions) > 1:
        completeness_constraints.append('cover_each_subquestion')
    if grouping:
        completeness_constraints.append('preserve_grouping')
    if format_constraints.step_by_step:
        completeness_constraints.append('step_by_step_required')
    if format_constraints.examples_required:
        completeness_constraints.append('examples_required')

    obligations = build_obligations(request, grouping, subquestions)
    return RequirementSpec(
        raw_request=request,
        task_type=detect_task_type(request),
        obligations=obligations,
        format_constraints=format_constraints,
        subquestions=subquestions,
        grouping=grouping,
        completeness_constraints=completeness_constraints,
    )
