# Clash AI Decision Engine on top of autoresearch

This repo now contains two distinct layers:

- `prepare.py` and `train.py`: the original ML-training autoresearch baseline. These remain training-specific.
- `clash_engine/`: a reusable conversational reasoning layer for collaborative multi-agent decision making.

## Separation of concerns

ML-specific / legacy:
- `prepare.py`
- `train.py`
- `analysis.ipynb`
- the current `program.md` workflow

Reusable / new system:
- `clash_engine/config.py`: agent and experiment configuration
- `clash_engine/ollama_client.py`: minimal LLM client
- `clash_engine/conversation.py`: collaborative multi-agent conversation loop
- `clash_engine/experiments.py`: config variation, scoring, best-config retention
- `clash_engine/storage.py`: persistence for transcripts, experiment logs, and best config
- `run_conversation.py`: run one conversation MVP
- `run_experiment.py`: run one config experiment cycle MVP

## MVP flow

1. User gives a task.
2. Analyst, Strategist, Skeptic, and Executor contribute in sequence.
3. The Synthesizer turns the conversation into one final recommendation.
4. The ExperimentRunner tries a few configuration variants.
5. An evaluator scores each result.
6. Experiments are logged and the best config is retained.

## Usage

Run one conversation:

```bash
uv run python run_conversation.py --task "Should I leave my job to start a SaaS company?"
```

Run one experiment cycle:

```bash
uv run python run_experiment.py --task "Should I leave my job to start a SaaS company?"
```

## Persistence

Logs are saved under `logs/`:
- `logs/transcripts/*.json`
- `logs/experiments.jsonl`
- `logs/best_config.json`
