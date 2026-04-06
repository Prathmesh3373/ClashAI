import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clash_engine.fulfillment import build_repair_prompt, check_answer_fulfillment
from clash_engine.planner import build_answer_plan
from clash_engine.requirements import extract_requirements
from clash_engine.state import detect_query_mode, finalize_conversation_state, initialize_conversation_state


class FulfillmentLayerTests(unittest.TestCase):
    def test_extracts_multi_part_academic_prompt(self):
        prompt = (
            'Answer all questions in detail. Unit 1: Explain supervised and unsupervised learning with examples. '
            'Unit 2: Compare CNN and RNN step by step. Unit 3: List advantages and disadvantages of transformers.'
        )
        requirements = extract_requirements(prompt)
        self.assertEqual(requirements.task_type, 'comparison')
        self.assertEqual(requirements.grouping, ['Unit 1', 'Unit 2', 'Unit 3'])
        self.assertTrue(requirements.format_constraints.step_by_step)
        self.assertTrue(requirements.format_constraints.examples_required)
        self.assertTrue(requirements.format_constraints.list_advantages_disadvantages)
        self.assertIn('cover_all_parts', requirements.completeness_constraints)
        self.assertEqual(len(requirements.obligations), 3)

    def test_plan_preserves_grouped_sections(self):
        prompt = 'Unit 1: Explain recursion. Unit 2: Derive merge sort. Unit 3: Compare BFS and DFS.'
        requirements = extract_requirements(prompt)
        plan = build_answer_plan(requirements)
        self.assertEqual([section.title for section in plan.sections], ['Unit 1', 'Unit 2', 'Unit 3'])
        self.assertEqual(len(plan.coverage_map), 3)

    def test_step_by_step_requirement_is_detected(self):
        requirements = extract_requirements('Explain dynamic programming step by step with examples.')
        self.assertTrue(requirements.format_constraints.step_by_step)
        self.assertTrue(requirements.format_constraints.examples_required)
        self.assertIn('step_by_step_required', requirements.completeness_constraints)

    def test_checker_detects_missing_sections_and_format_violations(self):
        prompt = (
            'Answer all questions in detail. Unit 1: Explain stacks with examples. '
            'Unit 2: Compare stack and queue step by step. Unit 3: List advantages and disadvantages of recursion.'
        )
        requirements = extract_requirements(prompt)
        plan = build_answer_plan(requirements)
        answer = 'Unit 1\nStacks store items in LIFO order. For example: a browser back stack.\n\nUnit 2\nStack and queue are both linear data structures.'
        report = check_answer_fulfillment(requirements, plan, answer)
        self.assertIn('obligation_3', report.missing)
        self.assertTrue(report.repair_needed)
        self.assertTrue(report.format_violations)
        self.assertLess(report.fulfillment_score, 1.0)

    def test_repair_prompt_targets_missing_parts_only(self):
        prompt = 'Unit 1: Explain trees. Unit 2: Compare BFS and DFS step by step with examples.'
        requirements = extract_requirements(prompt)
        plan = build_answer_plan(requirements)
        answer = 'Unit 1\nTrees are hierarchical data structures.'
        report = check_answer_fulfillment(requirements, plan, answer)
        repair_prompt = build_repair_prompt(requirements, plan, answer, report)
        self.assertIn('Unit 2', repair_prompt)
        self.assertIn('step by step', repair_prompt.lower())
        self.assertIn('example', repair_prompt.lower())
        self.assertIn('repairing an answer, not rewriting it from scratch', repair_prompt.lower())

    def test_state_detects_follow_up_and_tracks_focus(self):
        initial_prompt = 'Unit 1: Explain trees. Unit 2: Compare BFS and DFS step by step.'
        requirements = extract_requirements(initial_prompt)
        plan = build_answer_plan(requirements)
        state = initialize_conversation_state(initial_prompt, [], requirements, plan)
        report = {
            'answered': ['obligation_1'],
            'partially_answered': ['obligation_2'],
            'missing': [],
            'structure_violations': [],
            'format_violations': [],
        }
        final_state = finalize_conversation_state(state, requirements, plan, report, [{'speaker': 'Synthesizer', 'content': 'Unit 1 covered. Unit 2 partly covered.'}])
        memory = [
            {'speaker': 'User', 'content': initial_prompt},
            {'speaker': 'Answer', 'content': '...'},
            {'speaker': 'State', 'state': final_state.to_dict()},
        ]
        follow_up = 'Now explain Unit 2 with more detail and examples.'
        follow_requirements = extract_requirements(follow_up)
        follow_plan = build_answer_plan(follow_requirements)
        self.assertEqual(detect_query_mode(follow_up, memory, follow_requirements), 'refinement')
        next_state = initialize_conversation_state(follow_up, memory, follow_requirements, follow_plan)
        self.assertEqual(next_state.current_focus, 'Unit 2')
        self.assertIn('Unit 1', next_state.completed_sections)


if __name__ == '__main__':
    unittest.main()
