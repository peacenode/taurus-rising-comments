import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import build_page


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data/extracted.json").read_text())
TAXONOMY = json.loads((ROOT / "data/dream_themes.json").read_text())
TAXONOMY_V2 = json.loads((ROOT / "data/dream_themes_v2.json").read_text())
CALIBRATION_V2 = json.loads((ROOT / "data/dream_theme_calibration_v2.json").read_text())
THEME_IDS = [
    "home-belonging",
    "cultivation",
    "service",
    "freedom",
    "stewardship",
    "self-sufficiency",
    "transmission",
]
REVIEW_METHOD = "blind-independent-pass"
SAMPLE_RULE = (
    "sorted response keys where index % 5 == 0, plus every empty-theme "
    "and four-plus-theme assignment"
)


def source_key(row):
    return row["username"], row["created_time"]


def source_digest(row):
    canonical = json.dumps(
        {"dreams": row["dreams"], "text": row["text"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def fixture_row(index):
    return {
        "username": f"fixture-{index}",
        "created_time": f"2026-07-{index + 1:02d}T12:00:00",
        "dreams": f"Dream response {index}",
        "text": f"Full comment {index}",
    }


def write_fixture(
    base,
    rows,
    final_theme_ids,
    *,
    secondary_theme_ids=None,
    resolutions=None,
    assignment_mutator=None,
    review_overrides=None,
):
    """Write a complete isolated taxonomy/assignment/review fixture."""
    base = Path(base)
    taxonomy_path = base / "taxonomy.json"
    assignments_path = base / "assignments.json"
    review_path = base / "review.json"
    taxonomy_path.write_text(json.dumps(copy.deepcopy(TAXONOMY)))

    assignments = []
    for row, theme_ids in zip(rows, final_theme_ids, strict=True):
        assignment = {
            "username": row["username"],
            "created_time": row["created_time"],
            "source_digest": source_digest(row),
            "theme_ids": list(theme_ids),
            "review_status": "reviewed",
        }
        assignments.append(assignment)
    if assignment_mutator is not None:
        assignment_mutator(assignments)
    assignments_path.write_text(json.dumps({"taxonomy_version": 1, "assignments": assignments}))

    required_indexes = {index for index in range(len(rows)) if index % 5 == 0}
    required_indexes.update(
        index for index, theme_ids in enumerate(final_theme_ids)
        if not theme_ids or len(theme_ids) >= 4
    )
    secondary_theme_ids = secondary_theme_ids or {
        index: list(final_theme_ids[index]) for index in required_indexes
    }
    secondary_reviews = [
        {
            "username": rows[index]["username"],
            "created_time": rows[index]["created_time"],
            "theme_ids": list(secondary_theme_ids[index]),
        }
        for index in sorted(required_indexes)
    ]
    review = {
        "taxonomy_version": 1,
        "review_method": REVIEW_METHOD,
        "sample_rule": SAMPLE_RULE,
        "all_disagreements_resolved": True,
        "secondary_reviews": secondary_reviews,
        "resolutions": list(resolutions or []),
    }
    if review_overrides:
        review.update(review_overrides)
    review_path.write_text(json.dumps(review))
    return taxonomy_path, assignments_path, review_path


def load_fixture(rows, paths):
    return build_page.load_dream_theme_summary(
        rows,
        taxonomy_path=paths[0],
        assignments_path=paths[1],
        review_path=paths[2],
    )


def v2_classification(theme_id, row, *, role="primary"):
    item = {
        "theme_id": theme_id,
        "evidence_spans": [{
            "field": "text",
            "start": 0,
            "end": len(row["text"]),
            "quote": row["text"],
        }],
        "scores": {
            "explicit_support": 2,
            "centrality": 2,
            "standalone": 2,
            "specificity": 2,
            "total": 8,
        },
        "confidence": "high" if role != "supporting" else "medium",
    }
    if role == "supporting":
        item["supporting_reason"] = "setting"
    return item


def write_v2_fixture(
    base,
    rows,
    specs,
    *,
    taxonomy_mutator=None,
    assignments_mutator=None,
    review_mutator=None,
):
    """Write a complete, no-adjudication v2 fixture for the page loader."""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    taxonomy_path = base / "dream_themes_v2.json"
    calibration_path = base / "dream_theme_calibration_v2.json"
    assignments_path = base / "dream_theme_assignments_v2.json"
    review_path = base / "dream_theme_review_v2.json"

    taxonomy = copy.deepcopy(TAXONOMY_V2)
    if taxonomy_mutator:
        taxonomy_mutator(taxonomy)
    taxonomy_path.write_text(json.dumps(taxonomy))
    calibration_path.write_text(json.dumps(CALIBRATION_V2))
    taxonomy_digest = build_page.canonical_json_digest(taxonomy)
    calibration_digest = build_page.canonical_json_digest(CALIBRATION_V2)

    assignments = []
    pass_assignments = []
    for row, spec in zip(rows, specs, strict=True):
        primary_id = spec.get("primary")
        co_ids = spec.get("co_dominant", [])
        supporting_ids = spec.get("supporting", [])
        temporary = {
            "username": row["username"],
            "created_time": row["created_time"],
            "source_digest": source_digest(row),
            "public_status": "themed" if primary_id else "unthemed",
            "primary": v2_classification(primary_id, row) if primary_id else None,
            "co_dominant": [
                v2_classification(theme_id, row, role="co-dominant")
                for theme_id in co_ids
            ],
            "supporting": [
                v2_classification(theme_id, row, role="supporting")
                for theme_id in supporting_ids
            ],
            "rejected_candidates": [],
            "unthemed_reason": None if primary_id else "No candidate reaches the primary threshold.",
        }
        pass_assignments.append(copy.deepcopy(temporary))
        final = copy.deepcopy(temporary)
        final["review_status"] = "blind-public-role-agreement"
        final["adjudication_id"] = None
        assignments.append(final)

    assignment_doc = {
        "schema_version": 2,
        "taxonomy_version": 2,
        "taxonomy_digest_algorithm": build_page.DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM,
        "taxonomy_digest": taxonomy_digest,
        "calibration_digest_algorithm": build_page.DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM,
        "calibration_digest": calibration_digest,
        "supersedes": copy.deepcopy(build_page.DREAM_THEME_V2_ASSIGNMENTS_SUPERSEDES),
        "source_digest_algorithm": build_page.DREAM_THEME_V2_SOURCE_DIGEST_ALGORITHM,
        "source_row_count": len(rows),
        "assignments": assignments,
    }
    if assignments_mutator:
        assignments_mutator(assignment_doc)
    assignments_path.write_text(json.dumps(assignment_doc))

    blind_passes = []
    for pass_id, reviewer_id in (("pass-a", "fixture-a"), ("pass-b", "fixture-b")):
        blind_passes.append({
            "schema_version": 2,
            "taxonomy_version": 2,
            "pass_id": pass_id,
            "reviewer": {
                "reviewer_id": reviewer_id,
                "kind": "fixture",
                "prompt_version": "fixture-v2",
            },
            "assignments": copy.deepcopy(pass_assignments),
        })
    pass_maps = {
        blind_pass["pass_id"]: {
            (item["username"], item["created_time"]): item
            for item in blind_pass["assignments"]
        }
        for blind_pass in blind_passes
    }
    final_map = {
        (item["username"], item["created_time"]): item
        for item in assignment_doc["assignments"]
    }
    resolutions = []
    for key in sorted(final_map):
        final = final_map[key]
        resolutions.append({
            "username": key[0],
            "created_time": key[1],
            "decision": final["review_status"],
            "required_reasons": [],
            "pass_a_judgment_digest": build_page.canonical_json_digest(pass_maps["pass-a"][key]),
            "pass_b_judgment_digest": build_page.canonical_json_digest(pass_maps["pass-b"][key]),
            "final_assignment_digest": build_page.canonical_json_digest(final),
            "adjudication_id": final["adjudication_id"],
        })
    review = {
        "schema_version": 2,
        "taxonomy_version": 2,
        "taxonomy_digest_algorithm": build_page.DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM,
        "taxonomy_digest": taxonomy_digest,
        "calibration_digest_algorithm": build_page.DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM,
        "calibration_digest": calibration_digest,
        "calibration_identity_manifest": [
            {"username": key[0], "created_time": key[1]}
            for key in sorted(
                (item["username"], item["created_time"])
                for item in CALIBRATION_V2["rows"]
            )
        ],
        "supersedes": copy.deepcopy(build_page.DREAM_THEME_V2_REVIEW_SUPERSEDES),
        "review_method": build_page.DREAM_THEME_V2_REVIEW_METHOD,
        "source_digest_algorithm": build_page.DREAM_THEME_V2_SOURCE_DIGEST_ALGORITHM,
        "judgment_digest_algorithm": build_page.DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM,
        "source_row_count": len(rows),
        "blind_passes": blind_passes,
        "comparison": {
            "row_count": len(rows),
            "agreement": {},
            "per_theme_public_f1": {},
            "per_theme_primary_f1": {},
            "required_adjudications": [],
        },
        "adjudicator": None,
        "adjudications": [],
        "resolutions": resolutions,
        "all_required_adjudications_complete": True,
    }
    if review_mutator:
        review_mutator(review)
    review_path.write_text(json.dumps(review))
    return taxonomy_path, calibration_path, assignments_path, review_path


def load_v2_fixture(rows, paths):
    return build_page.load_dream_theme_summary_v2(
        rows,
        taxonomy_path=paths[0],
        calibration_path=paths[1],
        assignments_path=paths[2],
        review_path=paths[3],
    )


def render_summary(counts):
    total = sum(counts)
    return {
        "taxonomy_version": 2,
        "reviewed_dream_count": total,
        "themed_response_count": total,
        "total_primary_responses": total,
        "themes": [
            {
                "id": theme["id"],
                "label": theme["label"],
                "color": theme["color"],
                "description": theme["description"],
                "count": count,
                "percentage": count / total * 100,
            }
            for theme, count in zip(TAXONOMY_V2["themes"], counts, strict=True)
        ],
    }


class IsolatedDreamThemeValidationTests(unittest.TestCase):
    def test_importing_build_module_has_no_output_side_effects(self):
        tracked_paths = [ROOT / "index.html", ROOT / "data/extracted.csv"]
        before = {path: path.read_bytes() for path in tracked_paths}
        spec = importlib.util.spec_from_file_location("build_page_import_check", ROOT / "build_page.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        after = {path: path.read_bytes() for path in tracked_paths}
        self.assertEqual(after, before)

    def test_stale_source_digest_fails(self):
        rows = [fixture_row(0)]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_fixture(
                directory,
                rows,
                [[THEME_IDS[0]]],
                assignment_mutator=lambda items: items[0].update(source_digest="stale"),
            )
            with self.assertRaisesRegex(ValueError, "Stale Dream assignment"):
                load_fixture(rows, paths)

    def test_duplicate_resolution_identity_fails(self):
        rows = [fixture_row(0)]
        resolution = {
            "username": rows[0]["username"],
            "created_time": rows[0]["created_time"],
            "primary_theme_ids": [THEME_IDS[0]],
            "secondary_theme_ids": [THEME_IDS[1]],
            "resolved_theme_ids": [THEME_IDS[0]],
        }
        with tempfile.TemporaryDirectory() as directory:
            paths = write_fixture(
                directory,
                rows,
                [[THEME_IDS[0]]],
                secondary_theme_ids={0: [THEME_IDS[1]]},
                resolutions=[resolution, copy.deepcopy(resolution)],
            )
            with self.assertRaisesRegex(ValueError, "Duplicate Dream resolution"):
                load_fixture(rows, paths)

    def test_review_metadata_is_exact(self):
        rows = [fixture_row(0)]
        for field, value in (
            ("review_method", "manual-pass"),
            ("sample_rule", "every fifth"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                paths = write_fixture(
                    directory,
                    rows,
                    [[THEME_IDS[0]]],
                    review_overrides={field: value},
                )
                with self.assertRaisesRegex(ValueError, field):
                    load_fixture(rows, paths)

    def test_multi_label_counts_count_each_themed_response_once(self):
        rows = [fixture_row(0), fixture_row(1)]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_fixture(
                directory,
                rows,
                [[THEME_IDS[0], THEME_IDS[1]], [THEME_IDS[0]]],
            )
            summary = load_fixture(rows, paths)
        counts = {theme["id"]: theme["count"] for theme in summary["themes"]}
        self.assertEqual(summary["reviewed_dream_count"], 2)
        self.assertEqual(summary["themed_response_count"], 2)
        self.assertEqual(summary["total_theme_assignments"], 3)
        self.assertEqual(counts[THEME_IDS[0]], 2)
        self.assertEqual(counts[THEME_IDS[1]], 1)

    def test_legacy_v1_loader_remains_available_as_compatibility_coverage(self):
        rows = [fixture_row(0)]
        with tempfile.TemporaryDirectory() as directory:
            summary = load_fixture(
                rows,
                write_fixture(directory, rows, [[THEME_IDS[0], THEME_IDS[1]]]),
            )
        self.assertEqual(summary["taxonomy_version"], 1)
        self.assertEqual(summary["total_theme_assignments"], 2)
        self.assertNotIn("total_primary_responses", summary)

    def test_zero_total_fails(self):
        rows = [fixture_row(0)]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_fixture(directory, rows, [[]])
            with self.assertRaisesRegex(ValueError, "cannot total zero"):
                load_fixture(rows, paths)

    def test_resolution_may_choose_secondary_or_third_value(self):
        rows = [fixture_row(0)]
        cases = (
            ([THEME_IDS[1]], [THEME_IDS[0]], [THEME_IDS[1]], [THEME_IDS[1]]),
            ([THEME_IDS[2]], [THEME_IDS[0]], [THEME_IDS[1]], [THEME_IDS[2]]),
        )
        for final_ids, primary_ids, secondary_ids, resolved_ids in cases:
            with self.subTest(resolved=resolved_ids), tempfile.TemporaryDirectory() as directory:
                resolution = {
                    "username": rows[0]["username"],
                    "created_time": rows[0]["created_time"],
                    "primary_theme_ids": primary_ids,
                    "secondary_theme_ids": secondary_ids,
                    "resolved_theme_ids": resolved_ids,
                }
                paths = write_fixture(
                    directory,
                    rows,
                    [final_ids],
                    secondary_theme_ids={0: secondary_ids},
                    resolutions=[resolution],
                )
                summary = load_fixture(rows, paths)
                self.assertEqual(summary["total_theme_assignments"], 1)

    def test_unresolved_final_secondary_difference_fails(self):
        rows = [fixture_row(0)]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_fixture(
                directory,
                rows,
                [[THEME_IDS[0]]],
                secondary_theme_ids={0: [THEME_IDS[1]]},
            )
            with self.assertRaisesRegex(ValueError, "Unresolved Dream theme disagreement"):
                load_fixture(rows, paths)


class IsolatedDreamThemeV2ValidationTests(unittest.TestCase):
    def test_primary_only_counts_and_public_projection(self):
        rows = [fixture_row(index) for index in range(3)]
        specs = [
            {
                "primary": THEME_IDS[0],
                "co_dominant": [THEME_IDS[3]],
                "supporting": [THEME_IDS[2]],
            },
            {"primary": THEME_IDS[0]},
            {"primary": THEME_IDS[3]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            summary = load_v2_fixture(
                rows,
                write_v2_fixture(directory, rows, specs),
            )

        counts = {theme["id"]: theme["count"] for theme in summary["themes"]}
        percentages = {theme["id"]: theme["percentage"] for theme in summary["themes"]}
        self.assertEqual(summary["taxonomy_version"], 2)
        self.assertEqual(summary["reviewed_dream_count"], 3)
        self.assertEqual(summary["themed_response_count"], 3)
        self.assertEqual(summary["total_primary_responses"], 3)
        self.assertEqual(sum(counts.values()), 3)
        self.assertEqual(counts[THEME_IDS[0]], 2)
        self.assertEqual(counts[THEME_IDS[3]], 1)
        self.assertEqual(counts[THEME_IDS[2]], 0)
        self.assertAlmostEqual(percentages[THEME_IDS[0]], 2 / 3 * 100)
        self.assertAlmostEqual(sum(percentages.values()), 100)

        first = summary["public_assignments"][0]
        self.assertEqual(
            set(first),
            {"username", "created_time", "dream_primary_theme_id", "dream_theme_ids"},
        )
        self.assertEqual(first["dream_primary_theme_id"], THEME_IDS[0])
        self.assertEqual(first["dream_theme_ids"], [THEME_IDS[0], THEME_IDS[3]])
        self.assertNotIn(THEME_IDS[2], first["dream_theme_ids"])

    def test_co_dominant_displays_on_response_but_does_not_change_pie_or_filter(self):
        rows = [fixture_row(0), fixture_row(1)]
        specs = [
            {"primary": THEME_IDS[0], "co_dominant": [THEME_IDS[3]], "supporting": [THEME_IDS[2]]},
            {"primary": THEME_IDS[3]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            data_dir = project_root / "data"
            paths = write_v2_fixture(data_dir, rows, specs)
            (data_dir / "extracted.json").write_text(json.dumps(rows))
            output = build_page.build_page(project_root=project_root)
            payload = output.split("const DATA = ", 1)[1].split(
                ";\nconst DREAM_THEME_LABELS", 1
            )[0]
            embedded = json.loads(payload)

        self.assertEqual(embedded[0]["dream_primary_theme_id"], THEME_IDS[0])
        self.assertEqual(embedded[0]["dream_theme_ids"], [THEME_IDS[0], THEME_IDS[3]])
        self.assertIn('const themeNames = (r.dream_theme_ids || [])', output)
        self.assertIn('["Themes", themeNames && esc(themeNames)]', output)
        self.assertIn(
            "activeDreamTheme && r.dream_primary_theme_id !== activeDreamTheme",
            output,
        )
        self.assertNotIn("r.dream_theme_ids.includes(activeDreamTheme)", output)
        self.assertIn("activeDreamTheme = activeDreamTheme === themeId ? null : themeId", output)
        for private_key in (
            '"source_digest":',
            '"review_status":',
            '"public_status":',
            '"primary":',
            '"co_dominant":',
            '"supporting":',
            '"scores":',
            '"evidence_spans":',
            '"rejected_candidates":',
            '"blind_passes":',
        ):
            self.assertNotIn(private_key, output)

    def test_each_v2_file_rejects_wrong_version_metadata(self):
        rows = [fixture_row(0)]
        cases = (
            ("taxonomy", {"taxonomy_mutator": lambda document: document.update(taxonomy_version=1)}),
            ("assignments", {"assignments_mutator": lambda document: document.update(schema_version=1)}),
            ("review", {"review_mutator": lambda document: document.update(taxonomy_version=1)}),
        )
        for label, kwargs in cases:
            with self.subTest(file=label), tempfile.TemporaryDirectory() as directory:
                paths = write_v2_fixture(
                    directory,
                    rows,
                    [{"primary": THEME_IDS[0]}],
                    **kwargs,
                )
                with self.assertRaisesRegex(ValueError, "version"):
                    load_v2_fixture(rows, paths)

    def test_taxonomy_role_contract_controls_public_display_and_pie(self):
        rows = [fixture_row(0)]

        def invalidate_primary_role(taxonomy):
            taxonomy["roles"][0]["counts_in_pie"] = False

        with tempfile.TemporaryDirectory() as directory:
            paths = write_v2_fixture(
                directory,
                rows,
                [{"primary": THEME_IDS[0]}],
                taxonomy_mutator=invalidate_primary_role,
            )
            with self.assertRaisesRegex(ValueError, "role behavior"):
                load_v2_fixture(rows, paths)

    def test_review_rejects_hidden_pass_disagreement_and_forged_agreement_final(self):
        rows = [fixture_row(0)]

        def disagree_without_adjudication(review):
            pass_b = next(
                item for item in review["blind_passes"]
                if item["pass_id"] == "pass-b"
            )
            assignment = pass_b["assignments"][0]
            assignment["primary"]["theme_id"] = THEME_IDS[3]
            review["resolutions"][0]["pass_b_judgment_digest"] = (
                build_page.canonical_json_digest(assignment)
            )

        with tempfile.TemporaryDirectory() as directory:
            paths = write_v2_fixture(
                directory,
                rows,
                [{"primary": THEME_IDS[0]}],
                review_mutator=disagree_without_adjudication,
            )
            with self.assertRaisesRegex(ValueError, "omits a required"):
                load_v2_fixture(rows, paths)

        def forge_agreed_final(assignments):
            assignments["assignments"][0]["primary"]["theme_id"] = THEME_IDS[3]

        with tempfile.TemporaryDirectory() as directory:
            paths = write_v2_fixture(
                directory,
                rows,
                [{"primary": THEME_IDS[0]}],
                assignments_mutator=forge_agreed_final,
            )
            with self.assertRaisesRegex(ValueError, "agreement row"):
                load_v2_fixture(rows, paths)


class DreamThemeRenderTests(unittest.TestCase):
    def test_single_theme_renders_a_full_circle_and_percentage_label(self):
        markup = build_page.render_dream_theme_pie(render_summary([3, 0, 0, 0, 0, 0, 0]))
        self.assertIn(
            '<circle cx="160" cy="160" r="106" fill="#e11d48" fill-opacity="1.000"',
            markup,
        )
        self.assertNotIn('<path d="M 160 160', markup)
        self.assertIn(
            'data-dream-theme="home-belonging" data-chart-opacity="1.000" role="button"',
            markup,
        )
        self.assertIn("Home / Belonging: 3 primary responses, 100.0%", markup)
        self.assertIn("100.0%</text>", markup)
        self.assertEqual(markup.count('class="dream-theme-leader"'), 1)
        self.assertEqual(markup.count('class="dream-theme-option'), 7)

    def test_exact_percentage_labels_sit_outside_with_leader_lines(self):
        markup = build_page.render_dream_theme_pie(render_summary([1, 1, 0, 0, 0, 0, 0]))
        self.assertNotIn("<rect ", markup)
        self.assertEqual(markup.count('class="dream-theme-leader"'), 2)
        self.assertEqual(markup.count('class="dream-theme-percent"'), 2)
        self.assertEqual(markup.count('fill-opacity="0.5"'), 2)
        self.assertEqual(markup.count('stroke-opacity="0.5"'), 2)
        self.assertNotIn('stroke="#a3a3a3"', markup)
        self.assertIn('<line x1="269.000" y1="160.000" x2="286.000" y2="160.000"', markup)
        self.assertIn('<line x1="51.000" y1="160.000" x2="34.000" y2="160.000"', markup)
        self.assertIn('<text x="300.000" y="160.500"', markup)
        self.assertIn('<text x="20.000" y="160.500"', markup)
        self.assertEqual(markup.count("50.0%</text>"), 2)
        self.assertIn(
            'aria-label="Select primary theme Home / Belonging: 50.0%, 1 primary response"',
            markup,
        )
        self.assertIn(
            'aria-label="Select primary theme Cultivation: 50.0%, 1 primary response"',
            markup,
        )

    def test_legend_has_seven_ordered_rows_and_accessible_ids(self):
        markup = build_page.render_dream_theme_pie(render_summary([1, 1, 1, 1, 1, 1, 1]))
        self.assertEqual(markup.count("<li class="), 7)
        self.assertEqual(markup.count('<li class="py-1">'), 7)
        self.assertEqual(markup.count('class="dream-theme-option'), 7)
        self.assertEqual(markup.count('class="dream-theme-slice'), 7)
        self.assertEqual(markup.count("focus:outline-none focus-visible:outline"), 7)
        self.assertEqual(markup.count("[-webkit-tap-highlight-color:transparent]"), 7)
        self.assertEqual(markup.count('class="dream-theme-leader"'), 7)
        self.assertEqual(markup.count('data-dream-theme-line="'), 7)
        self.assertEqual(markup.count('class="dream-theme-percent"'), 7)
        self.assertEqual(markup.count('data-dream-theme-percent="'), 7)
        self.assertEqual(markup.count('fill="#000000" fill-opacity="0.5"'), 7)
        self.assertNotIn("group-aria-pressed:ring", markup)
        self.assertNotIn("size-3", markup)
        self.assertNotIn("dream-theme-number", markup)
        positions = [markup.index(theme["label"]) for theme in TAXONOMY_V2["themes"]]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('role="group" aria-labelledby="dream-pie-title dream-pie-desc"', markup)
        self.assertEqual(markup.count('id="dream-pie-title"'), 1)
        self.assertEqual(markup.count('id="dream-pie-desc"'), 1)

    def test_chart_and_legend_run_from_smallest_lightest_to_largest_solid(self):
        markup = build_page.render_dream_theme_pie(render_summary([4, 4, 2, 1, 5, 6, 7]))
        expected = [
            ("freedom", "0.100"),
            ("service", "0.250"),
            ("home-belonging", "0.400"),
            ("cultivation", "0.550"),
            ("stewardship", "0.700"),
            ("self-sufficiency", "0.850"),
            ("transmission", "1.000"),
        ]
        chart, legend = markup.split('<ol class="min-w-0">', 1)
        for section in (chart, legend):
            positions = [section.index(f'data-dream-theme="{theme_id}"') for theme_id, _ in expected]
            self.assertEqual(positions, sorted(positions))
        for theme_id, opacity in expected:
            chart_pattern = (
                rf'fill="#e11d48" fill-opacity="{opacity}"[^>]*'
                rf'data-dream-theme="{theme_id}"'
            )
            self.assertRegex(chart, chart_pattern)
        self.assertNotIn("background:rgba", legend)
        self.assertIn(
            '<span class="block text-sm font-medium">Freedom '
            '<span class="text-neutral-950/50">3.4%</span></span>',
            legend,
        )


class ProductionDreamThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = json.loads((ROOT / "data/dream_themes_v2.json").read_text())
        cls.assignments_doc = json.loads((ROOT / "data/dream_theme_assignments_v2.json").read_text())
        cls.review = json.loads((ROOT / "data/dream_theme_review_v2.json").read_text())
        cls.summary = build_page.load_dream_theme_summary_v2(DATA, project_root=ROOT)
        subprocess.run(
            [sys.executable, "build_page.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.html = (ROOT / "index.html").read_text()

    def test_taxonomy_is_complete_and_ordered(self):
        self.assertEqual(self.taxonomy["schema_version"], 2)
        self.assertEqual(self.taxonomy["taxonomy_version"], 2)
        self.assertEqual([theme["id"] for theme in self.taxonomy["themes"]], THEME_IDS)
        self.assertEqual([theme["order"] for theme in self.taxonomy["themes"]], list(range(1, 8)))
        self.assertEqual(
            [role["id"] for role in self.taxonomy["roles"]],
            ["primary", "co-dominant", "supporting"],
        )
        self.assertTrue(self.taxonomy["roles"][0]["counts_in_pie"])
        self.assertFalse(self.taxonomy["roles"][1]["counts_in_pie"])
        self.assertFalse(self.taxonomy["roles"][2]["public"])
        for theme in self.taxonomy["themes"]:
            self.assertTrue(theme["label"])
            self.assertTrue(theme["description"])
            self.assertTrue(theme["classification_guidance"])
            self.assertRegex(theme["color"], r"^#[0-9a-fA-F]{6}$")

    def test_assignments_cover_every_current_dream(self):
        dream_rows = [row for row in DATA if row.get("dreams")]
        source = {source_key(row): row for row in dream_rows}
        assignments = self.assignments_doc["assignments"]
        assignment_keys = [(item["username"], item["created_time"]) for item in assignments]
        self.assertEqual(len(dream_rows), 238)
        self.assertEqual(len(assignments), 238)
        self.assertEqual(set(assignment_keys), set(source))
        self.assertEqual(len(assignment_keys), len(set(assignment_keys)))
        for assignment in assignments:
            key = assignment["username"], assignment["created_time"]
            self.assertEqual(assignment["source_digest"], source_digest(source[key]))
            self.assertIn(assignment["review_status"], {"blind-public-role-agreement", "adjudicated"})
            if assignment["public_status"] == "themed":
                self.assertIsNotNone(assignment["primary"])
            else:
                self.assertIsNone(assignment["primary"])
                self.assertEqual(assignment["co_dominant"], [])

    def test_final_assignments_match_every_calibration_anchor(self):
        calibration = json.loads(
            (ROOT / "data/dream_theme_calibration_v2.json").read_text()
        )
        assignments = {
            (item["username"], item["created_time"]): item
            for item in self.assignments_doc["assignments"]
        }
        self.assertEqual(len(calibration["rows"]), 38)
        for anchor in calibration["rows"]:
            key = anchor["username"], anchor["created_time"]
            assignment = assignments[key]
            primary_id = (
                assignment["primary"]["theme_id"]
                if assignment["primary"]
                else None
            )
            co_dominant_ids = [
                item["theme_id"] for item in assignment["co_dominant"]
            ]
            self.assertEqual(primary_id, anchor["expected_primary_theme_id"], key)
            self.assertEqual(
                co_dominant_ids,
                anchor["expected_co_dominant_theme_ids"],
                key,
            )

    def test_v2_artifacts_are_bound_to_taxonomy_calibration_and_reconsideration(self):
        calibration = json.loads(
            (ROOT / "data/dream_theme_calibration_v2.json").read_text()
        )
        taxonomy_digest = build_page.canonical_json_digest(self.taxonomy)
        calibration_digest = build_page.canonical_json_digest(calibration)
        for document in (self.assignments_doc, self.review):
            self.assertEqual(
                document["taxonomy_digest_algorithm"],
                build_page.DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM,
            )
            self.assertEqual(document["taxonomy_digest"], taxonomy_digest)
            self.assertEqual(
                document["calibration_digest_algorithm"],
                build_page.DREAM_THEME_V2_JUDGMENT_DIGEST_ALGORITHM,
            )
            self.assertEqual(document["calibration_digest"], calibration_digest)
        expected_calibration_keys = {
            (item["username"], item["created_time"])
            for item in calibration["rows"]
        }
        self.assertEqual(
            {
                (item["username"], item["created_time"])
                for item in self.review["calibration_identity_manifest"]
            },
            expected_calibration_keys,
        )
        reconsideration = self.review["calibrated_reconsideration"]
        self.assertEqual(reconsideration["reconsidered_row_count"], 66)
        self.assertLessEqual(
            reconsideration["changed_row_count"],
            reconsideration["reconsidered_row_count"],
        )

    def test_two_full_independent_passes_and_required_adjudications_are_complete(self):
        self.assertEqual(self.review["review_method"], build_page.DREAM_THEME_V2_REVIEW_METHOD)
        self.assertTrue(self.review["all_required_adjudications_complete"])
        self.assertEqual(
            {blind_pass["pass_id"] for blind_pass in self.review["blind_passes"]},
            {"pass-a", "pass-b"},
        )
        self.assertTrue(all(len(blind_pass["assignments"]) == 238 for blind_pass in self.review["blind_passes"]))
        self.assertEqual(len(self.review["resolutions"]), 238)
        required = {
            (item["username"], item["created_time"])
            for item in self.review["comparison"]["required_adjudications"]
        }
        adjudicated = {
            (item["username"], item["created_time"])
            for item in self.assignments_doc["assignments"]
            if item["review_status"] == "adjudicated"
        }
        self.assertEqual(required, adjudicated)
        self.assertTrue(self.review["comparison"]["release_gate"]["passed"])
        self.assertEqual(self.review["comparison"]["release_gate"]["failed"], [])

    def test_primary_only_aggregate_counts_are_consistent(self):
        counts = {theme_id: 0 for theme_id in THEME_IDS}
        themed = 0
        public = 0
        for assignment in self.assignments_doc["assignments"]:
            if assignment["primary"]:
                themed += 1
                counts[assignment["primary"]["theme_id"]] += 1
                public += 1 + len(assignment["co_dominant"])
        self.assertGreater(themed, 0)
        self.assertEqual(sum(counts.values()), themed)
        self.assertGreater(public, themed)
        self.assertEqual(self.summary["total_primary_responses"], themed)
        self.assertEqual(
            {theme["id"]: theme["count"] for theme in self.summary["themes"]},
            counts,
        )
        self.assertAlmostEqual(sum(theme["percentage"] for theme in self.summary["themes"]), 100)

    def test_generated_chart_is_accessible_additive_and_has_seven_rows(self):
        self.assertIn('id="dream-themes"', self.html)
        self.assertIn('aria-labelledby="dream-pie-title dream-pie-desc"', self.html)
        self.assertEqual(self.html.count('id="dream-pie-title"'), 1)
        self.assertEqual(self.html.count('id="dream-pie-desc"'), 1)
        section = self.html.split('<section id="dream-themes"', 1)[1].split(
            '<div class="mt-12 mx-auto max-w-prose flex', 1
        )[0]
        self.assertEqual(section.count("<li class="), 7)
        self.assertEqual(section.count('class="dream-theme-option'), 7)
        self.assertEqual(
            section.count('class="dream-theme-slice'),
            sum(theme["count"] > 0 for theme in self.summary["themes"]),
        )
        self.assertIn('>Themes</h2>', section)
        self.assertIn("Primary themes across Dream responses", section)
        self.assertIn("listed primary first, followed by any co-dominant themes", section)
        self.assertIn("Primary Dream theme distribution", section)
        expected_ids = [
            theme["id"]
            for theme in sorted(
                self.summary["themes"],
                key=lambda theme: (theme["count"], THEME_IDS.index(theme["id"])),
            )
        ]
        chart, legend = section.split('<ol class="min-w-0">', 1)
        chart_ids = [theme_id for theme_id in expected_ids if next(
            theme["count"] for theme in self.summary["themes"] if theme["id"] == theme_id
        )]
        for rendered_section, rendered_ids in ((chart, chart_ids), (legend, expected_ids)):
            positions = [rendered_section.index(f'data-dream-theme="{theme_id}"') for theme_id in rendered_ids]
            self.assertEqual(positions, sorted(positions))
        self.assertIn('id="stats"', self.html)
        for label in ("Venus sign", "Venus house", "North node sign", "North node house", "Saturn sign", "Saturn house"):
            self.assertEqual(self.html.count(f'["{label}"'), 1)

    def test_private_assignment_and_review_metadata_is_absent(self):
        for private_key in (
            '"source_digest":',
            '"review_status":',
            '"public_status":',
            '"primary":',
            '"co_dominant":',
            '"supporting":',
            '"scores":',
            '"evidence_spans":',
            '"rejected_candidates":',
            '"blind_passes":',
            build_page.DREAM_THEME_V2_REVIEW_METHOD,
            "classification_guidance",
        ):
            self.assertNotIn(private_key, self.html)
        for theme in self.taxonomy["themes"]:
            self.assertEqual(self.html.count(theme["description"]), 1)
            self.assertNotIn(theme["classification_guidance"], self.html)

    def test_embedded_public_theme_ids_match_reviewed_assignments(self):
        payload = self.html.split("const DATA = ", 1)[1].split(
            ";\nconst DREAM_THEME_LABELS", 1
        )[0]
        embedded_rows = json.loads(payload)
        labels_payload = self.html.split("const DREAM_THEME_LABELS = ", 1)[1].split(
            ";\n\nconst ord", 1
        )[0]
        self.assertEqual(
            json.loads(labels_payload),
            {theme["id"]: theme["label"] for theme in self.taxonomy["themes"]},
        )
        assignment_by_key = {
            (item["username"], item["created_time"]): (
                item["primary"]["theme_id"] if item["primary"] else None,
                ([item["primary"]["theme_id"]] if item["primary"] else [])
                + [theme["theme_id"] for theme in item["co_dominant"]],
            )
            for item in self.assignments_doc["assignments"]
        }
        self.assertEqual(len(embedded_rows), 355)
        for row in embedded_rows:
            expected_primary, expected_public = assignment_by_key.get(
                (row["username"], row["created_time"]),
                (None, []),
            )
            self.assertEqual(row["dream_primary_theme_id"], expected_primary)
            self.assertEqual(
                row["dream_theme_ids"],
                expected_public,
            )

    def test_chart_and_theme_list_share_one_filter_behavior(self):
        section = self.html.split('<section id="dream-themes"', 1)[1].split(
            '<div class="mt-12 mx-auto max-w-prose flex', 1
        )[0]
        nonzero_theme_count = len(
            {
                assignment["primary"]["theme_id"]
                for assignment in self.assignments_doc["assignments"]
                if assignment["primary"] is not None
            }
        )
        control_count = len(self.taxonomy["themes"]) + nonzero_theme_count
        self.assertEqual(section.count('data-dream-theme="'), control_count)
        self.assertEqual(section.count('aria-pressed="false"'), control_count)
        self.assertIn('aria-controls="list"', section)
        self.assertIn("Themes on each response are listed primary first", section)
        self.assertIn('aria-label="Select primary theme ', section)
        self.assertIn('role="status" aria-live="polite" aria-atomic="true"', self.html)
        self.assertIn('dreamThemeSection.addEventListener("click"', self.html)
        self.assertIn('dreamThemeSection.addEventListener("keydown"', self.html)
        self.assertIn("r.dream_primary_theme_id !== activeDreamTheme", self.html)
        self.assertNotIn("r.dream_theme_ids.includes(activeDreamTheme)", self.html)
        self.assertIn("activeDreamTheme = null", self.html)
        self.assertIn(
            "activeDreamTheme = activeDreamTheme === themeId ? null : themeId",
            self.html,
        )
        self.assertIn('["Themes", themeNames && esc(themeNames)]', self.html)
        self.assertIn(
            'target.style.opacity = activeDreamTheme && !selected ? "0.5" : "1"',
            self.html,
        )
        self.assertIn(
            'target.setAttribute("fill-opacity", selected ? "1" : target.dataset.chartOpacity)',
            self.html,
        )
        self.assertIn(
            'label.setAttribute("fill", selected ? "#e11d48" : label.dataset.chartTextColor)',
            self.html,
        )
        self.assertIn(
            'line.setAttribute("stroke-opacity", selected ? "1" : line.dataset.chartLineOpacity)',
            self.html,
        )
        self.assertNotIn('? "0.28" : "1"', self.html)

    def test_existing_interaction_blocks_and_startup_calls_are_unchanged(self):
        source = (ROOT / "build_page.py").read_text()
        expected = [
            ("const filters =", "const chipDef =", "17d5003599651956e524a38b9ef59a77cba44bb8579c6b2662c727db40a938bc"),
            ("const chipDef =", "const q =", "8178b8c89fbbf120276c4b6a22bb04a3eda8c61325f979e3d33ee7b781641502"),
            ("const q =", "const updatedEl =", "e2d5233d4e704d7d52e2981ca932f6f863efc711121c68937a1b6399e39d8560"),
        ]
        for start, end, digest in expected:
            block = source[source.index(start):source.index(end)]
            self.assertEqual(hashlib.sha256(block.encode()).hexdigest(), digest)
        startup = "\nrenderStats();\nrenderDreamThemeSelection();\nrender();\n"
        self.assertEqual(source.count(startup), 1)
        self.assertEqual(self.html.count(startup), 1)


if __name__ == "__main__":
    unittest.main()
