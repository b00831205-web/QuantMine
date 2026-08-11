"""Normalize saved AI configuration and repair its default model.

This migration combines the historical model-alias cleanup with the default
model backfill. It is idempotent and only updates rows whose persisted value
changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import MetaData, Table, select, update

from quantmine.storage.database import get_engine


MODEL_ALIASES = {
    "deepseek-v4flash": "deepseek-v4-flash",
    "deepseek-v4pro": "deepseek-v4-pro",
}


def _normalize_models(models: object) -> list[str]:
    normalized: list[str] = []
    for model in models if isinstance(models, list) else []:
        if not isinstance(model, str) or not model:
            continue
        canonical = MODEL_ALIASES.get(model, model)
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def normalize_config(
    providers: object, default_model: object
) -> tuple[list[dict[str, Any]], str]:
    """Return canonical providers and a valid default model."""

    normalized_providers: list[dict[str, Any]] = []
    available_models: list[str] = []
    for provider in providers if isinstance(providers, list) else []:
        if not isinstance(provider, Mapping):
            continue
        normalized_models = _normalize_models(provider.get("models"))
        normalized_providers.append({**provider, "models": normalized_models})
        available_models.extend(
            model for model in normalized_models if model not in available_models
        )

    current = default_model if isinstance(default_model, str) else ""
    normalized_default = MODEL_ALIASES.get(current, current)
    if available_models and normalized_default not in available_models:
        normalized_default = available_models[0]

    return normalized_providers, normalized_default


def migrate() -> int:
    engine = get_engine()
    table = Table("ai_config", MetaData(), autoload_with=engine)
    changed = 0

    with engine.begin() as connection:
        rows = connection.execute(select(table)).mappings().all()
        for row in rows:
            providers = row.get("providers") or []
            default_model = row.get("default_model") or ""
            normalized_providers, normalized_default = normalize_config(
                providers, default_model
            )
            if (
                normalized_providers == providers
                and normalized_default == default_model
            ):
                continue
            connection.execute(
                update(table)
                .where(table.c.id == row["id"])
                .values(
                    providers=normalized_providers,
                    default_model=normalized_default,
                )
            )
            changed += 1

    return changed


if __name__ == "__main__":
    print(f"Updated AI config rows: {migrate()}")
