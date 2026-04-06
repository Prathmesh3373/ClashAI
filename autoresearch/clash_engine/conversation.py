from __future__ import annotations

from typing import Any

from .config import AgentSpec, ConversationConfig
from .fulfillment import build_repair_prompt, check_answer_fulfillment
from .ollama_client import OllamaClient
from .planner import AnswerPlan, build_answer_plan
from .requirements import RequirementSpec, extract_requirements
from .state import ConversationState, finalize_conversation_state, initialize_conversation_state


def _format_requirements(requirements: RequirementSpec) -> str:
    obligations = '\n'.join(f'- {item.id}: {item.text}' for item in requirements.obligations)
    formats = requirements.format_constraints.to_dict()
    active_formats = [name for name, enabled in formats.items() if enabled and name != 'requested_sections']
    sections = ', '.join(requirements.grouping) if requirements.grouping else 'None'
    completeness = ', '.join(requirements.completeness_constraints) if requirements.completeness_constraints else 'None'
    return '\n'.join([
        f'Task type: {requirements.task_type}',
        f'Required sections: {sections}',
        f'Active format constraints: {", ".join(active_formats) if active_formats else "None"}',
        f'Completeness constraints: {completeness}',
        'Obligations:',
        obligations or '- None',
    ])


def _format_plan(plan: AnswerPlan) -> str:
    lines: list[str] = []
    for section in plan.sections:
        lines.append(f'- {section.title}: covers {", ".join(section.obligation_ids)} | {section.guidance}')
    if plan.planning_notes:
        lines.append('Planning notes:')
        lines.extend(f'  - {note}' for note in plan.planning_notes)
    return '\n'.join(lines) if lines else 'No explicit plan.'


def _format_state(state: ConversationState | None) -> str:
    if state is None:
        return 'No structured conversation state.'
    return '\n'.join([
        f'Topic: {state.topic}',
        f'User goal: {state.user_goal}',
        f'Current focus: {state.current_focus}',
        f'Completed sections: {", ".join(state.completed_sections) if state.completed_sections else "None"}',
        f'Pending sections: {", ".join(state.pending_sections) if state.pending_sections else "None"}',
        f'Conversation intent: {state.conversation_intent}',
        f'Query mode: {state.query_mode}',
        f'Transcript summary: {state.transcript_summary}',
    ])


def _format_transcript_summary(transcript: list[dict[str, str]], limit: int = 4) -> str:
    if not transcript:
        return 'No current-round transcript yet.'
    lines = []
    for entry in transcript[-limit:]:
        lines.append(f"{entry['speaker']}: {entry['content'].strip().replace(chr(10), ' ')[:220]}")
    return '\n'.join(lines)


