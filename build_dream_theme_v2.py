#!/usr/bin/env python3
"""Validate, compare, adjudicate, and materialize Dream-theme v2 reviews.

The two blind passes use the temporary review schema documented by the pass
prompts: one primary object, co_dominant/supporting arrays, categorical
confidence, exact evidence_quotes, and optional rejected candidates. This
script turns those quotes into validated Unicode-code-point spans, attaches the
current source digest, compares only the public primary/co-dominant roles, and
writes the final v2 assignment and review documents once all required
adjudications are present.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "data/extracted.json"
TAXONOMY_PATH = ROOT / "data/dream_themes_v2.json"
EXPECTED_DREAM_ROWS = 238
SCHEMA_VERSION = 2
TAXONOMY_VERSION = 2
SOURCE_DIGEST_ALGORITHM = "sha256-canonical-dreams-text-v1"
JUDGMENT_DIGEST_ALGORITHM = "sha256-canonical-json-v1"
V1_ASSIGNMENTS_SUPERSEDES = {
    "taxonomy_version": 1,
    "path": "data/dream_theme_assignments.json",
    "sha256": "eb82e7810938ef97e28097ed5bcfb21ba06ce26f12d61a7b60aa470b18b8766b",
}
V1_REVIEW_SUPERSEDES = {
    "taxonomy_version": 1,
    "path": "data/dream_theme_review.json",
    "sha256": "404c2c00ce4348615c26d921fb9e7b443606972fc913bfdcd0438a663d3a9129",
}

SCORE_DIMENSIONS = (
    "explicit_support",
    "centrality",
    "standalone",
    "specificity",
)
SUPPORTING_REASONS = {
    "inferred",
    "means",
    "setting",
    "beneficiary",
    "consequence",
    "better-explained",
}
PUBLIC_ROLES = ("primary", "co-dominant")


class ValidationError(ValueError):
    """Raised when an input document cannot safely enter the v2 dataset."""


@dataclass(frozen=True)
class Context:
    taxonomy: dict[str, Any]
    source_rows: tuple[dict[str, Any], ...]
    source_by_key: dict[tuple[str, str], dict[str, Any]]
    theme_ids: tuple[str, ...]
    theme_order: dict[str, int]
    confidence_values: frozenset[str]
    minimum_score: int
    maximum_score: int
    primary_minimum: int
    co_dominant_minimum: int
    supporting_minimum: int


def fail(message: str) -> None:
    raise ValidationError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing JSON file: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def dream_source_digest(row: dict[str, Any]) -> str:
    return digest_json({"dreams": row.get("dreams"), "text": row.get("text")})


def source_digest(row: dict[str, Any]) -> str:
    """Public helper for the current Dream source-row digest."""
    return dream_source_digest(row)


def judgment_digest(judgment: dict[str, Any]) -> str:
    """Public helper for a normalized blind-pass judgment digest."""
    return digest_json(judgment)


def assignment_digest(assignment: dict[str, Any]) -> str:
    """Public helper for a normalized final-assignment digest."""
    return digest_json(assignment)


def source_key(row: dict[str, Any]) -> tuple[str, str]:
    return row.get("username"), row.get("created_time")


def key_label(key: tuple[str, str]) -> str:
    return f"{key[0]!r} at {key[1]!r}"


def sorted_keys(keys: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted(keys, key=lambda item: (item[0], item[1]))


def load_context() -> Context:
    taxonomy = load_json(TAXONOMY_PATH)
    require(isinstance(taxonomy, dict), "v2 taxonomy must be a JSON object")
    require(taxonomy.get("schema_version") == SCHEMA_VERSION, "taxonomy schema_version must be 2")
    require(taxonomy.get("taxonomy_version") == TAXONOMY_VERSION, "taxonomy_version must be 2")

    themes = taxonomy.get("themes")
    require(isinstance(themes, list) and themes, "taxonomy themes must be a non-empty array")
    theme_ids = tuple(theme.get("id") for theme in themes)
    require(all(isinstance(theme_id, str) and theme_id for theme_id in theme_ids), "every theme needs an ID")
    require(len(theme_ids) == len(set(theme_ids)), "taxonomy theme IDs must be unique")
    require(
        [theme.get("order") for theme in themes] == list(range(1, len(themes) + 1)),
        "taxonomy themes must use contiguous one-based order",
    )

    roles = taxonomy.get("roles")
    require(isinstance(roles, list), "taxonomy roles must be an array")
    role_by_id = {role.get("id"): role for role in roles if isinstance(role, dict)}
    require(set(role_by_id) == {"primary", "co-dominant", "supporting"}, "taxonomy roles are incomplete")
    require(role_by_id["primary"].get("counts_in_pie") is True, "primary must count in the pie")
    require(role_by_id["co-dominant"].get("public") is True, "co-dominant must be public")
    require(role_by_id["supporting"].get("public") is False, "supporting must remain private")

    dimensions = taxonomy.get("score_dimensions")
    require(isinstance(dimensions, list), "score_dimensions must be an array")
    require(
        tuple(dimension.get("id") for dimension in dimensions) == SCORE_DIMENSIONS,
        "score_dimensions must match the v2 rubric in order",
    )
    for dimension in dimensions:
        anchors = dimension.get("anchors")
        require(
            isinstance(anchors, dict) and set(anchors) == {"0", "1", "2"},
            f"score dimension {dimension.get('id')} must define 0/1/2 anchors",
        )

    scale = taxonomy.get("score_scale")
    require(isinstance(scale, dict), "score_scale must be an object")
    numeric_scale_fields = (
        "minimum_per_dimension",
        "maximum_per_dimension",
        "primary_minimum_total",
        "co_dominant_minimum_total",
        "supporting_minimum_total",
    )
    require(
        all(isinstance(scale.get(field), int) for field in numeric_scale_fields),
        "score_scale values must be integers",
    )

    confidence_values = taxonomy.get("confidence_values")
    require(
        isinstance(confidence_values, list)
        and set(confidence_values) == {"high", "medium", "low"},
        "confidence_values must be high, medium, and low",
    )

    source = load_json(SOURCE_PATH)
    require(isinstance(source, list), "data/extracted.json must be an array")
    dream_rows = tuple(
        row
        for row in source
        if isinstance(row.get("dreams"), str) and len(row["dreams"]) > 0
    )
    require(
        len(dream_rows) == EXPECTED_DREAM_ROWS,
        f"expected {EXPECTED_DREAM_ROWS} non-empty Dream rows, found {len(dream_rows)}",
    )
    for row in dream_rows:
        require(isinstance(row.get("username"), str) and row["username"], "source row has invalid username")
        require(
            isinstance(row.get("created_time"), str) and row["created_time"],
            f"source row {row.get('username')!r} has invalid created_time",
        )
        require(isinstance(row.get("text"), str), f"source row {key_label(source_key(row))} has invalid text")
    source_by_key = {source_key(row): row for row in dream_rows}
    require(len(source_by_key) == len(dream_rows), "Dream response identities must be unique")

    return Context(
        taxonomy=taxonomy,
        source_rows=dream_rows,
        source_by_key=source_by_key,
        theme_ids=theme_ids,
        theme_order={theme_id: index for index, theme_id in enumerate(theme_ids)},
        confidence_values=frozenset(confidence_values),
        minimum_score=scale["minimum_per_dimension"],
        maximum_score=scale["maximum_per_dimension"],
        primary_minimum=scale["primary_minimum_total"],
        co_dominant_minimum=scale["co_dominant_minimum_total"],
        supporting_minimum=scale["supporting_minimum_total"],
    )


def normalize_reviewer(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} reviewer must be an object")
    for field in ("reviewer_id", "kind", "prompt_version"):
        require(
            isinstance(value.get(field), str) and value[field].strip(),
            f"{label} reviewer.{field} must be a non-empty string",
        )
    return copy.deepcopy(value)


def quote_to_span(text: str, quote: str, label: str) -> dict[str, Any]:
    require(isinstance(quote, str) and quote, f"{label} evidence quote must be non-empty")
    start = text.find(quote)
    require(start >= 0, f"{label} evidence quote is not an exact substring of source text: {quote!r}")
    return {
        "field": "text",
        "start": start,
        "end": start + len(quote),
        "quote": quote,
    }


def validate_span(text: str, raw: Any, label: str) -> dict[str, Any]:
    require(isinstance(raw, dict), f"{label} evidence span must be an object")
    require(raw.get("field") == "text", f"{label} evidence span field must be text")
    start = raw.get("start")
    end = raw.get("end")
    quote = raw.get("quote")
    require(isinstance(start, int) and not isinstance(start, bool), f"{label} span start must be an integer")
    require(isinstance(end, int) and not isinstance(end, bool), f"{label} span end must be an integer")
    require(0 <= start < end <= len(text), f"{label} evidence span is outside source text")
    require(isinstance(quote, str) and quote, f"{label} evidence span quote must be non-empty")
    require(text[start:end] == quote, f"{label} evidence span does not reproduce its quote")
    return {"field": "text", "start": start, "end": end, "quote": quote}


def normalize_evidence(raw: dict[str, Any], text: str, label: str) -> list[dict[str, Any]]:
    has_quotes = "evidence_quotes" in raw
    has_spans = "evidence_spans" in raw
    require(has_quotes or has_spans, f"{label} must provide evidence_quotes or evidence_spans")

    spans: list[dict[str, Any]] = []
    if has_spans:
        raw_spans = raw.get("evidence_spans")
        require(isinstance(raw_spans, list) and raw_spans, f"{label} evidence_spans must be non-empty")
        spans = [validate_span(text, span, label) for span in raw_spans]
    if has_quotes:
        quotes = raw.get("evidence_quotes")
        require(isinstance(quotes, list) and quotes, f"{label} evidence_quotes must be non-empty")
        quote_spans = [quote_to_span(text, quote, label) for quote in quotes]
        if has_spans:
            require(
                [span["quote"] for span in spans] == [span["quote"] for span in quote_spans],
                f"{label} evidence_quotes and evidence_spans disagree",
            )
        else:
            spans = quote_spans

    unique: dict[tuple[int, int, str], dict[str, Any]] = {}
    for span in spans:
        unique[(span["start"], span["end"], span["quote"])] = span
    return [unique[key] for key in sorted(unique)]


def normalize_scores(value: Any, role: str, label: str, context: Context) -> dict[str, int]:
    require(isinstance(value, dict), f"{label} scores must be an object")
    require(set(value) == {*SCORE_DIMENSIONS, "total"}, f"{label} scores have the wrong fields")
    normalized: dict[str, int] = {}
    for dimension in SCORE_DIMENSIONS:
        score = value.get(dimension)
        require(
            isinstance(score, int)
            and not isinstance(score, bool)
            and context.minimum_score <= score <= context.maximum_score,
            f"{label} {dimension} must be an integer from {context.minimum_score} to {context.maximum_score}",
        )
        normalized[dimension] = score
    total = value.get("total")
    require(isinstance(total, int) and not isinstance(total, bool), f"{label} total must be an integer")
    require(total == sum(normalized.values()), f"{label} score total does not equal its dimensions")
    normalized["total"] = total

    thresholds = {
        "primary": context.primary_minimum,
        "co-dominant": context.co_dominant_minimum,
        "supporting": context.supporting_minimum,
    }
    require(total >= thresholds[role], f"{label} total {total} is below the {role} threshold")
    return normalized


def normalize_classification(
    value: Any,
    *,
    role: str,
    source: dict[str, Any],
    context: Context,
    label: str,
) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} classification must be an object")
    allowed_fields = {
        "theme_id",
        "evidence_quotes",
        "evidence_spans",
        "scores",
        "confidence",
        "supporting_reason",
    }
    require(not (set(value) - allowed_fields), f"{label} has unknown fields: {sorted(set(value) - allowed_fields)}")
    theme_id = value.get("theme_id")
    require(theme_id in context.theme_order, f"{label} has unknown theme_id {theme_id!r}")
    scores = normalize_scores(value.get("scores"), role, label, context)
    confidence = value.get("confidence")
    require(confidence in context.confidence_values, f"{label} has invalid confidence {confidence!r}")

    if confidence == "high" and role == "primary":
        require(scores["total"] == 8, f"{label} high-confidence primary must total 8")
    if confidence == "high" and role == "co-dominant":
        require(scores["total"] >= 7, f"{label} high-confidence co-dominant must total at least 7")

    normalized = {
        "theme_id": theme_id,
        "evidence_spans": normalize_evidence(value, source["text"], label),
        "scores": scores,
        "confidence": confidence,
    }
    if role == "supporting":
        reason = value.get("supporting_reason")
        require(reason in SUPPORTING_REASONS, f"{label} has invalid supporting_reason {reason!r}")
        normalized["supporting_reason"] = reason
    else:
        require("supporting_reason" not in value, f"{label} must not have supporting_reason")
    return normalized


def normalize_rejected(value: Any, context: Context, label: str) -> dict[str, str]:
    require(isinstance(value, dict), f"{label} rejected candidate must be an object")
    require(
        {"theme_id", "reason"} <= set(value) <= {"theme_id", "reason", "detail"},
        f"{label} rejected candidate has the wrong fields",
    )
    theme_id = value.get("theme_id")
    reason = value.get("reason")
    require(theme_id in context.theme_order, f"{label} rejected candidate has unknown theme {theme_id!r}")
    require(reason in SUPPORTING_REASONS, f"{label} has invalid rejected reason {reason!r}")
    normalized = {"theme_id": theme_id, "reason": reason}
    if "detail" in value:
        detail = value.get("detail")
        require(isinstance(detail, str) and detail.strip(), f"{label} rejected detail must be non-empty")
        normalized["detail"] = detail.strip()
    return normalized


def normalize_assignment(value: Any, source: dict[str, Any], context: Context, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} assignment must be an object")
    allowed_fields = {
        "username",
        "created_time",
        "source_digest",
        "public_status",
        "primary",
        "co_dominant",
        "supporting",
        "rejected_candidates",
        "unthemed_reason",
    }
    require(not (set(value) - allowed_fields), f"{label} has unknown assignment fields: {sorted(set(value) - allowed_fields)}")
    key = source_key(value)
    require(key == source_key(source), f"{label} assignment identity does not match its source")

    current_digest = dream_source_digest(source)
    if "source_digest" in value:
        require(value.get("source_digest") == current_digest, f"{label} has a stale source_digest")

    status = value.get("public_status")
    require(status in {"themed", "unthemed"}, f"{label} public_status must be themed or unthemed")
    co_raw = value.get("co_dominant")
    supporting_raw = value.get("supporting")
    rejected_raw = value.get("rejected_candidates")
    require(isinstance(co_raw, list), f"{label} co_dominant must be an array")
    require(isinstance(supporting_raw, list), f"{label} supporting must be an array")
    require(isinstance(rejected_raw, list), f"{label} rejected_candidates must be an array")
    require(len(co_raw) <= 2, f"{label} cannot have more than two co-dominant themes")

    primary = None
    if value.get("primary") is not None:
        primary = normalize_classification(
            value["primary"],
            role="primary",
            source=source,
            context=context,
            label=f"{label} primary",
        )
    co_dominant = [
        normalize_classification(
            item,
            role="co-dominant",
            source=source,
            context=context,
            label=f"{label} co-dominant[{index}]",
        )
        for index, item in enumerate(co_raw)
    ]
    supporting = [
        normalize_classification(
            item,
            role="supporting",
            source=source,
            context=context,
            label=f"{label} supporting[{index}]",
        )
        for index, item in enumerate(supporting_raw)
    ]
    rejected = [
        normalize_rejected(item, context, f"{label} rejected[{index}]")
        for index, item in enumerate(rejected_raw)
    ]

    if status == "themed":
        require(primary is not None, f"{label} themed response must have exactly one primary")
        require(value.get("unthemed_reason") is None, f"{label} themed response cannot have unthemed_reason")
        for item in co_dominant:
            require(
                primary["scores"]["total"] - 1 <= item["scores"]["total"] <= primary["scores"]["total"],
                f"{label} co-dominant score must be within one point of primary and not exceed it",
            )
    else:
        require(primary is None, f"{label} unthemed response cannot have a primary")
        require(not co_dominant, f"{label} unthemed response cannot have co-dominant themes")
        reason = value.get("unthemed_reason")
        require(isinstance(reason, str) and reason.strip(), f"{label} unthemed response needs a reason")

    public_count = (1 if primary else 0) + len(co_dominant)
    require(public_count <= 3, f"{label} cannot publish four or more themes")
    if public_count == 3:
        require(
            all(item["scores"]["total"] >= 7 for item in [primary, *co_dominant]),
            f"{label} three-public-theme case requires a score of at least 7 for every public theme",
        )

    classified = [item for item in [primary, *co_dominant, *supporting] if item is not None]
    classified_ids = [item["theme_id"] for item in classified]
    rejected_ids = [item["theme_id"] for item in rejected]
    require(len(classified_ids) == len(set(classified_ids)), f"{label} classifies a theme more than once")
    require(len(rejected_ids) == len(set(rejected_ids)), f"{label} rejects a theme more than once")
    require(not (set(classified_ids) & set(rejected_ids)), f"{label} both classifies and rejects a theme")

    co_dominant.sort(key=lambda item: context.theme_order[item["theme_id"]])
    supporting.sort(key=lambda item: context.theme_order[item["theme_id"]])
    rejected.sort(key=lambda item: context.theme_order[item["theme_id"]])
    return {
        "username": source["username"],
        "created_time": source["created_time"],
        "source_digest": current_digest,
        "public_status": status,
        "primary": primary,
        "co_dominant": co_dominant,
        "supporting": supporting,
        "rejected_candidates": rejected,
        "unthemed_reason": None if status == "themed" else value["unthemed_reason"].strip(),
    }


def normalize_pass_files(paths: list[Path], expected_pass_id: str, context: Context) -> dict[str, Any]:
    require(paths, f"{expected_pass_id} needs at least one input path")
    reviewer: dict[str, Any] | None = None
    assignments_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for path in paths:
        document = load_json(path)
        require(isinstance(document, dict), f"{path} must contain a JSON object")
        allowed_top = {"schema_version", "taxonomy_version", "pass_id", "reviewer", "assignments", "batch"}
        require(not (set(document) - allowed_top), f"{path} has unknown top-level fields: {sorted(set(document) - allowed_top)}")
        require(document.get("schema_version") == SCHEMA_VERSION, f"{path} schema_version must be 2")
        require(document.get("taxonomy_version") == TAXONOMY_VERSION, f"{path} taxonomy_version must be 2")
        require(document.get("pass_id") == expected_pass_id, f"{path} pass_id must be {expected_pass_id}")

        current_reviewer = normalize_reviewer(document.get("reviewer"), str(path))
        if reviewer is None:
            reviewer = current_reviewer
        else:
            require(
                canonical_json(current_reviewer) == canonical_json(reviewer),
                f"{expected_pass_id} batch files use different reviewer metadata",
            )

        raw_assignments = document.get("assignments")
        require(isinstance(raw_assignments, list), f"{path} assignments must be an array")
        if "batch" in document:
            batch = document["batch"]
            require(isinstance(batch, dict), f"{path} batch must be an object")
            start = batch.get("start")
            end = batch.get("end")
            require(
                isinstance(start, int) and isinstance(end, int) and 0 <= start <= end,
                f"{path} batch start/end are invalid",
            )
            require(end - start + 1 == len(raw_assignments), f"{path} batch range does not match assignment count")

        for index, raw in enumerate(raw_assignments):
            require(isinstance(raw, dict), f"{path} assignment[{index}] must be an object")
            key = source_key(raw)
            require(key in context.source_by_key, f"{path} assignment[{index}] has unknown identity {key_label(key)}")
            require(key not in assignments_by_key, f"duplicate {expected_pass_id} assignment for {key_label(key)}")
            assignments_by_key[key] = normalize_assignment(
                raw,
                context.source_by_key[key],
                context,
                f"{expected_pass_id} {key_label(key)}",
            )

    expected = set(context.source_by_key)
    actual = set(assignments_by_key)
    if actual != expected:
        missing = ", ".join(key_label(key) for key in sorted_keys(expected - actual)[:5])
        extra = ", ".join(key_label(key) for key in sorted_keys(actual - expected)[:5])
        fail(
            f"{expected_pass_id} coverage must be exactly {EXPECTED_DREAM_ROWS} rows; "
            f"missing={len(expected - actual)} [{missing}], extra={len(actual - expected)} [{extra}]"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "pass_id": expected_pass_id,
        "reviewer": reviewer,
        "assignments": [assignments_by_key[key] for key in sorted_keys(assignments_by_key)],
    }


def validate_pass_documents(
    paths: Iterable[Path | str],
    expected_pass_id: str,
    context: Context | None = None,
) -> dict[str, Any]:
    """Import-safe public validator/normalizer for one complete blind pass."""
    active_context = context or load_context()
    return normalize_pass_files([Path(path) for path in paths], expected_pass_id, active_context)


def validate_assignments_document(
    document: Any,
    context: Context | None = None,
) -> dict[str, Any]:
    """Validate and normalize a generated v2 final-assignments document.

    This is intentionally reusable by ``build_page.py``: it returns only
    current, fully validated source-linked assignments and never writes files.
    """
    active_context = context or load_context()
    require(isinstance(document, dict), "v2 assignments document must be an object")
    allowed_top = {
        "schema_version",
        "taxonomy_version",
        "supersedes",
        "source_digest_algorithm",
        "source_row_count",
        "assignments",
    }
    require(
        not (set(document) - allowed_top),
        f"v2 assignments document has unknown fields: {sorted(set(document) - allowed_top)}",
    )
    require(document.get("schema_version") == SCHEMA_VERSION, "assignments schema_version must be 2")
    require(document.get("taxonomy_version") == TAXONOMY_VERSION, "assignments taxonomy_version must be 2")
    require(
        document.get("supersedes") == V1_ASSIGNMENTS_SUPERSEDES,
        "assignments supersedes metadata does not match the preserved v1 file",
    )
    require(
        document.get("source_digest_algorithm") == SOURCE_DIGEST_ALGORITHM,
        f"source_digest_algorithm must be {SOURCE_DIGEST_ALGORITHM}",
    )
    require(
        document.get("source_row_count") == len(active_context.source_rows),
        "assignments source_row_count is stale",
    )
    raw_assignments = document.get("assignments")
    require(isinstance(raw_assignments, list), "assignments must be an array")
    normalized_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(raw_assignments):
        require(isinstance(raw, dict), f"assignments[{index}] must be an object")
        key = source_key(raw)
        require(key in active_context.source_by_key, f"assignments[{index}] has unknown identity {key_label(key)}")
        require(key not in normalized_by_key, f"duplicate final assignment for {key_label(key)}")
        review_status = raw.get("review_status")
        adjudication_id = raw.get("adjudication_id")
        require(
            review_status in {"blind-public-role-agreement", "adjudicated"},
            f"assignments[{index}] has invalid review_status",
        )
        if review_status == "adjudicated":
            require(
                isinstance(adjudication_id, str) and adjudication_id,
                f"assignments[{index}] adjudicated row needs adjudication_id",
            )
        else:
            require(adjudication_id is None, f"assignments[{index}] agreement row cannot have adjudication_id")
        temporary = {
            field: value
            for field, value in raw.items()
            if field not in {"review_status", "adjudication_id"}
        }
        normalized = normalize_assignment(
            temporary,
            active_context.source_by_key[key],
            active_context,
            f"final assignment {key_label(key)}",
        )
        normalized["review_status"] = review_status
        normalized["adjudication_id"] = adjudication_id
        normalized_by_key[key] = normalized
    require(
        set(normalized_by_key) == set(active_context.source_by_key),
        "final assignments must cover every non-empty Dream response exactly once",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "supersedes": V1_ASSIGNMENTS_SUPERSEDES,
        "source_digest_algorithm": SOURCE_DIGEST_ALGORITHM,
        "source_row_count": len(active_context.source_rows),
        "assignments": [normalized_by_key[key] for key in sorted_keys(normalized_by_key)],
    }


def assignment_map(pass_document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {source_key(item): item for item in pass_document["assignments"]}


def public_signature(item: dict[str, Any]) -> tuple[str | None, frozenset[str], frozenset[str]]:
    primary = item["primary"]["theme_id"] if item["primary"] else None
    co_dominant = frozenset(theme["theme_id"] for theme in item["co_dominant"])
    public_set = frozenset(([primary] if primary else []) + list(co_dominant))
    return primary, co_dominant, public_set


def public_classifications(item: dict[str, Any]) -> list[dict[str, Any]]:
    return ([item["primary"]] if item["primary"] else []) + item["co_dominant"]


def required_adjudication_reasons(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    a_primary, a_co, _ = public_signature(a)
    b_primary, b_co, _ = public_signature(b)
    reasons: list[str] = []
    if a_primary != b_primary or a_co != b_co:
        reasons.append("public-role-disagreement")
    if any(item["confidence"] == "low" for item in public_classifications(a) + public_classifications(b)):
        reasons.append("public-low-confidence")
    if len(public_classifications(a)) == 3 or len(public_classifications(b)) == 3:
        reasons.append("three-public-themes")
    return reasons


def safe_ratio(numerator: int, denominator: int, *, empty_value: float = 0.0) -> float:
    return round(numerator / denominator, 6) if denominator else empty_value


def theme_f1(
    pass_a: dict[tuple[str, str], dict[str, Any]],
    pass_b: dict[tuple[str, str], dict[str, Any]],
    theme_id: str,
    *,
    primary_only: bool,
) -> dict[str, Any]:
    a_positive: set[tuple[str, str]] = set()
    b_positive: set[tuple[str, str]] = set()
    for key in pass_a:
        a_primary, _, a_public = public_signature(pass_a[key])
        b_primary, _, b_public = public_signature(pass_b[key])
        if (a_primary == theme_id) if primary_only else (theme_id in a_public):
            a_positive.add(key)
        if (b_primary == theme_id) if primary_only else (theme_id in b_public):
            b_positive.add(key)
    true_positive = len(a_positive & b_positive)
    false_positive = len(b_positive - a_positive)
    false_negative = len(a_positive - b_positive)
    precision = safe_ratio(true_positive, true_positive + false_positive, empty_value=1.0 if not a_positive else 0.0)
    recall = safe_ratio(true_positive, true_positive + false_negative, empty_value=1.0 if not b_positive else 0.0)
    f1 = round(2 * precision * recall / (precision + recall), 6) if precision + recall else 0.0
    return {
        "pass_a_positive": len(a_positive),
        "pass_b_positive": len(b_positive),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def compare_passes(pass_a_document: dict[str, Any], pass_b_document: dict[str, Any], context: Context) -> dict[str, Any]:
    pass_a = assignment_map(pass_a_document)
    pass_b = assignment_map(pass_b_document)
    exact_set = 0
    primary = 0
    exact_roles = 0
    required: list[dict[str, Any]] = []

    for key in sorted_keys(pass_a):
        a_primary, a_co, a_set = public_signature(pass_a[key])
        b_primary, b_co, b_set = public_signature(pass_b[key])
        exact_set += a_set == b_set
        primary += a_primary == b_primary
        exact_roles += a_primary == b_primary and a_co == b_co
        reasons = required_adjudication_reasons(pass_a[key], pass_b[key])
        if reasons:
            required.append({"username": key[0], "created_time": key[1], "reasons": reasons})

    total = len(pass_a)
    return {
        "row_count": total,
        "agreement": {
            "exact_public_set": {
                "count": exact_set,
                "rate": safe_ratio(exact_set, total),
            },
            "primary": {
                "count": primary,
                "rate": safe_ratio(primary, total),
            },
            "exact_public_roles": {
                "count": exact_roles,
                "rate": safe_ratio(exact_roles, total),
            },
        },
        "per_theme_public_f1": {
            theme_id: theme_f1(pass_a, pass_b, theme_id, primary_only=False)
            for theme_id in context.theme_ids
        },
        "per_theme_primary_f1": {
            theme_id: theme_f1(pass_a, pass_b, theme_id, primary_only=True)
            for theme_id in context.theme_ids
        },
        "required_adjudications": required,
    }


def make_adjudication_packet(
    comparison: dict[str, Any],
    pass_a_document: dict[str, Any],
    pass_b_document: dict[str, Any],
    context: Context,
) -> dict[str, Any]:
    pass_a = assignment_map(pass_a_document)
    pass_b = assignment_map(pass_b_document)
    rows = []
    for required in comparison["required_adjudications"]:
        key = required["username"], required["created_time"]
        source = context.source_by_key[key]
        rows.append({
            "reasons": required["reasons"],
            "source": {
                "username": source["username"],
                "created_time": source["created_time"],
                "dreams": source["dreams"],
                "text": source["text"],
                "source_digest": dream_source_digest(source),
            },
            "pass_a": pass_a[key],
            "pass_b": pass_b[key],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "kind": "dream-theme-v2-adjudication-packet",
        "comparison": comparison,
        "rows": rows,
    }


def normalize_adjudications(
    path: Path,
    context: Context,
) -> tuple[dict[str, Any], dict[tuple[str, str], dict[str, Any]]]:
    document = load_json(path)
    require(isinstance(document, dict), "adjudications file must contain an object")
    allowed_top = {"schema_version", "taxonomy_version", "adjudicator", "adjudications"}
    require(not (set(document) - allowed_top), f"adjudications file has unknown fields: {sorted(set(document) - allowed_top)}")
    require(document.get("schema_version") == SCHEMA_VERSION, "adjudications schema_version must be 2")
    require(document.get("taxonomy_version") == TAXONOMY_VERSION, "adjudications taxonomy_version must be 2")
    adjudicator = normalize_reviewer(document.get("adjudicator"), "adjudicator")
    raw_items = document.get("adjudications")
    require(isinstance(raw_items, list), "adjudications must be an array")

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, item in enumerate(raw_items):
        label = f"adjudication[{index}]"
        require(isinstance(item, dict), f"{label} must be an object")
        required_fields = {"adjudication_id", "username", "created_time", "decision_reason", "final_assignment"}
        require(set(item) == required_fields, f"{label} must contain exactly {sorted(required_fields)}")
        key = source_key(item)
        require(key in context.source_by_key, f"{label} has unknown identity {key_label(key)}")
        require(key not in by_key, f"duplicate adjudication for {key_label(key)}")
        reason = item.get("decision_reason")
        require(isinstance(reason, str) and reason.strip(), f"{label} needs a decision_reason")
        final_raw = item.get("final_assignment")
        require(isinstance(final_raw, dict), f"{label} final_assignment must be an object")
        final_with_identity = copy.deepcopy(final_raw)
        final_with_identity.setdefault("username", key[0])
        final_with_identity.setdefault("created_time", key[1])
        final = normalize_assignment(final_with_identity, context.source_by_key[key], context, f"{label} final")
        adjudication_id = item.get("adjudication_id")
        require(isinstance(adjudication_id, str) and adjudication_id, f"{label} adjudication_id must be a string")
        by_key[key] = {
            "adjudication_id": adjudication_id,
            "username": key[0],
            "created_time": key[1],
            "decision_reason": reason.strip(),
            "final_assignment": final,
        }
    return adjudicator, by_key


def finalize_documents(
    pass_a_document: dict[str, Any],
    pass_b_document: dict[str, Any],
    comparison: dict[str, Any],
    context: Context,
    adjudicator: dict[str, Any] | None,
    adjudications: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    pass_a = assignment_map(pass_a_document)
    pass_b = assignment_map(pass_b_document)
    required_by_key = {
        (item["username"], item["created_time"]): item["reasons"]
        for item in comparison["required_adjudications"]
    }
    missing = set(required_by_key) - set(adjudications)
    if missing:
        sample = ", ".join(key_label(key) for key in sorted_keys(missing)[:5])
        fail(f"missing {len(missing)} required adjudications: {sample}")
    unexpected = set(adjudications) - set(required_by_key)
    if unexpected:
        sample = ", ".join(key_label(key) for key in sorted_keys(unexpected)[:5])
        fail(f"found {len(unexpected)} unnecessary adjudications: {sample}")

    final_assignments = []
    resolutions = []
    normalized_adjudications = []
    for key in sorted_keys(pass_a):
        if key in adjudications:
            adjudication = adjudications[key]
            final = copy.deepcopy(adjudication["final_assignment"])
            review_status = "adjudicated"
            adjudication_id = adjudication["adjudication_id"]
        else:
            final = copy.deepcopy(pass_a[key])
            review_status = "blind-public-role-agreement"
            adjudication_id = None

        final["review_status"] = review_status
        final["adjudication_id"] = adjudication_id
        final_assignments.append(final)

        pass_a_digest = digest_json(pass_a[key])
        pass_b_digest = digest_json(pass_b[key])
        final_digest = digest_json(final)
        resolution = {
            "username": key[0],
            "created_time": key[1],
            "decision": review_status,
            "required_reasons": required_by_key.get(key, []),
            "pass_a_judgment_digest": pass_a_digest,
            "pass_b_judgment_digest": pass_b_digest,
            "final_assignment_digest": final_digest,
            "adjudication_id": adjudication_id,
        }
        resolutions.append(resolution)

        if key in adjudications:
            item = {
                "adjudication_id": adjudication_id,
                "username": key[0],
                "created_time": key[1],
                "source_digest": final["source_digest"],
                "required_reasons": required_by_key.get(key, []),
                "decision_reason": adjudications[key]["decision_reason"],
                "pass_a_judgment_digest": pass_a_digest,
                "pass_b_judgment_digest": pass_b_digest,
                "final_assignment_digest": final_digest,
            }
            item["adjudication_digest"] = digest_json(item)
            normalized_adjudications.append(item)

    assignments_document = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "supersedes": V1_ASSIGNMENTS_SUPERSEDES,
        "source_digest_algorithm": SOURCE_DIGEST_ALGORITHM,
        "source_row_count": len(context.source_rows),
        "assignments": final_assignments,
    }
    review_document = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "supersedes": V1_REVIEW_SUPERSEDES,
        "review_method": "two-full-coverage-blind-independent-passes",
        "source_digest_algorithm": SOURCE_DIGEST_ALGORITHM,
        "judgment_digest_algorithm": JUDGMENT_DIGEST_ALGORITHM,
        "source_row_count": len(context.source_rows),
        "blind_passes": [pass_a_document, pass_b_document],
        "comparison": comparison,
        "adjudicator": adjudicator,
        "adjudications": normalized_adjudications,
        "resolutions": resolutions,
        "all_required_adjudications_complete": True,
    }
    return assignments_document, review_document


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = pretty_json(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def self_test() -> None:
    context = load_context()
    require(len(context.source_rows) == EXPECTED_DREAM_ROWS, "self-test source coverage failed")
    text = "🌙 I want freedom and time."
    span = quote_to_span(text, "I want freedom", "self-test")
    require(span["start"] == 2, "evidence offsets are not Unicode code-point indexes")
    require(text[span["start"]:span["end"]] == span["quote"], "evidence span round-trip failed")
    sample = {"b": 2, "a": "é"}
    require(digest_json(sample) == digest_json({"a": "é", "b": 2}), "canonical digest is not key-order stable")
    print(pretty_json({
        "valid": True,
        "dream_rows": len(context.source_rows),
        "theme_ids": list(context.theme_ids),
        "unicode_span": span,
    }), end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-a", type=Path, help="complete blind pass A JSON")
    parser.add_argument("--pass-b", type=Path, nargs="+", help="one or more blind pass B JSON batches")
    parser.add_argument("--adjudications", type=Path, help="optional adjudication decisions JSON")
    parser.add_argument("--comparison-output", type=Path, help="comparison or adjudication-packet JSON path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data",
        help="directory for dream_theme_assignments_v2.json and dream_theme_review_v2.json",
    )
    parser.add_argument("--self-test", action="store_true", help="run read-only internal/source checks and exit")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.self_test:
        require(args.pass_a is None and args.pass_b is None, "--self-test cannot be combined with pass inputs")
        self_test()
        return 0
    require(args.pass_a is not None, "--pass-a is required unless --self-test is used")
    require(args.pass_b, "--pass-b is required unless --self-test is used")

    context = load_context()
    pass_a_document = normalize_pass_files([args.pass_a], "pass-a", context)
    pass_b_document = normalize_pass_files(args.pass_b, "pass-b", context)
    require(
        pass_a_document["reviewer"]["reviewer_id"] != pass_b_document["reviewer"]["reviewer_id"],
        "blind passes must use different reviewer IDs",
    )
    comparison = compare_passes(pass_a_document, pass_b_document, context)
    comparison_path = args.comparison_output or args.output_dir / "dream_theme_v2_comparison.json"

    if args.adjudications is None and comparison["required_adjudications"]:
        packet = make_adjudication_packet(comparison, pass_a_document, pass_b_document, context)
        write_json_atomic(comparison_path, packet)
        print(
            f"validated both blind passes; {len(comparison['required_adjudications'])} rows require adjudication; "
            f"wrote source+pass-only packet to {comparison_path}",
            file=sys.stderr,
        )
        return 2

    adjudicator: dict[str, Any] | None = None
    adjudications: dict[tuple[str, str], dict[str, Any]] = {}
    if args.adjudications is not None:
        adjudicator, adjudications = normalize_adjudications(args.adjudications, context)

    assignments_document, review_document = finalize_documents(
        pass_a_document,
        pass_b_document,
        comparison,
        context,
        adjudicator,
        adjudications,
    )
    comparison_document = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "kind": "dream-theme-v2-comparison",
        "comparison": comparison,
        "adjudicated_row_count": len(adjudications),
    }
    write_json_atomic(comparison_path, comparison_document)
    write_json_atomic(args.output_dir / "dream_theme_assignments_v2.json", assignments_document)
    write_json_atomic(args.output_dir / "dream_theme_review_v2.json", review_document)
    print(
        f"wrote {args.output_dir / 'dream_theme_assignments_v2.json'} and "
        f"{args.output_dir / 'dream_theme_review_v2.json'}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
