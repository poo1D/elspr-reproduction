"""Typed JSONL input and output helpers."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def read_jsonl(path: Path, model_type: type[ModelT]) -> list[ModelT]:
    """Read a JSONL file and validate every non-empty line."""

    records: list[ModelT] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model_type.model_validate_json(line))
            except ValueError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return records


def write_jsonl(path: Path, records: Iterable[BaseModel]) -> None:
    """Write validated models as stable UTF-8 JSONL."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = record.model_dump(mode="json")
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
