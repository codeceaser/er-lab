"""Stage 7A.1: corpus profile loading.

A corpus profile is a small, frozen list of Stage 5A fixture keys to
include in ONE vector index -- see contracts/corpus_profiles_v1.json.
Never a generic, rule-based profile framework: adding a new profile
means adding a new literal fixture list to that JSON file, nothing more.

Reads Stage 5A's own frozen CanonicalChunk artifacts verbatim -- never
mutates them, never re-derives a value Stage 5A/Stage 4 already computed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ingestion_bench.chunking.model import CanonicalChunk
from ingestion_bench.evaluation.evaluator import FIXTURES

_FIXTURE_KEYS = {f[0] for f in FIXTURES}
_FIXTURE_BY_KEY: dict[str, tuple[str, str, str, str, str]] = {f[0]: f for f in FIXTURES}


def fixture_tuple(fixture: str) -> tuple[str, str, str, str, str]:
    """Resolves one fixture key to its full (fixture, doc_id, artifact_key,
    source_format, suite_key) tuple from the frozen Stage 6A evaluator
    registry -- read-only reuse, never a redefinition of that registry."""
    return _FIXTURE_BY_KEY[fixture]


class CorpusProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    fixtures: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_fixtures_are_real_and_unique(self) -> "CorpusProfile":
        if len(set(self.fixtures)) != len(self.fixtures):
            raise ValueError(f"{self.name}: duplicate fixtures declared")
        unknown = [f for f in self.fixtures if f not in _FIXTURE_KEYS]
        if unknown:
            raise ValueError(f"{self.name}: unknown fixture(s) {unknown!r} -- not in the frozen FIXTURES registry")
        return self


class CorpusProfileSet(BaseModel):
    """The complete, versioned set of corpus profiles."""

    model_config = ConfigDict(extra="forbid")

    corpus_profiles_version: str
    profiles: dict[str, CorpusProfile]
    format_comparison_group: list[str]

    @model_validator(mode="before")
    @classmethod
    def _inject_profile_name_from_dict_key(cls, data: Any) -> Any:
        """The JSON's own profile key (e.g. "baseline_demo") IS the
        profile's name -- injected here so it never has to be repeated
        redundantly inside each profile object in the JSON file."""
        if isinstance(data, dict) and isinstance(data.get("profiles"), dict):
            data = dict(data)
            data["profiles"] = {
                key: {**value, "name": key} if isinstance(value, dict) and "name" not in value else value
                for key, value in data["profiles"].items()
            }
        return data

    @model_validator(mode="after")
    def _validate_baseline_demo_excludes_duplicate_parity_variants(self) -> "CorpusProfileSet":
        if "baseline_demo" in self.profiles:
            fixtures = set(self.profiles["baseline_demo"].fixtures)
            forbidden = {"parity/PARITY_001.docx", "parity/PARITY_001.pptx"}
            overlap = fixtures & forbidden
            if overlap:
                raise ValueError(f"baseline_demo must exclude duplicate parity variants, found: {sorted(overlap)}")
        return self

    @model_validator(mode="after")
    def _validate_format_comparison_group_never_combined(self) -> "CorpusProfileSet":
        for name in self.format_comparison_group:
            if name not in self.profiles:
                raise ValueError(f"format_comparison_group references unknown profile {name!r}")
            profile = self.profiles[name]
            if len(profile.fixtures) != 1:
                raise ValueError(
                    f"format_comparison profile {name!r} must index exactly one fixture (never combined "
                    f"into one format-comparison index), got {profile.fixtures!r}"
                )
        return self

    @model_validator(mode="after")
    def _validate_format_comparison_profiles_are_distinct_fixtures(self) -> "CorpusProfileSet":
        seen_fixtures: dict[str, str] = {}
        for name in self.format_comparison_group:
            fixture = self.profiles[name].fixtures[0]
            if fixture in seen_fixtures:
                raise ValueError(
                    f"format_comparison profiles {seen_fixtures[fixture]!r} and {name!r} both index "
                    f"fixture {fixture!r} -- each format_comparison profile must be a distinct format"
                )
            seen_fixtures[fixture] = name
        return self


def load_corpus_profile_set(path: str | Path) -> CorpusProfileSet:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return CorpusProfileSet.model_validate(data)


@dataclass(frozen=True)
class TaggedChunk:
    """One CanonicalChunk tagged with the fixture/document/format identity
    it came from -- CanonicalChunk itself carries no "fixture" or
    "source_format" field (Stage 5A/6A's own FIXTURES registry is the
    only place that mapping exists), and this package must never modify
    CanonicalChunk to add one."""

    fixture: str
    doc_id: str
    source_format: str
    chunk: CanonicalChunk


def load_corpus_chunks(profile: CorpusProfile, artifacts_root: Path) -> list[TaggedChunk]:
    """Reads canonical_chunks.jsonl for every fixture in `profile`, in the
    profile's own declared fixture order (deterministic), tagging each
    chunk with its fixture/doc_id/source_format. Never mutates the
    underlying Stage 5A artifact files."""
    tagged: list[TaggedChunk] = []
    for fixture in profile.fixtures:
        _, doc_id, artifact_key, source_format, _suite_key = fixture_tuple(fixture)
        chunks_path = artifacts_root / artifact_key / "canonical_chunks.jsonl"
        if not chunks_path.exists():
            raise FileNotFoundError(
                f"{chunks_path} not found -- run scripts/run_docling_standard.py first to generate Stage 5A artifacts"
            )
        for line in chunks_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            chunk = CanonicalChunk.model_validate(json.loads(line))
            tagged.append(TaggedChunk(fixture=fixture, doc_id=doc_id, source_format=source_format, chunk=chunk))
    return tagged
