# ruff: noqa: TRY004
"""Immutable artifacts produced by one persisted IC workflow."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import pandas as pd

from ..ic_calculator import ICVariant

_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


@dataclass(frozen=True)
class ICResearchPublication:
    """Locations and summary of one immutable IC artifact set"""

    run_id: int
    output_dir: Path
    manifest_path: Path
    variant_count: int
    test_count: int
    variant_names: tuple[str, ...]
    test_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, int) or isinstance(self.run_id, bool) or self.run_id < 1:
            raise ValueError("run_id must be a positive integer")

        if self.variant_count != len(self.variant_names):
            raise ValueError("variant_count must match variant_names")

        if self.test_count != len(self.test_ids):
            raise ValueError("test_count must match test_ids")

@dataclass(frozen=True)
class ICResearchArtifacts:
    """Verified IC vartiants and test results loaded from one publication."""

    publication: ICResearchPublication
    variants: Mapping[str, ICVariant]
    test_results: Mapping[str, Mapping[str, object]]

    def __post_init__(self) -> None:
        if not isinstance(self.publication, ICResearchPublication):
            raise TypeError(
                "publication must be an ICResearchPublication"
            )

        if self.publication.variant_count != len(self.variants):
            raise ValueError("variant_count must match loaded variants")

        if self.publication.test_count != len(self.test_results):
            raise ValueError("test_count must match loaded test results")

def _require_safe_name(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
        raise ValueError(f"{label} must be a safe non-empty path segment")

    return value

def _json_copy(value: object, *, label: str) -> Any:
    try:
        serialized = json.dumps(
            value, allow_nan= False, sort_keys= True,
        )

    except(TypeError, ValueError) as error:
        raise TypeError(f"{label} must be JSON-serializable") from error
    return json.loads(serialized)

def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()

def _write_dataframe(
        frame: object,
        *,
        staging_dir: Path,
        relative_path: Path,
        files: dict[str, str],
        label: str,
) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")

    path = staging_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)

    relative = relative_path.as_posix()
    content_hash = _file_sha256(path)
    files[relative] = content_hash

    return {
        "path": relative,
        "content_sha256": content_hash,
        "row_count": len(frame.index),
        "column_count": len(frame.columns)
    }

def _write_scope(
        scope: Mapping[str, object],
        *,
        variant_name: str,
        scope_name: str,
        staging_dir: Path,
        files: dict[str, str]
) -> dict[str, Any]:
    if not isinstance(scope, Mapping):
        raise TypeError(f"variant {variant_name!r} scope {scope_name!r} must be a mapping")

    entries: dict[str, Any] = {}
    base = Path("variants") / variant_name / scope_name

    for key, value in scope.items():
        entry_name = _require_safe_name(key, label = "IC scope entry name")

        if isinstance(value, pd.DataFrame):
            entries[entry_name] = {
                "kind": "dataframe",
                **_write_dataframe(
                    value,
                    staging_dir= staging_dir,
                    relative_path= base / f"{entry_name}.parquet",
                    files = files,
                    label = f"{variant_name}.{scope_name}.{entry_name}"
                ),
            }
            continue

        if isinstance(value, Mapping):
            items = []
            for item_key, item_frame in sorted(
                value.items(),
                key = lambda item: str(item[0]),
            ):
                path_name = _require_safe_name(
                    str(item_key),
                    label=f"{entry_name} item key",
                )
                items.append(
                    {
                        "key": item_key,
                        **_write_dataframe(
                            item_frame,
                            staging_dir = staging_dir,
                            relative_path=(
                                base / entry_name / f"{path_name}.parquet"
                            ),
                            files = files,
                            label = f"{entry_name}{item_key!r}",
                        )
                    }
                )
            entries[entry_name] = {
                "kind": "dataframe_dict",
                "items": items,
            }
            continue

        entries[entry_name] = {
            "kind": "value",
            "value": _json_copy(value, label=f"{variant_name}.{scope_name}.{entry_name}"),
        }

    return {"entries": entries}

def _write_manifest_payload(variants: Mapping[str, ICVariant], test_results: Mapping[str, Mapping[str, object]], *, run_id:int, staging_dir: Path) -> dict[str, Any]:
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ValueError("run_id must be a positive integer")

    if not isinstance(variants, Mapping) or not variants:
        raise ValueError("variants must be a non-empty mapping")

    if not isinstance(test_results, Mapping):
        raise TypeError("test_results must be a mapping")

    files: dict[str, str] = {}
    variant_entries: dict[str, Any] = {}

    for variant_name in sorted(variants):
        safe_variant = _require_safe_name(variant_name, label="variant name")
        variant = variants[variant_name]
        if not isinstance(variant, ICVariant):
            raise TypeError(
                f"variant {variant_name!r} must be an ICVariant"
            )

        variant_entries[safe_variant] = {
            "transforms": _json_copy(variant.transforms, label= f"variant {variant_name!r} transforms"),
            "scopes": {
                "train": _write_scope(variant.train, variant_name= safe_variant, scope_name="train", staging_dir=staging_dir, files = files),
                "test": _write_scope(variant.test, variant_name=safe_variant, scope_name="test", staging_dir = staging_dir, files= files)
            }
        }
    test_entries: dict[str, Any] ={}

    for test_id in sorted(test_results):
        safe_test_id = _require_safe_name(test_id, label= "test id")
        result = test_results[test_id]
        if not isinstance(result, Mapping):
            raise TypeError(f"test result {test_id!r} must be a mapping")

        variant_name = _require_safe_name(
            result.get("variant_name"),
            label=f"test {test_id!r} variant_name",
        )
        if variant_name not in variant_entries:
            raise ValueError(
                f"test {test_id!r} reference unknown variant {variant_name!r}"
            )

        test_method = _require_safe_name(
            result.get("test_method"),
            label=f"test {test_id!r} test_method"
        )
        sample_scope = result.get("sample_scope", "train")
        if sample_scope not in {"train", "test"}:
            raise ValueError(
                f"test {test_id!r} has invalid sample_scope"
            )
        base = Path("tests") / safe_test_id / sample_scope
        artifacts = {
            "summary": _write_dataframe(
                result.get("summary"),
                staging_dir=staging_dir,
                relative_path= base / "summary.parquet",
                files = files,
                label = f"test {test_id!r} summary"
            )
        }

        multiple_testing = result.get("multiple_testing")
        if multiple_testing is not None:
            artifacts["multiple_testing"] = _write_dataframe(
                multiple_testing,
                staging_dir = staging_dir,
                relative_path = base / "multiple_testing.parquet",
                files = files,
                label = f"test {test_id!r} multiple_testing"
            )

        test_entries[safe_test_id] = {
            "variant_name": variant_name,
            "test_method": test_method,
            "sample_scope": sample_scope,
            "artifacts": artifacts,
        }

    return {
        "schema_version": 1,
        "run_id": run_id,
        "variant_count": len(variant_entries),
        "test_count": len(test_entries),
        "variants": variant_entries,
        "tests": test_entries,
        "files": dict(sorted(files.items()))
    }

def _publication_from_manifest(
        output_dir: Path,
        manifest: Mapping[str, Any],
) -> ICResearchPublication:
    variants = manifest.get("variants")
    tests = manifest.get("tests")
    if not isinstance(variants, Mapping) or not isinstance(tests, Mapping):
        raise ValueError("IC Research manifest is invalid")

    return ICResearchPublication(
        run_id=manifest["run_id"],
        output_dir=output_dir,
        manifest_path= output_dir /"manifest.json",
        variant_count= manifest["variant_count"],
        test_count = manifest["test_count"],
        variant_names= tuple(sorted(variants)),
        test_ids=tuple(sorted(tests))
    )

def _load_matching_publication(output_dir: Path, *, expected_manifest: Mapping[str, Any]) -> ICResearchPublication:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileExistsError(
            "IC research output already exists but is incomplete"
        )

    try:
        existing = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

    except(OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"IC research manifest is invalid: {manifest_path}"
        ) from error

    if existing != expected_manifest:
        raise FileExistsError(
            "IC research output already exists with different content"
        )

    files = existing.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("IC research manifest has invalid files")

    for relative_path, expected_hash in files.items():
        path = output_dir / relative_path
        if not path.is_file():
            raise FileExistsError(
                "IC research output already exists but is incomplete"
            )
        if _file_sha256(path) != expected_hash:
            raise FileExistsError(
                "IC research output already exists with different content"
            )
    return _publication_from_manifest(output_dir, existing)

def publish_ic_research_artifacts(variants: Mapping[str, ICVariant], test_results: Mapping[str, Mapping[str, object]], *, run_id: int, root: Path) -> ICResearchPublication:
    """Atomically publish one immutable IC workflow result."""

    output_root = Path(root)
    output_dir = output_root / str(run_id)
    output_root.mkdir(parents= True, exist_ok = True)

    staging_dir = output_root / f".{run_id}.staging-{uuid4().hex}"

    try:
        staging_dir.mkdir()
        manifest = _write_manifest_payload(variants, test_results, run_id=run_id, staging_dir = staging_dir)

        if output_dir.exists():
            return _load_matching_publication(output_dir, expected_manifest= manifest)

        (staging_dir /"manifest.json").write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8"
        )

        try:
            staging_dir.rename(output_dir)
        except FileExistsError:
            return _load_matching_publication(output_dir, expected_manifest=manifest)

        return _publication_from_manifest(output_dir, manifest)

    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

def _safe_artifact_path(output_dir: Path, relative_path: object) -> tuple[str, Path]:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise ValueError("IC artifact path must be a safe relative path")

    pure_path = PurePosixPath(relative_path)

    if pure_path.is_absolute() or any(part in {"", ".",".."} for part in pure_path.parts):
        raise ValueError("IC artifact path must be a safe relative path")

    resolved_root = output_dir.resolve()
    resolved_path = resolved_root.joinpath(*pure_path.parts).resolve()

    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(
            "IC artifact path escapes its publication directory"
        ) from error

    return pure_path.as_posix(), resolved_path

def _verify_manifest_files(output_dir: Path, files: object,) -> tuple[dict[str, Path], dict[str, str]]:
    if not isinstance(files, Mapping):
        raise ValueError("IC research manifest has invalid files")

    verified_paths: dict[str, Path] = {}
    verified_hashes: dict[str, str] = {}

    for relative_path, expected_hash in files.items():
        normalized_path, path = _safe_artifact_path(output_dir, relative_path)
        if not isinstance(expected_hash, str) or not expected_hash:
            raise ValueError("IC research manifest has an invalid content hash")

        if normalized_path in verified_paths:
            raise ValueError("IC research manifest contains duplicate artifact paths")

        if not path.is_file():
            raise FileNotFoundError(f"IC artifact does not exist: {path}")

        if _file_sha256(path) != expected_hash:
            raise ValueError(
                f"IC artifact content hash does not match: {normalized_path}"
            )

        verified_paths[normalized_path] = path
        verified_hashes[normalized_path] = expected_hash

    return verified_paths, verified_hashes

def _load_dataframe_entry(entry: object, *, output_dir: Path, verified_paths: Mapping[str, Path], verified_hashes: Mapping[str, str], label: str) -> pd.DataFrame:
    if not isinstance(entry, Mapping):
        raise ValueError(f"{label} manifest entry must be an object")

    relative_path, _ = _safe_artifact_path(output_dir, entry.get("path"))
    if relative_path not in verified_paths:
        raise ValueError(f"{label} path is not registered in manifest in manifest files")

    if entry.get("content_sha256") != verified_hashes[relative_path]:
        raise ValueError(f"{label} content hash is inconsistent with manifest files")

    try:
        frame = pd.read_parquet(verified_paths[relative_path])

    except (OSError, ValueError) as error:
        raise ValueError(
            f"{label} artifact cannot be read"
        ) from error

    if entry.get("row_count") != len(frame.index):
        raise ValueError(f"{label} row_count does not match")

    if entry.get("column_count") != len(frame.columns):
        raise ValueError(f"{label} column_count does not match")

    return frame

def _load_scope(
        scope_payload: object,
        *,
        output_dir: Path,
        verified_paths: Mapping[str, Path],
        verified_hashes: Mapping[str, str],
        label: str,
) -> dict[str, object]:
    if not isinstance(scope_payload, Mapping):
        raise ValueError(f"{label} scope must be an object")

    entries = scope_payload.get("entries")
    if not isinstance(entries, Mapping):
        raise ValueError(f"{label} scope has invalid entries")

    loaded: dict[str, object] = {}

    for entry_name, entry in entries.items():
        safe_name = _require_safe_name(entry_name, label=f"{label} entry name")
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"{label}.{safe_name} entry must be an object"
            )

        kind = entry.get("kind")

        if kind == "dataframe":
            loaded[safe_name] = _load_dataframe_entry(
                entry,
                output_dir= output_dir,
                verified_paths= verified_paths,
                verified_hashes = verified_hashes,
                label=f"{label}.{safe_name}"
            )
            continue

        if kind == "dataframe_dict":
            items = entry.get("items")
            if not isinstance(items, list):
                raise ValueError(
                    f"{label}.{safe_name} items must be a list"
                )
            restored_items: dict[object, pd.DataFrame] = {}
            for item in items:
                if not isinstance(item, Mapping):
                    raise ValueError(
                        f"{label}.{safe_name} contains an invalid item"
                    )

                item_key = item.get("key")
                if not isinstance(item_key, (str, int)) or isinstance(item_key, bool):
                    raise ValueError(
                        f"{label}.{safe_name} contains an invalid key"
                    )

                if item_key in restored_items:
                    raise ValueError(
                        f"{label}.{safe_name} contains duplicate keys"
                    )

                restored_items[item_key] = _load_dataframe_entry(
                    item,
                    output_dir=output_dir,
                    verified_paths= verified_paths,
                    verified_hashes= verified_hashes,
                    label = f"{label}.{safe_name}[{item_key!r}]"
                )

            loaded[safe_name] = restored_items
            continue

        if kind == "value":
            loaded[safe_name] = entry.get("value")
            continue

        raise ValueError(
            f"{label}.{safe_name} has unknown artifact kind {kind!r}"
        )

    return loaded

def load_ic_research_artifacts(*, root: Path, run_id: int) -> ICResearchArtifacts:
    """Load and verify one immutable IC workflow publication."""

    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ValueError("run_id must be a positive integer")

    output_dir = Path(root) / str(run_id)
    manifest_path = output_dir / "manifest.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"IC research manifest does not exist: {manifest_path}"
        )

    try:
        manifest = json.loads(
            manifest_path.read_text(encoding = "utf-8")
        )

    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"IC research manifest is invalid: {manifest_path}"
        ) from error

    if not isinstance(manifest, Mapping):
        raise ValueError("IC research manifest must be a JSON object")

    if manifest.get("run_id") != run_id:
        raise ValueError(
            "IC research manifest run_id does not match request"
        )

    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported IC research manifest schema")

    verified_paths, verified_hashes = _verify_manifest_files(output_dir, manifest.get("files"))

    variants_payload = manifest.get("variants")
    tests_payload = manifest.get("tests")
    if not isinstance(variants_payload, Mapping):
        raise ValueError("IC research manifest has invalid variants")

    if not isinstance(tests_payload, Mapping):
        raise ValueError("IC research manifest has invalid tests")

    if manifest.get("variant_count") != len(variants_payload):
        raise ValueError("IC research manifest variant_count is inconsistent")
    if manifest.get("test_count") != len(tests_payload):
        raise ValueError("IC research manifest test_count is inconsistent")

    variants: dict[str, ICVariant] = {}

    for variant_name, variant_payload in variants_payload.items():
        safe_variant = _require_safe_name(
            variant_name,
            label = "variant name"
        )
        if not isinstance(variant_payload, Mapping):
            raise ValueError(
                f"variant {variant_name!r} manifest is invalid"
            )

        scopes = variant_payload.get("scopes")
        if not isinstance(scopes, Mapping) or set(scopes) != {"train","test"}:
            raise ValueError(f"variant {variant_name!r} must contain train and test scopes")

        transforms = variant_payload.get("transforms")
        if not isinstance(transforms, list):
            raise ValueError(f"variant {variant_name!r} has invalid transforms")

        variants[safe_variant] = ICVariant(
            train = _load_scope(
                scopes["train"],
                output_dir = output_dir,
                verified_paths= verified_paths,
                verified_hashes= verified_hashes,
                label = f"{safe_variant}.train"
            ),
            test = _load_scope(
                scopes["test"],
                output_dir= output_dir,
                verified_paths= verified_paths,
                verified_hashes= verified_hashes,
                label= f"{safe_variant}.test"
            ),
            transforms = transforms,
        )

    test_results: dict[str, dict[str, object]] = {}

    for test_id, test_payload in tests_payload.items():
        safe_test_id = _require_safe_name(test_id, label="test id")
        if not isinstance(test_payload, Mapping):
            raise ValueError(
                f"test {test_id!r} manifest is invalid"
            )
        variant_name = test_payload.get("variant_name")
        if variant_name not in variants:
            raise ValueError(
                f"test {test_id!r} references an unknown variant"
            )

        test_method = _require_safe_name(test_payload.get("test_method"), label= f"test {test_id!r} method")
        sample_scope = test_payload.get("sample_scope")
        if sample_scope not in {"train", "test"}:
            raise ValueError(
                f"test {test_id!r} has invalid sample_scope"
            )
        artifacts = test_payload.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(
                f"test {test_id!r} has invalid artifacts"
            )
        if "summary" not in artifacts:
            raise ValueError(
                f"test {test_id!r} has no summary artifact"
            )

        summary = _load_dataframe_entry(
            artifacts["summary"],
            output_dir= output_dir,
            verified_paths= verified_paths,
            verified_hashes= verified_hashes,
            label = f"test {safe_test_id!r} summary"
        )
        multiple_entry = artifacts.get("multiple_testing")
        multiple_testing = (
            None if multiple_entry is None 
            else _load_dataframe_entry(
                multiple_entry,
                output_dir= output_dir,
                verified_paths= verified_paths,
                verified_hashes= verified_hashes,
                label = f"test {safe_test_id!r} multiple_testing"
            )
        )
        test_results[safe_test_id] = {
            "variant_name": variant_name,
            "test_method": test_method,
            "sample_scope": sample_scope,
            "summary": summary,
            "multiple_testing": multiple_testing
        }

    publication = _publication_from_manifest(
        output_dir,
        manifest
    )
    return ICResearchArtifacts(
        publication = publication,
        variants= variants,
        test_results= test_results
    )