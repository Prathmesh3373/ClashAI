from __future__ import annotations

import json
from typing import Any

from .config import ConversationConfig, ExperimentResult, build_default_config
from .conversation import MultiAgentConversationEngine
from .ollama_client import OllamaClient
from .storage import Storage


class ExperimentRunner:
    def __init__(self, client: OllamaClient, storage: Storage):
        self.client = client
        self.storage = storage
        self.engine = MultiAgentConversationEngine(client)

    def generate_variants(self, base_config: ConversationConfig) -> list[ConversationConfig]:
        baseline = build_default_config(base_config.name)

        no_planner = build_default_config('no-planner')
        no_planner.planner_enabled = False

        no_checker = build_default_config('no-checker')
        no_checker.fulfillment_checker_enabled = False
        no_checker.repair_enabled = False
        no_checker.fulfillment_weight = 0.55

        strict_structured = build_default_config('strict-structured')
        strict_structured.strict_synthesis = True
        strict_structured.synthesis_style = 'structured'

        no_state = build_default_config('no-state')
        no_state.state_enabled = False
        no_state.fulfillment_weight = 0.65

        return [baseline, no_planner, no_checker, strict_structured, no_state]

    def _evaluate_with_model(self, task: str, conversation_result: dict[str, Any], config: ConversationConfig) -> tuple[float, str, dict[str, float]]:
        requirements = json.dumps(conversation_result.get('requirements', {}), indent=2)
        report = json.dumps(conversation_result.get('fulfillment_report', {}), indent=2)
        state = json.dumps(conversation_result.get('conversation_state', {}), indent=2)
        prompt = f"""
Evaluate this answer with fulfillment weighted above polish.
Return strict JSON with numeric keys:
- completeness
- format_adherence
- subquestion_coverage
- step_by_step_compliance
- clarity
- usefulness
- overall_score
- explanation

Task:
{task}

Extracted requirements:
{requirements}

Conversation state:
{state}

Fulfillment report:
{report}

Final answer:
{conversation_result['final_answer']}
""".strip()
        raw = self.client.generate(
            config.evaluator_model,
            prompt,
            system='You are an evaluator. Return only valid JSON.',
            temperature=0.1,
            max_tokens=240,
        )
        data = json.loads(raw)
        dimensions = {
            'completeness': float(data['completeness']),
            'format_adherence': float(data['format_adherence']),
            'subquestion_coverage': float(data['subquestion_coverage']),
            'step_by_step_compliance': float(data['step_by_step_compliance']),
            'clarity': float(data['clarity']),
            'usefulness': float(data['usefulness']),
        }
        return float(data['overall_score']), str(data['explanation']).strip(), dimensions

    def evaluate_result(self, task: str, conversation_result: dict[str, Any], config: ConversationConfig) -> tuple[float, float, str, dict[str, float]]:
        report = conversation_result.get('fulfillment_report') or {}
        fulfillment_score = float(report.get('fulfillment_score', 0.0)) * 10.0
        fallback_dimensions = {
            'completeness': fulfillment_score,
            'format_adherence': max(0.0, 10.0 - 2.5 * len(report.get('format_violations', []))),
            'subquestion_coverage': max(0.0, 10.0 - 3.0 * len(report.get('missing', []))),
            'step_by_step_compliance': 10.0 if not report.get('format_violations') else 6.0,
            'clarity': max(4.0, min(9.0, len(conversation_result['final_answer']) / 180.0)),
            'usefulness': max(4.0, min(9.0, fulfillment_score)),
        }

        try:
            model_score, explanation, dimensions = self._evaluate_with_model(task, conversation_result, config)
        except Exception:
            dimensions = fallback_dimensions
            weighted = (
                0.3 * dimensions['completeness']
                + 0.2 * dimensions['format_adherence']
                + 0.2 * dimensions['subquestion_coverage']
                + 0.1 * dimensions['step_by_step_compliance']
                + 0.1 * dimensions['clarity']
                + 0.1 * dimensions['usefulness']
            )
            model_score = round(weighted, 2)
            explanation = 'Evaluator returned invalid JSON, so a fulfillment-aware fallback score was used.'

        final_score = round(config.fulfillment_weight * fulfillment_score + (1 - config.fulfillment_weight) * model_score, 2)
        return final_score, round(fulfillment_score, 2), explanation, dimensions

    def run_single_experiment(self, task: str, config: ConversationConfig, *, memory: list[dict[str, str]] | None = None) -> ExperimentResult:
        conversation_result = self.engine.run_conversation(task, config, memory=memory)
        transcript_path = self.storage.write_transcript(conversation_result, prefix=config.name)
        score, fulfillment_score, explanation, dimensions = self.evaluate_result(task, conversation_result, config)
        payload = {
            'task': task,
            'config': config.to_dict(),
            'score': score,
            'fulfillment_score': fulfillment_score,
            'dimensions': dimensions,
            'explanation': explanation,
            'transcript_path': transcript_path,
            'final_answer': conversation_result['final_answer'],
            'requirements': conversation_result.get('requirements'),
            'plan': conversation_result.get('plan'),
            'conversation_state': conversation_result.get('conversation_state'),
            'fulfillment_report': conversation_result.get('fulfillment_report'),
            'repair_applied': conversation_result.get('repair_applied'),
        }
        log_path = self.storage.append_experiment(payload)
        result = ExperimentResult(
            config_name=config.name,
            task=task,
            score=score,
            explanation=explanation,
            transcript_path=transcript_path,
            log_path=log_path,
            decision=conversation_result['final_answer'],
            fulfillment_score=fulfillment_score,
        )
        self._maybe_update_best(config, result, payload)
        return result

    def run_experiment_cycle(self, task: str, base_config: ConversationConfig | None = None) -> dict[str, Any]:
        base_config = base_config or build_default_config()
        variants = self.generate_variants(base_config)
        results = [self.run_single_experiment(task, variant) for variant in variants]
        best = max(results, key=lambda result: (result.score, result.fulfillment_score))
        return {
            'task': task,
            'results': [result.to_dict() for result in results],
            'best': best.to_dict(),
        }

    def _maybe_update_best(self, config: ConversationConfig, result: ExperimentResult, payload: dict[str, Any]) -> None:
        current_best = self.storage.load_best_config()
        if current_best:
            current_score = float(current_best.get('score', 0.0))
            current_fulfillment = float(current_best.get('fulfillment_score', 0.0))
            if (current_score, current_fulfillment) >= (result.score, result.fulfillment_score):
                return
        best_payload = dict(payload)
        best_payload['config_name'] = config.name
        self.storage.save_best_config(best_payload)
