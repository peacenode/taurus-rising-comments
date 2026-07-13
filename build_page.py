#!/usr/bin/env python3
"""Embed data/extracted.json into a self-contained index.html (inline Tailwind)."""
import base64
import csv
import hashlib
import html as html_lib
import json
import math
import re
from pathlib import Path

root = Path(__file__).parent

THEME_ID_ORDER = [
    "home-belonging",
    "cultivation",
    "service",
    "freedom",
    "stewardship",
    "self-sufficiency",
    "transmission",
]

DREAM_THEME_CHART_COLOR = "#e11d48"

DREAM_THEME_V2_SOURCE_DIGEST_ALGORITHM = "sha256-canonical-dreams-text-v1"
DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM = "sha256-canonical-json-v1"
DREAM_THEME_V2_REVIEW_METHOD = "two-full-coverage-independent-passes-with-calibrated-reconsideration"
DREAM_THEME_V2_EXPECTED_DREAM_ROWS = 238
DREAM_THEME_V2_EXPECTED_CALIBRATION_ROWS = 38
DREAM_THEME_V2_CALIBRATION_PROTOCOL_NOTE = "Calibration rows are excluded from blind agreement metrics."
DREAM_THEME_V2_TAXONOMY_SUPERSEDES = {
    "taxonomy_version": 1,
    "path": "data/dream_themes.json",
    "sha256": "331c0e69cd2aea44abf1b8bcc665093c258c0e50ceafa28fde3af7e3e4903590",
}
DREAM_THEME_V2_ASSIGNMENTS_SUPERSEDES = {
    "taxonomy_version": 1,
    "path": "data/dream_theme_assignments.json",
    "sha256": "eb82e7810938ef97e28097ed5bcfb21ba06ce26f12d61a7b60aa470b18b8766b",
}
DREAM_THEME_V2_REVIEW_SUPERSEDES = {
    "taxonomy_version": 1,
    "path": "data/dream_theme_review.json",
    "sha256": "404c2c00ce4348615c26d921fb9e7b443606972fc913bfdcd0438a663d3a9129",
}


def source_key(row):
    return row["username"], row["created_time"]


