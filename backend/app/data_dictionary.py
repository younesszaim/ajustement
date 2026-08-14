"""Validated semantic field catalog shared by all backend boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_DICTIONARY = Path(__file__).parents[1] / "config" / "data_dictionary.yaml"


@dataclass(frozen=True)
class FieldDefinition:
    semantic_id: str
    api: str
    label: str
    type: str
    db: str | None = None
    parquet: str | None = None
    editable: bool = False
    additive: bool = False
    producer: str | None = None
    starts: tuple[str, ...] = ()


class DataDictionary:
    def __init__(self, path: Path = DEFAULT_DICTIONARY):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("fields"), dict):
            raise ValueError(f"Invalid data dictionary: {path}")
        self.version = raw.get("version")
        self.fields = {
            semantic_id: FieldDefinition(
                semantic_id=semantic_id,
                starts=tuple(values.get("starts", ())),
                **{key: value for key, value in values.items() if key != "starts"},
            )
            for semantic_id, values in raw["fields"].items()
        }
        self._validate()
        self.by_api = {field.api: field for field in self.fields.values()}

    def _validate(self):
        if self.version != 1:
            raise ValueError(f"Unsupported data dictionary version: {self.version}")
        for namespace in ("api", "db"):
            names = [getattr(field, namespace) for field in self.fields.values() if getattr(field, namespace)]
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                raise ValueError(f"Duplicate {namespace} field names: {duplicates}")
        for field in self.fields.values():
            if not field.api or not field.label or not field.type:
                raise ValueError(f"Incomplete field definition: {field.semantic_id}")

    def field(self, semantic_id: str) -> FieldDefinition:
        try:
            return self.fields[semantic_id]
        except KeyError as exc:
            raise KeyError(f'Unknown semantic field "{semantic_id}"') from exc

    def api(self, semantic_id: str) -> str:
        return self.field(semantic_id).api

    def parquet(self, semantic_id: str) -> str:
        value = self.field(semantic_id).parquet
        if not value:
            raise KeyError(f'Field "{semantic_id}" has no Parquet name')
        return value

    def label_for_api(self, api_name: str) -> str:
        field = self.by_api.get(api_name)
        return field.label if field else api_name.replace("_", " ").title()

    def api_names(self, attribute: str) -> set[str]:
        return {field.api for field in self.fields.values() if getattr(field, attribute)}

    def as_frontend_payload(self) -> dict[str, Any]:
        return {
            field.api: {
                "semanticId": field.semantic_id,
                "label": field.label,
                "type": field.type,
                "editable": field.editable,
                "additive": field.additive,
            }
            for field in self.fields.values()
        }


FIELDS = DataDictionary()
DB_TO_API = {
    field.db: field.api for field in FIELDS.fields.values() if field.db
}
