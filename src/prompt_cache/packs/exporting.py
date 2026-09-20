"""Writing a template pack.

Plain Markdown plus a small manifest, so a pack is readable, diffable and git-friendly
without prompt-cache being installed to make sense of it.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from prompt_cache.core.models import Prompt
from prompt_cache.store import prompts as prompt_store

PACK_VERSION = 1
MANIFEST_NAME = "pack.json"
PROMPTS_DIR = "prompts"


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    prompt_count: int
    names: tuple[str, ...]


def _entry(prompt: Prompt) -> dict:
    return {
        "name": prompt.name,
        "title": prompt.title,
        "title_is_custom": prompt.title_is_custom,
        "pinned": prompt.pinned,
        "tags": list(prompt.tags),
        "file": f"{PROMPTS_DIR}/{prompt.name}.md",
    }


def export_pack(
    conn: sqlite3.Connection,
    destination: Path | str,
    *,
    name: str = "prompt-cache pack",
    prompt_ids: list[str] | None = None,
) -> ExportResult:
    """Write the chosen prompts (or all live ones) to `destination` as a pack.

    Usage counts and timestamps are deliberately left out: they describe how *this*
    machine has used a prompt, not what the prompt is.
    """
    destination = Path(destination)
    (destination / PROMPTS_DIR).mkdir(parents=True, exist_ok=True)

    prompts = prompt_store.list_live(conn)
    if prompt_ids is not None:
        wanted = set(prompt_ids)
        prompts = [p for p in prompts if p.id in wanted]
    prompts.sort(key=lambda p: p.name)

    for prompt in prompts:
        (destination / PROMPTS_DIR / f"{prompt.name}.md").write_text(prompt.body, encoding="utf-8")

    manifest = {
        "pack_version": PACK_VERSION,
        "name": name,
        "exported_at": datetime.now(UTC).isoformat(),
        "prompts": [_entry(p) for p in prompts],
    }
    (destination / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return ExportResult(
        path=destination,
        prompt_count=len(prompts),
        names=tuple(p.name for p in prompts),
    )
