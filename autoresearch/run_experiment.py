from __future__ import annotations

import argparse
import json

from clash_engine.config import build_default_config
from clash_engine.experiments import ExperimentRunner
from clash_engine.ollama_client import OllamaClient
from clash_engine.storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description='Run one configuration experiment cycle for collaborative reasoning.')
    parser.add_argument('--task', required=True, help='The user task or decision problem to solve.')
    args = parser.parse_args()

    client = OllamaClient()
    storage = Storage()
    runner = ExperimentRunner(client, storage)
    result = runner.run_experiment_cycle(args.task, build_default_config())
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