def dream_source_digest(row):
    canonical = json.dumps(
        {"dreams": row["dreams"], "text": row["text"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_json_digest(value):
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_dream_theme_summary(
    rows,
    project_root=None,
    *,
    taxonomy_path=None,
    assignments_path=None,
    review_path=None,
):
    """Validate reviewed theme data and return its public aggregate summary.

    ``project_root`` keeps normal project-relative behavior while the explicit
    paths allow isolated fixtures to exercise validation without touching the
    tracked data files.
    """
    project_root = Path(project_root) if project_root is not None else root
    taxonomy_path = Path(taxonomy_path) if taxonomy_path is not None else project_root / "data/dream_themes.json"
    assignments_path = Path(assignments_path) if assignments_path is not None else project_root / "data/dream_theme_assignments.json"
    review_path = Path(review_path) if review_path is not None else project_root / "data/dream_theme_review.json"

    taxonomy = json.loads(taxonomy_path.read_text())
    assignment_doc = json.loads(assignments_path.read_text())
    review = json.loads(review_path.read_text())

    if taxonomy.get("taxonomy_version") != 1:
        raise ValueError("Dream theme taxonomy_version must be 1")
    themes = taxonomy.get("themes", [])
    if [theme.get("id") for theme in themes] != THEME_ID_ORDER:
        raise ValueError("Dream themes must contain the seven IDs in taxonomy order")
    for index, theme in enumerate(themes, 1):
        if theme.get("order") != index:
            raise ValueError(f"Dream theme order is invalid for {theme.get('id')}")
        if not theme.get("label") or not theme.get("description") or not theme.get("classification_guidance"):
            raise ValueError(f"Dream theme copy is incomplete for {theme.get('id')}")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", theme.get("color", "")):
            raise ValueError(f"Dream theme color is invalid for {theme.get('id')}")

    if assignment_doc.get("taxonomy_version") != 1:
        raise ValueError("Dream assignment taxonomy_version must be 1")
    dream_rows = [row for row in rows if row.get("dreams")]
    source_by_key = {source_key(row): row for row in dream_rows}
    if len(source_by_key) != len(dream_rows):
        raise ValueError("Dream response identities are not unique")

    assignments = assignment_doc.get("assignments", [])
    assignment_by_key = {}
    for assignment in assignments:
        key = assignment.get("username"), assignment.get("created_time")
        if key in assignment_by_key:
            raise ValueError(f"Duplicate Dream assignment for {key[0]} at {key[1]}")
        source = source_by_key.get(key)
        if source is None:
            raise ValueError(f"Orphaned Dream assignment for {key[0]} at {key[1]}")
        if assignment.get("source_digest") != dream_source_digest(source):
            raise ValueError(f"Stale Dream assignment for {key[0]} at {key[1]}")
        if assignment.get("review_status") != "reviewed":
            raise ValueError(f"Unreviewed Dream assignment for {key[0]} at {key[1]}")
        theme_ids = assignment.get("theme_ids")
        if not isinstance(theme_ids, list) or len(theme_ids) != len(set(theme_ids)):
            raise ValueError(f"Invalid Dream theme list for {key[0]} at {key[1]}")
        if any(theme_id not in THEME_ID_ORDER for theme_id in theme_ids):
            raise ValueError(f"Unknown Dream theme for {key[0]} at {key[1]}")
        if theme_ids != sorted(theme_ids, key=THEME_ID_ORDER.index):
            raise ValueError(f"Dream themes are out of taxonomy order for {key[0]} at {key[1]}")
        assignment_by_key[key] = assignment

    missing = set(source_by_key) - set(assignment_by_key)
    if missing:
        username, created_time = sorted(missing)[0]
        raise ValueError(f"Missing Dream assignment for {username} at {created_time}")

    if review.get("taxonomy_version") != 1 or not review.get("all_disagreements_resolved"):
        raise ValueError("Dream theme secondary review is incomplete")
    if review.get("review_method") != "blind-independent-pass":
        raise ValueError("Dream theme review_method must be blind-independent-pass")
    if review.get("sample_rule") != (
        "sorted response keys where index % 5 == 0, plus every empty-theme "
        "and four-plus-theme assignment"
    ):
        raise ValueError("Dream theme sample_rule does not match the required review sample")
    sorted_keys = sorted(source_by_key)
    required_review_keys = {key for index, key in enumerate(sorted_keys) if index % 5 == 0}
    required_review_keys.update(
        key for key, assignment in assignment_by_key.items()
        if not assignment["theme_ids"] or len(assignment["theme_ids"]) >= 4
    )
    secondary_by_key = {}
    for secondary in review.get("secondary_reviews", []):
        key = secondary.get("username"), secondary.get("created_time")
        theme_ids = secondary.get("theme_ids")
        if key in secondary_by_key or key not in source_by_key:
            raise ValueError(f"Invalid secondary review identity for {key[0]} at {key[1]}")
        if not isinstance(theme_ids, list) or len(theme_ids) != len(set(theme_ids)):
            raise ValueError(f"Invalid secondary theme list for {key[0]} at {key[1]}")
        if any(theme_id not in THEME_ID_ORDER for theme_id in theme_ids):
            raise ValueError(f"Unknown secondary Dream theme for {key[0]} at {key[1]}")
        if theme_ids != sorted(theme_ids, key=THEME_ID_ORDER.index):
            raise ValueError(f"Secondary Dream themes are out of order for {key[0]} at {key[1]}")
        secondary_by_key[key] = secondary
    if set(secondary_by_key) != required_review_keys:
        raise ValueError("Dream theme secondary-review coverage does not match the required sample")

    resolution_by_key = {}
    for item in review.get("resolutions", []):
        key = item.get("username"), item.get("created_time")
        if key in resolution_by_key:
            raise ValueError(f"Duplicate Dream resolution for {key[0]} at {key[1]}")
        if key not in secondary_by_key:
            raise ValueError(f"Orphaned Dream resolution for {key[0]} at {key[1]}")
        resolution_by_key[key] = item
    for key, secondary in secondary_by_key.items():
        final_ids = assignment_by_key[key]["theme_ids"]
        secondary_ids = secondary_by_key[key]["theme_ids"]
        resolution = resolution_by_key.get(key)
        if resolution is None:
            if final_ids != secondary_ids:
                raise ValueError(f"Unresolved Dream theme disagreement for {key[0]} at {key[1]}")
            continue

        resolution_lists = {}
        for field in ("primary_theme_ids", "secondary_theme_ids", "resolved_theme_ids"):
            theme_ids = resolution.get(field)
            if not isinstance(theme_ids, list) or len(theme_ids) != len(set(theme_ids)):
                raise ValueError(f"Invalid {field} for {key[0]} at {key[1]}")
            if any(theme_id not in THEME_ID_ORDER for theme_id in theme_ids):
                raise ValueError(f"Unknown theme in {field} for {key[0]} at {key[1]}")
            if theme_ids != sorted(theme_ids, key=THEME_ID_ORDER.index):
                raise ValueError(f"Themes are out of order in {field} for {key[0]} at {key[1]}")
            resolution_lists[field] = theme_ids
        if resolution_lists["primary_theme_ids"] == resolution_lists["secondary_theme_ids"]:
            raise ValueError(f"Dream resolution does not record a disagreement for {key[0]} at {key[1]}")
        if resolution.get("secondary_theme_ids") != secondary_ids:
            raise ValueError(f"Resolution secondary themes do not match for {key[0]} at {key[1]}")
        if resolution.get("resolved_theme_ids") != final_ids:
            raise ValueError(f"Final Dream assignment does not match resolution for {key[0]} at {key[1]}")

    counts = {theme_id: 0 for theme_id in THEME_ID_ORDER}
    themed_response_count = 0
    for assignment in assignments:
        if assignment["theme_ids"]:
            themed_response_count += 1
        for theme_id in assignment["theme_ids"]:
            counts[theme_id] += 1
    total_theme_assignments = sum(counts.values())
    if total_theme_assignments == 0:
        raise ValueError("Dream theme assignments cannot total zero")

    public_themes = []
    for theme in themes:
        count = counts[theme["id"]]
        public_themes.append({
            "id": theme["id"],
            "label": theme["label"],
            "color": theme["color"],
            "description": theme["description"],
            "count": count,
            "percentage": count / total_theme_assignments * 100,
        })
    return {
        "taxonomy_version": 1,
        "reviewed_dream_count": len(dream_rows),
        "themed_response_count": themed_response_count,
        "total_theme_assignments": total_theme_assignments,
        "themes": public_themes,
    }


def _validate_dream_theme_classification_v2(
    classification,
    *,
    role,
    row,
    theme_order,
    taxonomy,
    label,
):
    if not isinstance(classification, dict):
        raise ValueError(f"{label} must be an object")
    allowed_fields = {"theme_id", "evidence_spans", "scores", "confidence", "supporting_reason"}
    if set(classification) - allowed_fields:
        raise ValueError(f"{label} has unknown fields")

    theme_id = classification.get("theme_id")
    if theme_id not in theme_order:
        raise ValueError(f"{label} has an unknown Dream theme")

    evidence_spans = classification.get("evidence_spans")
    if not isinstance(evidence_spans, list) or not evidence_spans:
        raise ValueError(f"{label} needs exact evidence spans")
    text = row["text"]
    for span in evidence_spans:
        if not isinstance(span, dict) or set(span) != {"field", "start", "end", "quote"}:
            raise ValueError(f"{label} has an invalid evidence span")
        start, end = span.get("start"), span.get("end")
        if (
            span.get("field") != "text"
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 0 <= start < end <= len(text)
            or text[start:end] != span.get("quote")
        ):
            raise ValueError(f"{label} evidence does not match the source text")

    dimension_ids = [item.get("id") for item in taxonomy.get("score_dimensions", [])]
    scores = classification.get("scores")
    if not isinstance(scores, dict) or set(scores) != {*dimension_ids, "total"}:
        raise ValueError(f"{label} has invalid score fields")
    score_scale = taxonomy["score_scale"]
    minimum = score_scale["minimum_per_dimension"]
    maximum = score_scale["maximum_per_dimension"]
    dimension_scores = []
    for dimension_id in dimension_ids:
        value = scores.get(dimension_id)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not minimum <= value <= maximum
        ):
            raise ValueError(f"{label} has an invalid {dimension_id} score")
        dimension_scores.append(value)
    total = scores.get("total")
    if not isinstance(total, int) or isinstance(total, bool) or total != sum(dimension_scores):
        raise ValueError(f"{label} score total is invalid")
    minimum_total = score_scale[f"{role.replace('-', '_')}_minimum_total"]
    if total < minimum_total:
        raise ValueError(f"{label} is below the {role} threshold")

    confidence = classification.get("confidence")
    if confidence not in taxonomy.get("confidence_values", []):
        raise ValueError(f"{label} has invalid confidence")
    if confidence == "high" and role == "primary" and total != 8:
        raise ValueError(f"{label} high-confidence primary must total 8")
    if confidence == "high" and role == "co-dominant" and total < 7:
        raise ValueError(f"{label} high-confidence co-dominant must total at least 7")

    if role == "supporting":
        if classification.get("supporting_reason") not in {
            "inferred", "means", "setting", "beneficiary", "consequence", "better-explained",
        }:
            raise ValueError(f"{label} has invalid supporting_reason")
    elif "supporting_reason" in classification:
        raise ValueError(f"{label} cannot have supporting_reason")
    return theme_id


def _validate_dream_theme_review_v2(
    review,
    *,
    assignments_by_key,
    source_by_key,
    taxonomy_digest,
    calibration_digest,
    calibration_keys,
):
    if not isinstance(review, dict):
        raise ValueError("Dream theme v2 review must be an object")
    if review.get("schema_version") != 2 or review.get("taxonomy_version") != 2:
        raise ValueError("Dream theme review schema and taxonomy versions must be 2")
    if (
        review.get("taxonomy_digest_algorithm") != DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM
        or review.get("taxonomy_digest") != taxonomy_digest
        or review.get("calibration_digest_algorithm") != DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM
        or review.get("calibration_digest") != calibration_digest
    ):
        raise ValueError("Dream theme v2 review taxonomy or calibration provenance is invalid")
    expected_manifest = [
        {"username": key[0], "created_time": key[1]}
        for key in sorted(calibration_keys)
    ]
    if review.get("calibration_identity_manifest") != expected_manifest:
        raise ValueError("Dream theme v2 review calibration identity manifest is invalid")
    if review.get("supersedes") != DREAM_THEME_V2_REVIEW_SUPERSEDES:
        raise ValueError("Dream theme review supersedes metadata is invalid")
    if review.get("review_method") != DREAM_THEME_V2_REVIEW_METHOD:
        raise ValueError("Dream theme v2 review_method is invalid")
    if review.get("source_digest_algorithm") != DREAM_THEME_V2_SOURCE_DIGEST_ALGORITHM:
        raise ValueError("Dream theme v2 review source digest algorithm is invalid")
    if review.get("judgment_digest_algorithm") != DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM:
        raise ValueError("Dream theme v2 judgment digest algorithm is invalid")
    if review.get("source_row_count") != len(source_by_key):
        raise ValueError("Dream theme v2 review source_row_count is stale")
    if review.get("all_required_adjudications_complete") is not True:
        raise ValueError("Dream theme v2 required adjudications are incomplete")

    blind_passes = review.get("blind_passes")
    if not isinstance(blind_passes, list) or len(blind_passes) != 2:
        raise ValueError("Dream theme v2 review needs two full independent passes")
    pass_assignment_maps = {}
    reviewer_ids = []
    for blind_pass in blind_passes:
        if not isinstance(blind_pass, dict):
            raise ValueError("Dream theme v2 independent pass must be an object")
        pass_id = blind_pass.get("pass_id")
        if pass_id not in {"pass-a", "pass-b"} or pass_id in pass_assignment_maps:
            raise ValueError("Dream theme v2 blind pass IDs must be pass-a and pass-b")
        if blind_pass.get("schema_version") != 2 or blind_pass.get("taxonomy_version") != 2:
            raise ValueError(f"{pass_id} has invalid version metadata")
        reviewer = blind_pass.get("reviewer")
        if not isinstance(reviewer, dict) or not all(
            isinstance(reviewer.get(field), str) and reviewer[field].strip()
            for field in ("reviewer_id", "kind", "prompt_version")
        ):
            raise ValueError(f"{pass_id} reviewer metadata is invalid")
        reviewer_ids.append(reviewer["reviewer_id"])
        pass_assignments = blind_pass.get("assignments")
        if not isinstance(pass_assignments, list):
            raise ValueError(f"{pass_id} assignments must be an array")
        assignment_map = {}
        for item in pass_assignments:
            if not isinstance(item, dict):
                raise ValueError(f"{pass_id} assignment must be an object")
            key = item.get("username"), item.get("created_time")
            if key not in source_by_key or key in assignment_map:
                raise ValueError(f"{pass_id} assignment coverage is invalid")
            assignment_map[key] = item
        if set(assignment_map) != set(source_by_key):
            raise ValueError(f"{pass_id} must cover every Dream response exactly once")
        pass_assignment_maps[pass_id] = assignment_map
    if len(set(reviewer_ids)) != 2:
        raise ValueError("Dream theme independent passes must use different reviewers")

    def pass_public_signature(item, label):
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object")
        primary = item.get("primary")
        if primary is not None and not isinstance(primary, dict):
            raise ValueError(f"{label} primary must be an object or null")
        co_dominant = item.get("co_dominant")
        if not isinstance(co_dominant, list) or not all(
            isinstance(classification, dict) for classification in co_dominant
        ):
            raise ValueError(f"{label} co_dominant must be an array of objects")
        primary_id = primary.get("theme_id") if primary else None
        co_dominant_ids = frozenset(
            classification.get("theme_id") for classification in co_dominant
        )
        public_items = ([primary] if primary else []) + co_dominant
        return primary_id, co_dominant_ids, public_items

    computed_required_by_key = {}
    for key in source_by_key:
        pass_a = pass_assignment_maps["pass-a"][key]
        pass_b = pass_assignment_maps["pass-b"][key]
        expected_source_digest = dream_source_digest(source_by_key[key])
        if (
            pass_a.get("source_digest") != expected_source_digest
            or pass_b.get("source_digest") != expected_source_digest
        ):
            raise ValueError("Dream theme v2 pass source digest is stale")
        a_primary, a_co_dominant, a_public = pass_public_signature(
            pass_a, f"pass-a assignment for {key[0]} at {key[1]}"
        )
        b_primary, b_co_dominant, b_public = pass_public_signature(
            pass_b, f"pass-b assignment for {key[0]} at {key[1]}"
        )
        reasons = []
        if a_primary != b_primary or a_co_dominant != b_co_dominant:
            reasons.append("public-role-disagreement")
        if any(item.get("confidence") == "low" for item in a_public + b_public):
            reasons.append("public-low-confidence")
        if len(a_public) == 3 or len(b_public) == 3:
            reasons.append("three-public-themes")
        if reasons:
            computed_required_by_key[key] = reasons

    if len(source_by_key) == DREAM_THEME_V2_EXPECTED_DREAM_ROWS:
        reconsideration = review.get("calibrated_reconsideration")
        if not isinstance(reconsideration, dict):
            raise ValueError("Dream theme v2 review is missing calibrated reconsideration provenance")
        if reconsideration.get("method") != (
            "targeted-calibrated-reconsideration-of-baseline-public-role-disagreements"
        ):
            raise ValueError("Dream theme v2 reconsideration method is invalid")
        baseline_pass_b = reconsideration.get("baseline_pass_b")
        if not isinstance(baseline_pass_b, dict):
            raise ValueError("Dream theme v2 baseline pass B is invalid")
        if reconsideration.get("baseline_pass_b_digest") != canonical_json_digest(baseline_pass_b):
            raise ValueError("Dream theme v2 baseline pass B digest does not match")
        calibrated_pass_b = next(
            item for item in blind_passes if item["pass_id"] == "pass-b"
        )
        if reconsideration.get("calibrated_pass_b_digest") != canonical_json_digest(calibrated_pass_b):
            raise ValueError("Dream theme v2 calibrated pass B digest does not match")
        baseline_reviewer = baseline_pass_b.get("reviewer")
        if (
            not isinstance(baseline_reviewer, dict)
            or baseline_reviewer.get("reviewer_id") != calibrated_pass_b["reviewer"]["reviewer_id"]
            or baseline_reviewer.get("kind") != calibrated_pass_b["reviewer"]["kind"]
        ):
            raise ValueError("Dream theme v2 baseline and calibrated pass B reviewers do not match")
        baseline_items = baseline_pass_b.get("assignments")
        if not isinstance(baseline_items, list):
            raise ValueError("Dream theme v2 baseline pass B assignments are invalid")
        baseline_map = {}
        for item in baseline_items:
            if not isinstance(item, dict):
                raise ValueError("Dream theme v2 baseline pass B assignment is invalid")
            key = item.get("username"), item.get("created_time")
            if key not in source_by_key or key in baseline_map:
                raise ValueError("Dream theme v2 baseline pass B coverage is invalid")
            if item.get("source_digest") != dream_source_digest(source_by_key[key]):
                raise ValueError("Dream theme v2 baseline pass B source digest is stale")
            baseline_map[key] = item
        if set(baseline_map) != set(source_by_key):
            raise ValueError("Dream theme v2 baseline pass B must cover every Dream response")

        expected_reconsidered = {
            key
            for key in source_by_key
            if pass_public_signature(
                pass_assignment_maps["pass-a"][key],
                f"pass-a assignment for {key[0]} at {key[1]}",
            )[:2]
            != pass_public_signature(
                baseline_map[key],
                f"baseline pass-b assignment for {key[0]} at {key[1]}",
            )[:2]
        }

        def manifest_keys(value, label):
            if not isinstance(value, list):
                raise ValueError(f"{label} must be an array")
            result = []
            for item in value:
                if not isinstance(item, dict) or set(item) != {"username", "created_time"}:
                    raise ValueError(f"{label} has an invalid identity")
                result.append((item["username"], item["created_time"]))
            if len(result) != len(set(result)):
                raise ValueError(f"{label} repeats an identity")
            return set(result)

        reconsidered_keys = manifest_keys(
            reconsideration.get("reconsidered_identity_manifest"),
            "Dream theme v2 reconsidered identity manifest",
        )
        if reconsidered_keys != expected_reconsidered:
            raise ValueError("Dream theme v2 reconsidered identities do not match baseline disagreements")
        changed_keys = {
            key
            for key in source_by_key
            if canonical_json_digest(baseline_map[key])
            != canonical_json_digest(pass_assignment_maps["pass-b"][key])
        }
        declared_changed_keys = manifest_keys(
            reconsideration.get("changed_identity_manifest"),
            "Dream theme v2 changed identity manifest",
        )
        if changed_keys != declared_changed_keys or not changed_keys <= reconsidered_keys:
            raise ValueError("Dream theme v2 calibrated pass B changes are not auditable")
        if (
            reconsideration.get("reconsidered_row_count") != len(reconsidered_keys)
            or reconsideration.get("changed_row_count") != len(changed_keys)
        ):
            raise ValueError("Dream theme v2 reconsideration counts are invalid")

    comparison = review.get("comparison")
    if not isinstance(comparison, dict) or comparison.get("row_count") != len(source_by_key):
        raise ValueError("Dream theme v2 comparison coverage is invalid")
    if len(source_by_key) == DREAM_THEME_V2_EXPECTED_DREAM_ROWS and (
        comparison.get("calibration_row_count") != DREAM_THEME_V2_EXPECTED_CALIBRATION_ROWS
        or comparison.get("evaluation_row_count")
        != len(source_by_key) - DREAM_THEME_V2_EXPECTED_CALIBRATION_ROWS
    ):
        raise ValueError("Dream theme v2 comparison calibration split is invalid")
    if (
        len(source_by_key) == DREAM_THEME_V2_EXPECTED_DREAM_ROWS
        and (
            not isinstance(comparison.get("release_gate"), dict)
            or comparison["release_gate"].get("passed") is not True
            or comparison["release_gate"].get("failed") != []
        )
    ):
        raise ValueError("Dream theme v2 agreement release gate did not pass")
    required_items = comparison.get("required_adjudications")
    if not isinstance(required_items, list):
        raise ValueError("Dream theme v2 required_adjudications must be an array")
    required_by_key = {}
    allowed_reasons = {
        "public-role-disagreement",
        "public-low-confidence",
        "three-public-themes",
        "calibration-anchor-mismatch",
    }
    for item in required_items:
        if not isinstance(item, dict):
            raise ValueError("Dream theme v2 required adjudication is invalid")
        key = item.get("username"), item.get("created_time")
        reasons = item.get("reasons")
        if key not in source_by_key or key in required_by_key or not isinstance(reasons, list) or not reasons:
            raise ValueError("Dream theme v2 required adjudication coverage is invalid")
        if len(reasons) != len(set(reasons)) or not set(reasons) <= allowed_reasons:
            raise ValueError("Dream theme v2 required adjudication reasons are invalid")
        required_by_key[key] = reasons

    for key, computed_reasons in computed_required_by_key.items():
        if not set(computed_reasons) <= set(required_by_key.get(key, [])):
            raise ValueError("Dream theme v2 comparison omits a required public-role adjudication")

    expected_adjudicated = {
        key for key, assignment in assignments_by_key.items()
        if assignment.get("review_status") == "adjudicated"
    }
    if set(required_by_key) != expected_adjudicated:
        raise ValueError("Dream theme v2 adjudicated assignments do not match the comparison")
    for key, final in assignments_by_key.items():
        if key in required_by_key:
            continue
        pass_a_signature = pass_public_signature(
            pass_assignment_maps["pass-a"][key],
            f"pass-a assignment for {key[0]} at {key[1]}",
        )[:2]
        pass_b_signature = pass_public_signature(
            pass_assignment_maps["pass-b"][key],
            f"pass-b assignment for {key[0]} at {key[1]}",
        )[:2]
        final_signature = pass_public_signature(
            final, f"final assignment for {key[0]} at {key[1]}"
        )[:2]
        if pass_a_signature != pass_b_signature or final_signature != pass_a_signature:
            raise ValueError("Dream theme v2 agreement row does not match both independent passes")

    resolutions = review.get("resolutions")
    if not isinstance(resolutions, list):
        raise ValueError("Dream theme v2 resolutions must be an array")
    resolutions_by_key = {}
    for resolution in resolutions:
        if not isinstance(resolution, dict):
            raise ValueError("Dream theme v2 resolution must be an object")
        key = resolution.get("username"), resolution.get("created_time")
        if key not in assignments_by_key or key in resolutions_by_key:
            raise ValueError("Dream theme v2 resolution identity is invalid")
        assignment = assignments_by_key[key]
        if resolution.get("decision") != assignment["review_status"]:
            raise ValueError("Dream theme v2 resolution decision does not match its assignment")
        if resolution.get("required_reasons") != required_by_key.get(key, []):
            raise ValueError("Dream theme v2 resolution reasons do not match the comparison")
        if resolution.get("adjudication_id") != assignment.get("adjudication_id"):
            raise ValueError("Dream theme v2 resolution adjudication ID does not match")
        if resolution.get("final_assignment_digest") != canonical_json_digest(assignment):
            raise ValueError("Dream theme v2 final assignment digest does not match")
        for pass_id in ("pass-a", "pass-b"):
            digest_field = f"{pass_id.replace('-', '_')}_judgment_digest"
            if resolution.get(digest_field) != canonical_json_digest(pass_assignment_maps[pass_id][key]):
                raise ValueError(f"Dream theme v2 {pass_id} judgment digest does not match")
        resolutions_by_key[key] = resolution
    if set(resolutions_by_key) != set(source_by_key):
        raise ValueError("Dream theme v2 resolutions must cover every Dream response")

    adjudications = review.get("adjudications")
    if not isinstance(adjudications, list):
        raise ValueError("Dream theme v2 adjudications must be an array")
    adjudications_by_key = {}
    for adjudication in adjudications:
        if not isinstance(adjudication, dict):
            raise ValueError("Dream theme v2 adjudication must be an object")
        key = adjudication.get("username"), adjudication.get("created_time")
        if key not in expected_adjudicated or key in adjudications_by_key:
            raise ValueError("Dream theme v2 adjudication identity is invalid")
        assignment = assignments_by_key[key]
        if (
            adjudication.get("adjudication_id") != assignment.get("adjudication_id")
            or adjudication.get("source_digest") != assignment.get("source_digest")
            or adjudication.get("required_reasons") != required_by_key[key]
            or adjudication.get("final_assignment_digest") != canonical_json_digest(assignment)
        ):
            raise ValueError("Dream theme v2 adjudication does not match its assignment")
        digest_payload = {field: value for field, value in adjudication.items() if field != "adjudication_digest"}
        if adjudication.get("adjudication_digest") != canonical_json_digest(digest_payload):
            raise ValueError("Dream theme v2 adjudication digest does not match")
        adjudications_by_key[key] = adjudication
    if set(adjudications_by_key) != expected_adjudicated:
        raise ValueError("Dream theme v2 adjudications do not cover every required row")
    if expected_adjudicated:
        adjudicator = review.get("adjudicator")
        if not isinstance(adjudicator, dict) or not all(
            isinstance(adjudicator.get(field), str) and adjudicator[field].strip()
            for field in ("reviewer_id", "kind", "prompt_version")
        ):
            raise ValueError("Dream theme v2 adjudicator metadata is invalid")
        if adjudicator["reviewer_id"] in reviewer_ids:
            raise ValueError("Dream theme v2 adjudicator must be independent from both pass reviewers")


def load_dream_theme_summary_v2(
    rows,
    project_root=None,
    *,
    taxonomy_path=None,
    calibration_path=None,
    assignments_path=None,
    review_path=None,
):
    """Validate Dream theme v2 data and return its public-only projection.

    Primary themes alone supply the pie denominator and counts. The response
    projection includes the primary followed by public co-dominants; rubric
    scores, evidence, supporting themes, and review metadata never leave this
    loader.
    """
    project_root = Path(project_root) if project_root is not None else root
    taxonomy_path = Path(taxonomy_path) if taxonomy_path is not None else project_root / "data/dream_themes_v2.json"
    calibration_path = Path(calibration_path) if calibration_path is not None else project_root / "data/dream_theme_calibration_v2.json"
    assignments_path = Path(assignments_path) if assignments_path is not None else project_root / "data/dream_theme_assignments_v2.json"
    review_path = Path(review_path) if review_path is not None else project_root / "data/dream_theme_review_v2.json"

    taxonomy = json.loads(taxonomy_path.read_text())
    calibration = json.loads(calibration_path.read_text())
    assignment_doc = json.loads(assignments_path.read_text())
    review = json.loads(review_path.read_text())

    if taxonomy.get("schema_version") != 2 or taxonomy.get("taxonomy_version") != 2:
        raise ValueError("Dream theme taxonomy schema and taxonomy versions must be 2")
    if taxonomy.get("supersedes") != DREAM_THEME_V2_TAXONOMY_SUPERSEDES:
        raise ValueError("Dream theme taxonomy supersedes metadata is invalid")
    taxonomy_digest = canonical_json_digest(taxonomy)
    if (
        not isinstance(calibration, dict)
        or calibration.get("schema_version") != 2
        or calibration.get("taxonomy_version") != 2
        or calibration.get("protocol_note") != DREAM_THEME_V2_CALIBRATION_PROTOCOL_NOTE
        or not isinstance(calibration.get("rows"), list)
        or len(calibration["rows"]) != DREAM_THEME_V2_EXPECTED_CALIBRATION_ROWS
    ):
        raise ValueError("Dream theme v2 calibration corpus is invalid")
    calibration_keys = {
        (item.get("username"), item.get("created_time"))
        for item in calibration["rows"]
        if isinstance(item, dict)
    }
    if len(calibration_keys) != DREAM_THEME_V2_EXPECTED_CALIBRATION_ROWS or any(
        not isinstance(username, str)
        or not username
        or not isinstance(created_time, str)
        or not created_time
        for username, created_time in calibration_keys
    ):
        raise ValueError("Dream theme v2 calibration identities are invalid")
    calibration_digest = canonical_json_digest(calibration)
    themes = taxonomy.get("themes")
    if not isinstance(themes, list) or [theme.get("id") for theme in themes] != THEME_ID_ORDER:
        raise ValueError("Dream themes must contain the seven IDs in taxonomy order")
    for index, theme in enumerate(themes, 1):
        if theme.get("order") != index:
            raise ValueError(f"Dream theme order is invalid for {theme.get('id')}")
        if not theme.get("label") or not theme.get("description") or not theme.get("classification_guidance"):
            raise ValueError(f"Dream theme copy is incomplete for {theme.get('id')}")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", theme.get("color", "")):
            raise ValueError(f"Dream theme color is invalid for {theme.get('id')}")

    roles = taxonomy.get("roles")
    if not isinstance(roles, list) or [role.get("id") for role in roles] != [
        "primary", "co-dominant", "supporting",
    ]:
        raise ValueError("Dream theme roles are incomplete or out of order")
    expected_role_behavior = {
        "primary": (True, True, True, 1),
        "co-dominant": (True, True, False, 2),
        "supporting": (False, False, False, None),
    }
    for role in roles:
        expected = expected_role_behavior[role["id"]]
        actual = (
            role.get("public"),
            role.get("display_on_response"),
            role.get("counts_in_pie"),
            role.get("maximum_per_response"),
        )
        if actual != expected:
            raise ValueError(f"Dream theme role behavior is invalid for {role['id']}")

    dimensions = taxonomy.get("score_dimensions")
    if not isinstance(dimensions, list) or [item.get("id") for item in dimensions] != [
        "explicit_support", "centrality", "standalone", "specificity",
    ]:
        raise ValueError("Dream theme score dimensions are invalid")
    score_scale = taxonomy.get("score_scale")
    if not isinstance(score_scale, dict) or not all(
        isinstance(score_scale.get(field), int)
        for field in (
            "minimum_per_dimension", "maximum_per_dimension", "primary_minimum_total",
            "co_dominant_minimum_total", "supporting_minimum_total",
        )
    ):
        raise ValueError("Dream theme score scale is invalid")
    if set(taxonomy.get("confidence_values", [])) != {"high", "medium", "low"}:
        raise ValueError("Dream theme confidence values are invalid")

    dream_rows = [row for row in rows if isinstance(row.get("dreams"), str) and row["dreams"]]
    source_by_key = {source_key(row): row for row in dream_rows}
    if len(source_by_key) != len(dream_rows):
        raise ValueError("Dream response identities are not unique")
    for row in dream_rows:
        if not isinstance(row.get("text"), str):
            raise ValueError("Dream response text must be a string")
    if len(dream_rows) == DREAM_THEME_V2_EXPECTED_DREAM_ROWS:
        if not calibration_keys <= set(source_by_key):
            raise ValueError("Dream theme v2 calibration identities are stale")
        for anchor in calibration["rows"]:
            key = anchor["username"], anchor["created_time"]
            quotes = anchor.get("evidence_quotes")
            if not isinstance(quotes, list) or not quotes or not all(
                isinstance(quote, str) and quote in source_by_key[key]["text"]
                for quote in quotes
            ):
                raise ValueError("Dream theme v2 calibration evidence is stale")

    if assignment_doc.get("schema_version") != 2 or assignment_doc.get("taxonomy_version") != 2:
        raise ValueError("Dream assignment schema and taxonomy versions must be 2")
    if (
        assignment_doc.get("taxonomy_digest_algorithm") != DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM
        or assignment_doc.get("taxonomy_digest") != taxonomy_digest
        or assignment_doc.get("calibration_digest_algorithm") != DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM
        or assignment_doc.get("calibration_digest") != calibration_digest
    ):
        raise ValueError("Dream assignment taxonomy or calibration provenance is invalid")
    if assignment_doc.get("supersedes") != DREAM_THEME_V2_ASSIGNMENTS_SUPERSEDES:
        raise ValueError("Dream assignment supersedes metadata is invalid")
    if assignment_doc.get("source_digest_algorithm") != DREAM_THEME_V2_SOURCE_DIGEST_ALGORITHM:
        raise ValueError("Dream assignment source digest algorithm is invalid")
    if assignment_doc.get("source_row_count") != len(dream_rows):
        raise ValueError("Dream assignment source_row_count is stale")

    assignments = assignment_doc.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("Dream theme v2 assignments must be an array")
    theme_order = {theme_id: index for index, theme_id in enumerate(THEME_ID_ORDER)}
    assignments_by_key = {}
    public_assignments = []
    primary_counts = {theme_id: 0 for theme_id in THEME_ID_ORDER}
    for assignment in assignments:
        if not isinstance(assignment, dict):
            raise ValueError("Dream theme v2 assignment must be an object")
        key = assignment.get("username"), assignment.get("created_time")
        if key not in source_by_key or key in assignments_by_key:
            raise ValueError("Dream theme v2 assignment identity is invalid")
        row = source_by_key[key]
        if assignment.get("source_digest") != dream_source_digest(row):
            raise ValueError(f"Stale Dream assignment for {key[0]} at {key[1]}")
        review_status = assignment.get("review_status")
        adjudication_id = assignment.get("adjudication_id")
        if review_status not in {"blind-public-role-agreement", "adjudicated"}:
            raise ValueError(f"Invalid Dream review status for {key[0]} at {key[1]}")
        if (
            (review_status == "adjudicated" and not (
                isinstance(adjudication_id, str) and adjudication_id
            ))
            or (review_status == "blind-public-role-agreement" and adjudication_id is not None)
        ):
            raise ValueError(f"Invalid Dream adjudication ID for {key[0]} at {key[1]}")

        status = assignment.get("public_status")
        primary = assignment.get("primary")
        co_dominant = assignment.get("co_dominant")
        supporting = assignment.get("supporting")
        rejected = assignment.get("rejected_candidates")
        if status not in {"themed", "unthemed"}:
            raise ValueError(f"Invalid Dream public status for {key[0]} at {key[1]}")
        if not isinstance(co_dominant, list) or len(co_dominant) > 2:
            raise ValueError(f"Invalid Dream co-dominant list for {key[0]} at {key[1]}")
        if not isinstance(supporting, list) or not isinstance(rejected, list):
            raise ValueError(f"Invalid private Dream theme data for {key[0]} at {key[1]}")

        primary_id = None
        classified = []
        if primary is not None:
            primary_id = _validate_dream_theme_classification_v2(
                primary,
                role="primary",
                row=row,
                theme_order=theme_order,
                taxonomy=taxonomy,
                label=f"Dream primary for {key[0]} at {key[1]}",
            )
            classified.append(("primary", primary))
        co_ids = []
        for index, item in enumerate(co_dominant):
            theme_id = _validate_dream_theme_classification_v2(
                item,
                role="co-dominant",
                row=row,
                theme_order=theme_order,
                taxonomy=taxonomy,
                label=f"Dream co-dominant[{index}] for {key[0]} at {key[1]}",
            )
            co_ids.append(theme_id)
            classified.append(("co-dominant", item))
        supporting_ids = []
        for index, item in enumerate(supporting):
            supporting_ids.append(_validate_dream_theme_classification_v2(
                item,
                role="supporting",
                row=row,
                theme_order=theme_order,
                taxonomy=taxonomy,
                label=f"Dream supporting[{index}] for {key[0]} at {key[1]}",
            ))
        rejected_ids = []
        for item in rejected:
            if not isinstance(item, dict) or item.get("theme_id") not in theme_order:
                raise ValueError(f"Invalid rejected Dream candidate for {key[0]} at {key[1]}")
            rejected_ids.append(item["theme_id"])

        if status == "themed":
            if primary_id is None or assignment.get("unthemed_reason") is not None:
                raise ValueError(f"Themed Dream response needs one primary for {key[0]} at {key[1]}")
        elif (
            primary_id is not None
            or co_ids
            or not isinstance(assignment.get("unthemed_reason"), str)
            or not assignment["unthemed_reason"].strip()
        ):
            raise ValueError(f"Unthemed Dream response has public themes for {key[0]} at {key[1]}")
        if co_ids != sorted(co_ids, key=theme_order.get):
            raise ValueError(f"Dream co-dominants are out of taxonomy order for {key[0]} at {key[1]}")
        if primary is not None and any(
            not primary["scores"]["total"] - 1 <= item["scores"]["total"] <= primary["scores"]["total"]
            for item in co_dominant
        ):
            raise ValueError(f"Dream co-dominant score is not comparable to primary for {key[0]} at {key[1]}")
        all_ids = ([primary_id] if primary_id else []) + co_ids + supporting_ids + rejected_ids
        if len(all_ids) != len(set(all_ids)):
            raise ValueError(f"Dream theme is classified more than once for {key[0]} at {key[1]}")
        public_classifications = [item for role, item in classified if role in {"primary", "co-dominant"}]
        if len(public_classifications) == 3 and any(
            item["scores"]["total"] < 7 for item in public_classifications
        ):
            raise ValueError(f"Three public Dream themes require scores of 7 for {key[0]} at {key[1]}")
        if (len(public_classifications) == 3 or any(item["confidence"] == "low" for item in public_classifications)) and review_status != "adjudicated":
            raise ValueError(f"Exceptional public Dream themes require adjudication for {key[0]} at {key[1]}")

        public_theme_ids = ([primary_id] if primary_id else []) + co_ids
        if primary_id:
            primary_counts[primary_id] += 1
        public_assignments.append({
            "username": key[0],
            "created_time": key[1],
            "dream_primary_theme_id": primary_id,
            "dream_theme_ids": public_theme_ids,
        })
        assignments_by_key[key] = assignment

    if set(assignments_by_key) != set(source_by_key):
        raise ValueError("Dream theme v2 assignments must cover every Dream response exactly once")

    _validate_dream_theme_review_v2(
        review,
        assignments_by_key=assignments_by_key,
        source_by_key=source_by_key,
        taxonomy_digest=taxonomy_digest,
        calibration_digest=calibration_digest,
        calibration_keys=calibration_keys,
    )

    themed_response_count = sum(primary_counts.values())
    if themed_response_count == 0:
        raise ValueError("Dream theme primary responses cannot total zero")
    public_themes = []
    for theme in themes:
        count = primary_counts[theme["id"]]
        public_themes.append({
            "id": theme["id"],
            "label": theme["label"],
            "color": theme["color"],
            "description": theme["description"],
            "count": count,
            "percentage": count / themed_response_count * 100,
        })
    return {
        "taxonomy_version": 2,
        "reviewed_dream_count": len(dream_rows),
        "themed_response_count": themed_response_count,
        "total_primary_responses": themed_response_count,
        "themes": public_themes,
        "public_assignments": public_assignments,
    }


def render_dream_theme_pie(summary):
    center = 160
    radius = 106
    label_radius = radius + 20
    angle = -90.0
    paths = []
    markers = []
    denominator = summary.get("total_primary_responses")
    if denominator is None:
        denominator = summary["total_theme_assignments"]

    ordered_themes = sorted(
        summary["themes"],
        key=lambda theme: (theme["count"], THEME_ID_ORDER.index(theme["id"])),
    )
    opacity_by_theme = {
        theme["id"]: (
            1.0
            if len(ordered_themes) == 1
            else 0.1 + 0.9 * index / (len(ordered_themes) - 1)
        )
        for index, theme in enumerate(ordered_themes)
    }

    def point(degrees, distance):
        radians = math.radians(degrees)
        return center + distance * math.cos(radians), center + distance * math.sin(radians)

    nonzero = [theme for theme in ordered_themes if theme["count"]]
    for theme in ordered_themes:
        count = theme["count"]
        if not count:
            continue
        opacity = opacity_by_theme[theme["id"]]
        sweep = count / denominator * 360
        end = angle + sweep
        label = html_lib.escape(theme["label"])
        percent = theme["percentage"]
        percent_text = "0%" if percent == 0 else f"{percent:.1f}%"
        response_word = "response" if count == 1 else "responses"
        title = html_lib.escape(
            f"{theme['label']}: {count} primary {response_word}, {percent_text}"
        )
        theme_id = html_lib.escape(theme["id"])
        interaction_attrs = (
            f'class="dream-theme-slice cursor-pointer transition-opacity duration-150 focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-600 [-webkit-tap-highlight-color:transparent]" '
            f'data-dream-theme="{theme_id}" data-chart-opacity="{opacity:.3f}" '
            'role="button" tabindex="0" '
            f'aria-label="Select primary theme {label}: {percent_text}, {count} primary {response_word}" '
            'aria-pressed="false" aria-controls="list"'
        )
        if len(nonzero) == 1:
            path_markup = (
                f'<circle cx="{center}" cy="{center}" r="{radius}" fill="{DREAM_THEME_CHART_COLOR}" '
                f'fill-opacity="{opacity:.3f}" '
                f'stroke="#ffffff" stroke-width="2" {interaction_attrs}>'
                f'<title>{title}</title></circle>'
            )
        else:
            x1, y1 = point(angle, radius)
            x2, y2 = point(end, radius)
            large_arc = 1 if sweep > 180 else 0
            path_markup = (
                f'<path d="M {center} {center} L {x1:.3f} {y1:.3f} '
                f'A {radius} {radius} 0 {large_arc} 1 {x2:.3f} {y2:.3f} Z" '
                f'fill="{DREAM_THEME_CHART_COLOR}" fill-opacity="{opacity:.3f}" '
                f'stroke="#ffffff" stroke-width="2" {interaction_attrs}>'
                f'<title>{title}</title></path>'
            )
        paths.append(path_markup)

        middle = angle + sweep / 2
        marker_x, marker_y = point(middle, label_radius)
        horizontal_direction = math.cos(math.radians(middle))
        text_anchor = (
            "middle"
            if abs(horizontal_direction) < 0.15
            else "start" if horizontal_direction > 0 else "end"
        )
        markers.append(
            f'<text x="{marker_x:.3f}" y="{marker_y + 0.5:.3f}" text-anchor="{text_anchor}" '
            'dominant-baseline="middle" fill="#000000" fill-opacity="0.5" '
            f'data-dream-theme-percent="{theme_id}" data-chart-text-color="#000000" '
            'font-size="11" font-weight="600" '
            f'class="dream-theme-percent" aria-hidden="true" pointer-events="none">{percent_text}</text>'
        )
        angle = end

    legend = []
    for theme in ordered_themes:
        label = html_lib.escape(theme["label"])
        description = html_lib.escape(theme["description"])
        theme_id = html_lib.escape(theme["id"])
        percent = theme["percentage"]
        percent_text = "0%" if percent == 0 else f"{percent:.1f}%"
        legend.append(f'''
        <li class="py-1">
          <button type="button" data-dream-theme="{theme_id}" aria-pressed="false" aria-controls="list"
            class="dream-theme-option w-full rounded-lg px-2 py-3 text-left transition-colors hover:bg-neutral-950/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-neutral-400 aria-pressed:bg-neutral-950/[0.04]">
            <span class="block text-sm font-medium">{label} <span class="text-neutral-950/50">{percent_text}</span></span>
            <span class="mt-1 block text-xs leading-relaxed text-neutral-500">{description}</span>
          </button>
        </li>''')

    return f'''
  <section id="dream-themes" class="mt-16 pt-12">
    <div class="mx-auto max-w-prose text-center">
      <h2 class="font-serif text-2xl font-normal tracking-tight">Themes</h2>
      <p class="mt-2 text-sm text-neutral-500 text-balance">Primary themes across Dream responses. Select a theme or pie slice to show responses where it is primary. Themes on each response are listed primary first, followed by any co-dominant themes.</p>
    </div>
    <div class="mt-8 grid items-start gap-8 md:grid-cols-[minmax(0,20rem)_1fr] md:gap-10">
      <div class="mx-auto w-full max-w-xs">
        <svg viewBox="0 0 320 320" role="group" aria-labelledby="dream-pie-title dream-pie-desc" class="block h-auto w-full overflow-visible">
          <title id="dream-pie-title">Primary Dream theme distribution</title>
          <desc id="dream-pie-desc">A seven-part interactive pie chart of primary themes, ordered from the smallest, lightest group to the largest, darkest group. Each exact percentage begins just outside its slice. Select a slice to filter responses whose primary theme matches it; co-dominant themes remain listed on each response.</desc>
          {''.join(paths)}
          {''.join(markers)}
        </svg>
      </div>
      <ol class="min-w-0">{''.join(legend)}
      </ol>
    </div>
  </section>'''


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Taurus Dreamscapes</title>
<meta name="description" content="__DESC__">
<link rel="icon" type="image/png" href="favicon.png">
<link rel="apple-touch-icon" href="favicon.png">

<meta property="og:type" content="website">
<meta property="og:title" content="Taurus Dreamscapes">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__SITE__/">
<meta property="og:image" content="__SITE__/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Taurus Dreamscapes">
<meta name="twitter:description" content="__DESC__">
<meta name="twitter:image" content="__SITE__/og.png">

<link rel="preconnect" href="https://rsms.me/">
<link rel="stylesheet" href="https://rsms.me/inter/inter.css">
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: { extend: {
    fontFamily: {
      sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      serif: ['"Times New Roman"', 'Times', 'serif'],
    },
    colors: {
      venus: '#D6455B',   // coral-pink, pulled warm off the dress
      node: '#0E8074',    // deep teal, between the sea and the sash
      saturn: '#B07D12',  // gold, off the ointment jar
    },
  } }
}
</script>
</head>
<body class="font-sans antialiased bg-white text-neutral-900">
<div class="max-w-4xl mx-auto px-5 py-8 sm:px-8 sm:py-12">

  <header class="text-center">
    <a href="https://communionarchive.substack.com/" class="inline-block">
      __COMMUNION_LOGO__
    </a>
    <h1 class="mt-4 font-serif text-3xl sm:text-4xl font-normal tracking-tighter text-balance">Taurus Dreamscapes</h1>
    <p class="mt-2.5 text-sm font-medium">
      <a class="inline-flex items-center gap-1.5" href="https://www.tiktok.com/@thebaileygrind_/video/7660139501171395853">
        <svg viewBox="0 0 24 24" fill="currentColor" class="size-4" aria-hidden="true"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg><span class="inline-flex items-center gap-1.5 rounded-full bg-neutral-950/[0.03] hover:bg-neutral-950/[0.06] transition-colors pl-1 pr-3 py-1">__BAILEY_AVATAR__@thebaileygrind_</span></a>
    </p>
    <p class="mt-2.5 mx-auto text-sm text-neutral-500 max-w-prose text-balance">
      Taurus risings to share their Venus, north node, and Saturn placements,
      along with their dreams and the lessons they&rsquo;ve attracted.
      Tap any sign or house to filter the messages.
    </p>
    <p class="mt-3">
      <span class="inline-flex items-center gap-1.5 rounded-full bg-neutral-950/[0.03] px-3 py-1 text-xs text-neutral-500">
        Last updated <span id="updated" class="font-medium text-neutral-900" data-time="__UPDATED__"></span>
      </span>
    </p>
  </header>

  <div id="stats" class="mt-12 grid grid-cols-2 md:grid-cols-3 gap-2.5"></div>

  <div class="mt-10 mx-auto max-w-prose text-center">
    <p class="text-xs text-neutral-400 text-balance">
      Every placement is self-reported, and each comment is shown verbatim. Where someone named only
      a sign or only a house, the other was filled in using whole-sign houses &mdash; about 1 in 9 values.
      Roughly 16% of the fully-stated placements don&rsquo;t fit whole-sign, so some of those are off by a house.
    </p>

  </div>

__DREAM_THEME_PIE__

  <div class="mt-12 mx-auto max-w-prose flex flex-wrap items-center gap-2">
    <input id="q" type="search" placeholder="Search dreams, lessons, comments&hellip;"
      class="flex-1 min-w-40 rounded-xl bg-neutral-950/[0.03] px-3.5 py-2.5 text-sm placeholder:text-neutral-400 focus:outline-none focus:ring-1 focus:ring-neutral-300">
    <button id="clear" class="hidden rounded-xl px-3.5 py-2.5 text-sm text-neutral-500 bg-neutral-950/[0.03]">Clear filters</button>
  </div>

  <div id="count" role="status" aria-live="polite" aria-atomic="true" class="mt-10 py-2 mx-auto max-w-prose text-center text-xs font-semibold text-neutral-900"></div>

  <div id="list" class="mt-10 mx-auto max-w-prose space-y-14"></div>

  <div class="h-10"></div>
</div>

<script>
const DATA = __DATA__;
const DREAM_THEME_LABELS = __DREAM_THEME_LABELS__;

const ord = h => h + (h === 1 ? "st" : h === 2 ? "nd" : h === 3 ? "rd" : "th");
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// returns HTML: sign stays foreground, house is softened
const fmtPlacement = (sign, house) => {
  if (!sign && !house) return null;
  const parts = [];
  if (sign) parts.push(esc(sign));
  if (house) parts.push(`<span class="text-neutral-950/50">${ord(house)} house</span>`);
  return parts.join(" ");
};
const rel = iso => {
  const s = Math.max(0, (Date.now() - new Date(iso + "Z").getTime()) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return Math.floor(s / 60) + "m";
  if (s < 86400) return Math.floor(s / 3600) + "h";
  if (s < 604800) return Math.floor(s / 86400) + "d";
  if (s < 2419200) return Math.floor(s / 604800) + "w";
  const d = new Date(iso + "Z");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return months[d.getMonth()] + " " + d.getDate();
};

// painting-sampled accents per planet (see tailwind.config colors)
const ACCENT = {
  venus:  { title: "text-venus", bar: "bg-venus", barSoft: "bg-venus/25", rowOn: "bg-venus/10" },
  nn:     { title: "text-node", bar: "bg-node", barSoft: "bg-node/25", rowOn: "bg-node/10" },
  saturn: { title: "text-saturn", bar: "bg-saturn", barSoft: "bg-saturn/25", rowOn: "bg-saturn/10" },
};
const planetOf = key => key.startsWith("venus") ? "venus" : key.startsWith("nn") ? "nn" : "saturn";

const filters = { venus_sign: null, venus_house: null, nn_sign: null, nn_house: null, saturn_sign: null, saturn_house: null };

function dist(key) {
  const c = {};
  for (const r of DATA) { const v = r[key]; if (v != null) c[v] = (c[v] || 0) + 1; }
  return Object.entries(c).sort((a, b) => b[1] - a[1]);
}
const STAT_DEFS = [
  ["Venus sign", "venus_sign"], ["Venus house", "venus_house"],
  ["North node sign", "nn_sign"], ["North node house", "nn_house"],
  ["Saturn sign", "saturn_sign"], ["Saturn house", "saturn_house"],
];
const statsEl = document.getElementById("stats");

function renderStats() {
  statsEl.innerHTML = STAT_DEFS.map(([title, key]) => {
    const a = ACCENT[planetOf(key)];
    const rows = dist(key);
    const max = rows.length ? rows[0][1] : 1;
    const isHouse = key.endsWith("house");
    return `
    <div class="rounded-2xl bg-neutral-950/[0.03] p-3">
      <h2 class="text-xs font-medium ${a.title}">${title}</h2>
      <div class="mt-2">
        ${rows.map(([v, n], i) => {
          const active = String(filters[key]) === String(v);
          const solid = active || i === 0;
          return `
          <button data-key="${key}" data-value="${esc(v)}"
            class="w-full grid grid-cols-[3.5rem_1fr_1.25rem] sm:grid-cols-[4.5rem_1fr_1.25rem] items-center gap-1.5 text-xs text-left rounded-md px-1.5 py-[3px] -mx-1.5 cursor-pointer transition-colors ${active ? a.rowOn : "hover:bg-neutral-950/5"}">
            <span class="truncate ${active ? "font-semibold" : ""}">${isHouse ? ord(+v) : v}</span>
            <span class="h-1 rounded-full overflow-hidden">
              <span class="block h-full rounded-full ${solid ? a.bar : a.barSoft}" style="width:${(n / max) * 100}%"></span>
            </span>
            <span class="text-right tabular-nums ${i === 0 || active ? "font-semibold " + a.title : "text-neutral-400"}">${n}</span>
          </button>`;
        }).join("")}
      </div>
    </div>`;
  }).join("");
}
statsEl.addEventListener("click", e => {
  const btn = e.target.closest("[data-key]");
  if (!btn) return;
  const { key, value } = btn.dataset;
  filters[key] = String(filters[key]) === value ? null : (key.endsWith("house") ? +value : value);
  renderStats();
  render();
});

const chipDef = [
  ["Venus", "venus", "venus_sign", "venus_house"],
  ["Node", "nn", "nn_sign", "nn_house"],
  ["Saturn", "saturn", "saturn_sign", "saturn_house"],
];

function entryHTML(r) {
  const themeNames = (r.dream_theme_ids || [])
    .map(themeId => DREAM_THEME_LABELS[themeId])
    .filter(Boolean)
    .join(", ");
  const fields = [
    ...chipDef.map(([label, , sk, hk]) => [label, fmtPlacement(r[sk], r[hk])]),
    ["Dreams", r.dreams && esc(r.dreams)],
    ["Themes", themeNames && esc(themeNames)],
    ["Lessons", r.lessons_attracted && esc(r.lessons_attracted)],
  ].filter(([, v]) => v)
   .map(([k, v]) => `
    <div class="grid grid-cols-[4.5rem_1fr] gap-x-3">
      <span class="font-medium text-neutral-500">${k}</span><span>${v}</span>
    </div>`).join("");

  const bubble = r.text ? `
    <div class="mt-2 rounded-2xl rounded-tl-none bg-neutral-950/[0.03] px-3.5 py-2.5 whitespace-pre-wrap">${esc(r.text)}</div>` : "";

  return `<div class="mx-auto max-w-prose text-xs">
    <div class="flex items-center gap-2">
      ${r.avatar ? `<img src="${r.avatar}" alt="" class="size-5 rounded-full object-cover">` : `<span class="size-5 rounded-full bg-neutral-950/10"></span>`}
      <span class="font-semibold">@${esc(r.username)}</span>
      <span class="text-neutral-400">${rel(r.created_time)}</span>
    </div>
    ${bubble}
    ${fields ? `<div class="mt-3 space-y-2">${fields}</div>` : ""}
  </div>`;
}

const q = document.getElementById("q");
const list = document.getElementById("list");
const clearBtn = document.getElementById("clear");
const countEl = document.getElementById("count");
const dreamThemeSection = document.getElementById("dream-themes");
let activeDreamTheme = null;

function renderDreamThemeSelection() {
  for (const target of dreamThemeSection.querySelectorAll("[data-dream-theme]")) {
    const selected = target.dataset.dreamTheme === activeDreamTheme;
    target.setAttribute("aria-pressed", String(selected));
    target.style.opacity = activeDreamTheme && !selected ? "0.5" : "1";
    if (target.classList.contains("dream-theme-slice")) {
      target.setAttribute("fill-opacity", selected ? "1" : target.dataset.chartOpacity);
      target.setAttribute("stroke-width", selected ? "4" : "2");
    }
  }
  for (const label of dreamThemeSection.querySelectorAll("[data-dream-theme-percent]")) {
    const selected = label.dataset.dreamThemePercent === activeDreamTheme;
    label.setAttribute("fill", selected ? "#e11d48" : label.dataset.chartTextColor);
    label.setAttribute("fill-opacity", selected ? "1" : "0.5");
    label.style.opacity = activeDreamTheme && !selected ? "0.5" : "1";
  }
}

function selectDreamTheme(themeId) {
  activeDreamTheme = activeDreamTheme === themeId ? null : themeId;
  renderDreamThemeSelection();
  render();
}

dreamThemeSection.addEventListener("click", event => {
  const target = event.target.closest("[data-dream-theme]");
  if (target) selectDreamTheme(target.dataset.dreamTheme);
});
dreamThemeSection.addEventListener("keydown", event => {
  const target = event.target.closest(".dream-theme-slice[data-dream-theme]");
  if (!target || (event.key !== "Enter" && event.key !== " ")) return;
  event.preventDefault();
  selectDreamTheme(target.dataset.dreamTheme);
});

function render() {
  const term = q.value.trim().toLowerCase();
  const active = Object.entries(filters).filter(([, v]) => v != null);
  clearBtn.classList.toggle("hidden", !active.length && !term && !activeDreamTheme);
  const shown = DATA.filter(r => {
    for (const [k, v] of active) if (r[k] !== v) return false;
    if (activeDreamTheme && r.dream_primary_theme_id !== activeDreamTheme) return false;
    if (term) {
      const hay = [r.username, r.display_name, r.text, r.dreams, r.lessons_attracted, r.life_events, r.notes]
        .filter(Boolean).join(" ").toLowerCase();
      if (!hay.includes(term)) return false;
    }
    return true;
  });
  countEl.textContent = shown.length === DATA.length
    ? `${DATA.length} responses`
    : `${shown.length} of ${DATA.length} responses`;
  list.innerHTML = shown.length
    ? shown.map(entryHTML).join("")
    : `<div class="py-10 text-center text-sm text-neutral-400">No responses match.</div>`;
}
q.addEventListener("input", render);
clearBtn.addEventListener("click", () => {
  q.value = "";
  for (const k of Object.keys(filters)) filters[k] = null;
  activeDreamTheme = null;
  renderStats();
  renderDreamThemeSelection();
  render();
});

const updatedEl = document.getElementById("updated");
updatedEl.textContent = rel(updatedEl.dataset.time) + " ago";

renderStats();
renderDreamThemeSelection();
render();
</script>
</body>
</html>
"""

def build_page(project_root=None):
    """Build the self-contained HTML page and synchronized extracted CSV."""
    project_root = Path(project_root) if project_root is not None else root
    data = json.loads((project_root / "data/extracted.json").read_text())
    dream_theme_summary = load_dream_theme_summary_v2(data, project_root=project_root)
    dream_theme_pie = render_dream_theme_pie(dream_theme_summary)
    dream_theme_labels = {
        theme["id"]: theme["label"] for theme in dream_theme_summary["themes"]
    }

    # keep the CSV in sync
    fields = ["username","display_name","created_time","digg_count","reply_count",
              "venus_sign","venus_house","nn_sign","nn_house","saturn_sign","saturn_house",
              "dreams","lessons_attracted","life_events","notes","text"]
    with open(project_root / "data/extracted.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)

    public_themes_by_source = {
        (assignment["username"], assignment["created_time"]): assignment
        for assignment in dream_theme_summary["public_assignments"]
    }
    for row in data:
        public_assignment = public_themes_by_source.get(source_key(row), {})
        row["dream_primary_theme_id"] = public_assignment.get("dream_primary_theme_id")
        row["dream_theme_ids"] = public_assignment.get("dream_theme_ids", [])

    # inline avatars (fetched by fetch_avatars.py) as data URIs
    for row in data:
        avatar = project_root / "avatars" / f"{row['username']}.jpg"
        row["avatar"] = (
            "data:image/jpeg;base64," + base64.b64encode(avatar.read_bytes()).decode()
            if avatar.exists()
            else None
        )

    bailey = project_root / "avatars" / "thebaileygrind_.jpg"
    bailey_img = (f'<img src="data:image/jpeg;base64,{base64.b64encode(bailey.read_bytes()).decode()}" alt="" '
                  'class="size-5 rounded-full object-cover">') if bailey.exists() else ""

    logo = project_root / "avatars" / "communion_logo.png"
    logo_b64 = base64.b64encode(logo.read_bytes()).decode() if logo.exists() else ""
    logo_img = (f'<img src="data:image/png;base64,{logo_b64}" alt="Communion" class="size-10 mx-auto">') if logo_b64 else ""
    logo_sm = (f'<img src="data:image/png;base64,{logo_b64}" alt="" class="size-7">') if logo_b64 else ""

    # newest comment in the set = how current the data is; rendered relative by rel()
    updated = max(row["created_time"] for row in data)

    site = "https://taurus-rising-comments.vercel.app"
    description = (f"{len(data)} Taurus risings share their Venus, north node, and Saturn "
                   "placements, along with their dreams and the lessons they've attracted.")

    output = (TEMPLATE
              .replace("__DATA__", json.dumps(data, ensure_ascii=False))
              .replace("__DREAM_THEME_LABELS__", json.dumps(dream_theme_labels, ensure_ascii=False))
              .replace("__BAILEY_AVATAR__", bailey_img)
              .replace("__COMMUNION_LOGO_SM__", logo_sm)
              .replace("__COMMUNION_LOGO__", logo_img)
              .replace("__DREAM_THEME_PIE__", dream_theme_pie)
              .replace("__UPDATED__", updated)
              .replace("__SITE__", site)
              .replace("__DESC__", description)
              .replace("__COUNT__", str(len(data))))
    (project_root / "index.html").write_text(output)
    print(f"wrote index.html ({len(output):,} bytes, {len(data)} records)")
    return output


def main():
    build_page()


if __name__ == "__main__":
    main()
