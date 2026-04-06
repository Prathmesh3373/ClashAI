from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, root: str | Path | None = None):
        base = Path(root or Path(__file__).resolve().parents[1] / 'logs')
        self.root = base
        self.root.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir = self.root / 'transcripts'
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_file = self.root / 'experiments.jsonl'
        self.best_config_file = self.root / 'best_config.json'

    def write_transcript(self, payload: dict[str, Any], *, prefix: str = 'conversation') -> str:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        path = self.transcripts_dir / f'{prefix}-{stamp}.json'
        path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        return str(path)

    def append_experiment(self, payload: dict[str, Any]) -> str:
        with self.experiments_file.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(payload) + os.linesep)
        return str(self.experiments_file)

    def load_best_config(self) -> dict[str, Any] | None:
        if not self.best_config_file.exists():
            return None
        return json.loads(self.best_config_file.read_text(encoding='utf-8'))

    def save_best_config(self, payload: dict[str, Any]) -> str:
        self.best_config_file.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        return str(self.best_config_file)