class MultiAgentConversationEngine:
    def __init__(self, client: OllamaClient):
        self.client = client

    def _agent_system_prompt(self, agent: AgentSpec, requirements: RequirementSpec, config: ConversationConfig) -> str:
        strict_note = 'You must not skip any listed obligation.' if config.fulfillment_checker_enabled else 'Aim to cover the task fully.'
        return (
            'You are part of a collaborative multi-agent reasoning system. '
            'You are not debating to win. You are helping the group reach a better decision for the user. '
            f'Your role: {agent.role} '
            f'Your objective: {agent.objective} '
            f'{strict_note} '
            'Use the conversation state to avoid repetition. '
            'Continue from what is already covered and focus on what remains. '
            'When the user requests structure, preserve it. '
            'When the user requests step-by-step reasoning or examples, explicitly provide them. '
            'Reference prior agent contributions when useful and improve them where possible.'
        )

    def _build_agent_prompt(
        self,
        *,
        user_task: str,
        agent: AgentSpec,
        transcript: list[dict[str, str]],
        round_index: int,
        config: ConversationConfig,
        requirements: RequirementSpec,
        plan: AnswerPlan,
        state: ConversationState | None,
    ) -> str:
        return f"""
User task:
{user_task}

Conversation round: {round_index + 1}
Current agent: {agent.name}

Conversation state:
{_format_state(state)}

Structured requirements:
{_format_requirements(requirements)}

Answer plan:
{_format_plan(plan)}

Current transcript summary:
{_format_transcript_summary(transcript)}

Write the next helpful contribution for the group.
Improve the shared reasoning.
Do not repeat completed content unless the current query mode suggests refinement or correction.
Focus on pending sections and the current focus.
Point out anything that could still be skipped or mishandled in the final answer.
""".strip()

    def _build_synthesis_prompt(
        self,
        *,
        user_task: str,
        transcript: list[dict[str, str]],
        config: ConversationConfig,
        requirements: RequirementSpec,
        plan: AnswerPlan,
        state: ConversationState | None,
    ) -> str:
        structure_rule = 'Use the exact requested section headings and preserve the plan order.' if config.strict_synthesis or requirements.format_constraints.strict_structure else 'Use a clean structure that still covers every planned section.'
        return f"""
You are producing the final answer for the user after a collaborative multi-agent reasoning session.
Synthesis style: {config.synthesis_style}

User task:
{user_task}

Conversation state:
{_format_state(state)}

Structured requirements:
{_format_requirements(requirements)}

Answer plan:
{_format_plan(plan)}

Current transcript summary:
{_format_transcript_summary(transcript, limit=6)}

Write the final answer for the user.
Requirements:
- satisfy every listed obligation
- follow the requested structure and formatting exactly when present
- {structure_rule}
- continue the conversation appropriately if the query mode is follow_up, refinement, or correction
- if step by step was requested, use numbered steps
- if examples were requested, include explicit examples
- do not omit any major subquestion
- do not repeat already completed sections unless refinement or correction requires it
- do not mention internal agent roles unless necessary
""".strip()

    def run_conversation(
        self,
        user_task: str,
        config: ConversationConfig,
        *,
        memory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        memory = list(memory or [])
        transcript: list[dict[str, str]] = []
        requirements = extract_requirements(user_task)
        plan = build_answer_plan(requirements) if config.planner_enabled else AnswerPlan()
        state = initialize_conversation_state(user_task, memory, requirements, plan) if config.state_enabled else None

        for round_index in range(config.rounds):
            for agent in config.agents:
                prompt = self._build_agent_prompt(
                    user_task=user_task,
                    agent=agent,
                    transcript=transcript,
                    round_index=round_index,
                    config=config,
                    requirements=requirements,
                    plan=plan,
                    state=state,
                )
                content = self.client.generate(
                    agent.model,
                    prompt,
                    system=self._agent_system_prompt(agent, requirements, config),
                    temperature=config.temperature,
                    max_tokens=agent.max_tokens,
                )
                transcript.append(
                    {
                        'speaker': agent.name,
                        'role': agent.role,
                        'content': content,
                        'model': agent.model,
                        'round': round_index + 1,
                    }
                )

        synthesizer = config.synthesizer
        if synthesizer is None:
            raise ValueError('Conversation config is missing a synthesizer.')

        draft_answer = self.client.generate(
            synthesizer.model,
            self._build_synthesis_prompt(
                user_task=user_task,
                transcript=transcript,
                config=config,
                requirements=requirements,
                plan=plan,
                state=state,
            ),
            system=(
                'You synthesize collaborative agent reasoning into one clear recommendation for the user. '
                'Fulfillment matters more than polish. Cover every requested part.'
            ),
            temperature=config.temperature,
            max_tokens=synthesizer.max_tokens,
        )

        fulfillment_report = check_answer_fulfillment(requirements, plan, draft_answer) if config.fulfillment_checker_enabled else None
        repair_applied = False
        final_answer = draft_answer

        if fulfillment_report and fulfillment_report.repair_needed and config.repair_enabled:
            repair_applied = True
            repair_prompt = build_repair_prompt(requirements, plan, draft_answer, fulfillment_report)
            final_answer = self.client.generate(
                synthesizer.model,
                repair_prompt,
                system=(
                    'You are repairing an answer to satisfy explicit user requirements. '
                    'Fix only the missing or weak parts while preserving good content.'
                ),
                temperature=0.1,
                max_tokens=synthesizer.max_tokens + 120,
            )
            fulfillment_report = check_answer_fulfillment(requirements, plan, final_answer)
        else:
            repair_prompt = None

        final_state = finalize_conversation_state(state, requirements, plan, fulfillment_report.to_dict() if fulfillment_report else None, transcript) if state else None

        updated_memory = memory + [
            {'speaker': 'User', 'content': user_task},
            {'speaker': 'Answer', 'content': final_answer},
        ]
        if final_state is not None:
            updated_memory.append({'speaker': 'State', 'state': final_state.to_dict()})

        return {
            'task': user_task,
            'config': config.to_dict(),
            'requirements': requirements.to_dict(),
            'plan': plan.to_dict(),
            'conversation_state': final_state.to_dict() if final_state else None,
            'transcript': transcript,
            'draft_answer': draft_answer,
            'final_answer': final_answer,
            'fulfillment_report': fulfillment_report.to_dict() if fulfillment_report else None,
            'repair_applied': repair_applied,
            'repair_prompt': repair_prompt,
            'memory': updated_memory,
        }
