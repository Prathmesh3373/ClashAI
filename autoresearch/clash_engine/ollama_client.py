from __future__ import annotations

import json
import os
from typing import Any

import requests


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout: int = 180):
        self.base_url = (base_url or os.getenv('OLLAMA_URL') or 'http://localhost:11434').rstrip('/')
        self.timeout = timeout

    def generate(self, model: str, prompt: str, *, system: str = '', temperature: float = 0.2, max_tokens: int = 220) -> str:
        payload: dict[str, Any] = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens,
            },
        }
        if system:
            payload['system'] = system

        response = requests.post(f'{self.base_url}/api/generate', json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return (data.get('response') or '').strip()

    def healthcheck(self) -> bool:
        response = requests.get(f'{self.base_url}/api/tags', timeout=10)
        response.raise_for_status()
        return True
