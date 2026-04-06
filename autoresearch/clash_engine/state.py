from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .planner import AnswerPlan
from .requirements import RequirementSpec

FOLLOW_UP_PATTERN = re.compile(r'^(what about|how about|and\b|also\b|then\b|now\b|so\b|in that case|for unit|for section|for part)', re.IGNORECASE)
CORRECTION_PATTERN = re.compile(r"^(actually|no\b|that's wrong|you missed|fix this|correction|revise)", re.IGNORECASE)
REFINEMENT_PATTERN = re.compile(r'\b(more detail|in depth|elaborate|step by step|with examples|expand|be specific|go deeper)\b', re.IGNORECASE)
REFERENCE_PATTERN = re.compile(r'\b(this|that|it|they|them|those|these|above|earlier|previous|same|unit\s+\d+|section\s+\d+|part\s+[a-z0-9]+)\b', re.IGNORECASE)


@dataclass(slots=True)
class ConversationState:
    topic: str
    user_goal: str
    current_focus: str
    completed_sections: list[str] = field(default_factory=list)
    pending_sections: list[str] = field(default_factory=list)
    conversation_intent: str = 'general_reasoning'
    query_mode: str = 'new_task'
    transcript_summary: str = 'No prior summary.'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _topic_from_request(request: str) -> str:
    words = request.strip().split()
    return ' '.join(words[:12]).strip() or 'General task'


def _intent_from_requirements(requirements: RequirementSpec) -> str:
    mapping = {
        'comparison': 'learning',
        'derivation': 'learning',
        'explanation': 'learning',
        'problem_solving': 'problem_solving',
        'planning': 'decision',
        'decision': 'decision',
        'qa': 'explanation',
    }
    return mapping.get(requirements.task_type, requirements.task_type)


def detect_query_mode(user_input: str, memory: list[dict[str, Any]], requirements: RequirementSpec) -> str:
    text = user_input.strip()
    if not memory:
        return 'new_task'
    if CORRECTION_PATTERN.search(text):
        return 'correction'
    if REFINEMENT_PATTERN.search(text):
        return 'refinement'
    if FOLLOW_UP_PATTERN.search(text) or (len(text.split()) <= 18 and REFERENCE_PATTERN.search(text)):
        return 'follow_up'
    if requirements.grouping and any(group.lower() in text.lower() for group in requirements.grouping):
        return 'follow_up'
    return 'new_task'


def summarize_memory(memory: list[dict[str, Any]], limit: int = 4) -> str:
    if not memory:
        return 'No prior summary.'
    summary_lines: list[str] = []
    for item in memory[-limit:]:
        if item.get('state'):
            state = item['state']
            summary_lines.append(
                f"State: focus={state.get('current_focus', 'unknown')}; completed={', '.join(state.get('completed_sections', [])) or 'none'}; pending={', '.join(state.get('pending_sections', [])) or 'none'}"
            )
            continue
        speaker = item.get('speaker', 'Unknown')
        content = (item.get('content') or '').strip().replace('\n', ' ')
        summary_lines.append(f"{speaker}: {content[:180]}")
    return '\n'.join(summary_lines)


def latest_state_from_memory(memory: list[dict[str, Any]]) -> ConversationState | None:
    for item in reversed(memory):
        if item.get('state'):
            data = item['state']
            return ConversationState(
                topic=data.get('topic', 'General task'),
                user_goal=data.get('user_goal', ''),
                current_focus=data.get('current_focus', 'General task'),
                completed_sections=list(data.get('completed_sections', [])),
                pending_sections=list(data.get('pending_sections', [])),
                conversation_intent=data.get('conversation_intent', 'general_reasoning'),
                query_mode=data.get('query_mode', 'new_task'),
                transcript_summary=data.get('transcript_summary', 'No prior summary.'),
            )
    return None


def _focus_from_request(user_input: str, requirements: RequirementSpec, plan: AnswerPlan, previous: ConversationState | None) -> str:
    lowered = user_input.lower()
    for section in plan.sections:
        if section.title.lower() in lowered:
            return section.title
    for group in requirements.grouping:
        if group.lower() in lowered:
            return group
    if previous and previous.current_focus and REFERENCE_PATTERN.search(user_input):
        return previous.current_focus
    if plan.sections:
        return plan.sections[0].title
    return _topic_from_request(user_input)


def initialize_conversation_state(user_input: str, memory: list[dict[str, Any]], requirements: RequirementSpec, plan: AnswerPlan) -> ConversationState:
    previous = latest_state_from_memory(memory)
    query_mode = detect_query_mode(user_input, memory, requirements)
    sections = [section.title for section in plan.sections]

    if query_mode == 'new_task' or previous is None:
        completed = []
        pending = sections[:]
        topic = _topic_from_request(user_input)
        user_goal = requirements.raw_request
    else:
        completed = list(previous.completed_sections)
        pending = list(previous.pending_sections) if previous.pending_sections else sections[:]
        topic = previous.topic
        user_goal = previous.user_goal or requirements.raw_request

    current_focus = _focus_from_request(user_input, requirements, plan, previous)
    if current_focus:
        if current_focus in pending:
            pending = [current_focus] + [section for section in pending if section != current_focus]
        elif sections:
            pending = [current_focus] + [section for section in pending if section != current_focus]
        elif not pending:
            pending = [current_focus]

    return ConversationState(
        topic=topic,
        user_goal=user_goal,
        current_focus=current_focus,
        completed_sections=completed,
        pending_sections=pending,
        conversation_intent=_intent_from_requirements(requirements),
        query_mode=query_mode,
        transcript_summary=summarize_memory(memory),
    )


def finalize_conversation_state(state: ConversationState, requirements: RequirementSpec, plan: AnswerPlan, fulfillment_report: dict[str, Any] | None, transcript: list[dict[str, Any]]) -> ConversationState:
    coverage_map = dict(plan.coverage_map)
    answered_ids = set((fulfillment_report or {}).get('answered', []))
    partial_ids = set((fulfillment_report or {}).get('partially_answered', []))
    missing_ids = set((fulfillment_report or {}).get('missing', []))

    completed = list(state.completed_sections)
    pending: list[str] = []

    for obligation in requirements.obligations:
        section_name = coverage_map.get(obligation.id, obligation.group or obligation.text)
        if obligation.id in answered_ids:
            if section_name not in completed:
                completed.append(section_name)
        elif obligation.id in partial_ids or obligation.id in missing_ids:
            if section_name not in pending:
                pending.append(section_name)

    if not pending:
        pending = [section for section in state.pending_sections if section not in completed]

    transcript_lines = [
        f"{entry['speaker']}: {(entry.get('content') or '').strip().replace('\n', ' ')[:160]}"
        for entry in transcript[-4:]
    ]

    return ConversationState(
        topic=state.topic,
        user_goal=state.user_goal,
        current_focus=pending[0] if pending else (completed[-1] if completed else state.current_focus),
        completed_sections=completed,
        pending_sections=pending,
        conversation_intent=state.conversation_intent,
        query_mode=state.query_mode,
        transcript_summary='\n'.join(transcript_lines) if transcript_lines else state.transcript_summary,
    )
