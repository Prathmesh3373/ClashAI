from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .requirements import RequirementSpec


@dataclass(slots=True)
class PlannedSection:
    title: str
    obligation_ids: list[str] = field(default_factory=list)
    guidance: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnswerPlan:
    sections: list[PlannedSection] = field(default_factory=list)
    coverage_map: dict[str, str] = field(default_factory=dict)
    planning_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'sections': [section.to_dict() for section in self.sections],
            'coverage_map': dict(self.coverage_map),
            'planning_notes': list(self.planning_notes),
        }


def build_answer_plan(requirements: RequirementSpec) -> AnswerPlan:
    plan = AnswerPlan()

    if requirements.grouping:
        for obligation in requirements.obligations:
            title = obligation.group or obligation.text[:60]
            guidance = 'Answer this grouped section completely.'
            if requirements.format_constraints.step_by_step:
                guidance += ' Use ordered steps inside this section.'
            section = PlannedSection(title=title, obligation_ids=[obligation.id], guidance=guidance)
            plan.sections.append(section)
            plan.coverage_map[obligation.id] = title
    elif len(requirements.obligations) == 1:
        title = 'Complete Answer'
        guidance = 'Cover the full request directly.'
        if requirements.format_constraints.step_by_step:
            guidance += ' Present it step by step.'
        section = PlannedSection(title=title, obligation_ids=[requirements.obligations[0].id], guidance=guidance)
        plan.sections.append(section)
        plan.coverage_map[requirements.obligations[0].id] = title
    else:
        for index, obligation in enumerate(requirements.obligations, start=1):
            title = f'Part {index}'
            guidance = 'Address this subquestion clearly and completely.'
            if requirements.format_constraints.examples_required:
                guidance += ' Include an example if useful.'
            section = PlannedSection(title=title, obligation_ids=[obligation.id], guidance=guidance)
            plan.sections.append(section)
            plan.coverage_map[obligation.id] = title

    if requirements.format_constraints.list_advantages_disadvantages:
        plan.planning_notes.append('Ensure both advantages and disadvantages are explicitly covered.')
    if requirements.format_constraints.compare_required:
        plan.planning_notes.append('Include direct comparison points, not isolated descriptions.')
    if requirements.format_constraints.derivation_required:
        plan.planning_notes.append('Show the derivation flow rather than only the final result.')
    if requirements.format_constraints.examples_required:
        plan.planning_notes.append('Add examples where they improve understanding.')

    return plan
