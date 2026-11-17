"""YAML/JSON loading and JSON Schema export for authoring models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def load_yaml(model: type[T], path: str | Path) -> T:
    return model.model_validate(yaml.safe_load(Path(path).read_text()))


def load_yaml_list(model: type[T], path: str | Path) -> list[T]:
    data = yaml.safe_load(Path(path).read_text()) or []
    return [model.model_validate(d) for d in data]


def dump_yaml(obj: BaseModel) -> str:
    data = obj.model_dump(mode="json", by_alias=True, exclude_defaults=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def json_schema(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema(by_alias=True)
