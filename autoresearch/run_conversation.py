from __future__ import annotations

import argparse
import json

from clash_engine.config import build_default_config
from clash_engine.conversation import MultiAgentConversationEngine
from clash_engine.ollama_client import OllamaClient


def main() -> None:
    parser = argparse.ArgumentParser(description='Run one collaborative multi-agent conversation.')
    parser.add_argument('--task', required=True, help='The user task or decision problem to solve.')
    args = parser.parse_args()

    client = OllamaClient()
    engine = MultiAgentConversationEngine(client)
    result = engine.run_conversation(args.task, build_default_config())
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
