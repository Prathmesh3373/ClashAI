from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentSpec:
    name: str
    role: str
    objective: str
    model: str = 'llama3.2'
    max_tokens: int = 220


@dataclass(slots=True)
class ConversationConfig:
    name: str = 'baseline-collab'
    rounds: int = 2
    include_memory: bool = True
    synthesis_style: str = 'balanced'
    evaluation_style: str = 'practical'
    temperature: float = 0.2
    memory_window: int = 8
    planner_enabled: bool = True
    fulfillment_checker_enabled: bool = True
    repair_enabled: bool = True
    strict_synthesis: bool = False
    fulfillment_weight: float = 0.7
    state_enabled: bool = True
    agents: list[AgentSpec] = field(default_factory=list)
    synthesizer: AgentSpec | None = None
    evaluator_model: str = 'mistral'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExperimentResult:
    config_name: str
    task: str
    score: float
    explanation: str
    transcript_path: str
    log_path: str
    decision: str
    fulfillment_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_AGENTS = [
    AgentSpec(
        name='Analyst',
        role='Clarifies the problem, assumptions, and tradeoffs.',
        objective='Break the task into the core decision factors and frame the problem cleanly.',
        model='llama3.2',
    ),
    AgentSpec(
        name='Strategist',
        role='Finds the most leverageable path forward.',
        objective='Propose the best strategic options and explain why they matter.',
        model='mistral',
    ),
    AgentSpec(
        name='Skeptic',
        role='Pressure-tests the reasoning and spots blind spots.',
        objective='Challenge weak assumptions, risks, and edge cases without being adversarial.',
        model='llama3.2',
    ),
    AgentSpec(
        name='Executor',
        role='Turns the reasoning into an actionable plan.',
        objective='Translate the discussion into concrete next steps, constraints, and execution details.',
        model='mistral',
    ),
]

DEFAULT_SYNTHESIZER = AgentSpec(
    name='Synthesizer',
    role='Combines the multi-agent discussion into one user-facing recommendation.',
    objective='Write a clear, direct, useful recommendation for the user that reflects the agent conversation.',
    model='mistral',
    max_tokens=320,
)


def build_default_config(name: str = 'baseline-collab') -> ConversationConfig:
    strict = 'structured' in name or 'exam' in name
    return ConversationConfig(
        name=name,
        rounds=2,
        include_memory=True,
        synthesis_style='structured' if strict else 'balanced',
        evaluation_style='fulfillment_first',
        temperature=0.2,
        memory_window=8,
        planner_enabled=True,
        fulfillment_checker_enabled=True,
        repair_enabled=True,
        strict_synthesis=strict,
        fulfillment_weight=0.7,
        state_enabled=True,
        agents=[AgentSpec(**asdict(agent)) for agent in DEFAULT_AGENTS],
        synthesizer=AgentSpec(**asdict(DEFAULT_SYNTHESIZER)),
        evaluator_model='mistral',
    )
