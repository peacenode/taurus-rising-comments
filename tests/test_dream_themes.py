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


def render_summary(counts):
    total = sum(counts)
    return {
        "taxonomy_version": 1,
        "reviewed_dream_count": total,
        "themed_response_count": sum(count > 0 for count in counts),
        "total_theme_assignments": total,
        "themes": [
            {
                "id": theme["id"],
                "label": theme["label"],
                "color": theme["color"],
                "description": theme["description"],
                "count": count,
                "percentage": count / total * 100,
            }
            for theme, count in zip(TAXONOMY["themes"], counts, strict=True)
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


class DreamThemeRenderTests(unittest.TestCase):
    def test_single_theme_renders_a_full_circle_and_zero_percentages(self):
        markup = build_page.render_dream_theme_pie(render_summary([3, 0, 0, 0, 0, 0, 0]))
        self.assertIn('<circle cx="160" cy="160" r="128" fill="#171717"', markup)
        self.assertNotIn('<path d="M 160 160', markup)
        self.assertIn("3 · 100.0%", markup)
        self.assertEqual(markup.count("0 · 0%"), 6)
        self.assertNotIn("0 · 0.0%", markup)

    def test_narrow_slice_renders_a_leader_line_and_numbered_markers(self):
        markup = build_page.render_dream_theme_pie(render_summary([99, 1, 0, 0, 0, 0, 0]))
        self.assertEqual(markup.count("<line "), 1)
        self.assertEqual(markup.count('r="11"'), 2)
        self.assertIn('aria-label="Home / Belonging"', markup)
        self.assertIn('aria-label="Cultivation"', markup)

    def test_legend_has_seven_ordered_rows_and_accessible_ids(self):
        markup = build_page.render_dream_theme_pie(render_summary([1, 1, 1, 1, 1, 1, 1]))
        self.assertEqual(markup.count("<li class="), 7)
        positions = [markup.index(theme["label"]) for theme in TAXONOMY["themes"]]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('role="img" aria-labelledby="dream-pie-title dream-pie-desc"', markup)
        self.assertEqual(markup.count('id="dream-pie-title"'), 1)
        self.assertEqual(markup.count('id="dream-pie-desc"'), 1)


class ProductionDreamThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assignments_doc = json.loads((ROOT / "data/dream_theme_assignments.json").read_text())
        cls.review = json.loads((ROOT / "data/dream_theme_review.json").read_text())
        subprocess.run(
            [sys.executable, "build_page.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.html = (ROOT / "index.html").read_text()

    def test_taxonomy_is_complete_and_ordered(self):
        self.assertEqual(TAXONOMY["taxonomy_version"], 1)
        self.assertEqual([theme["id"] for theme in TAXONOMY["themes"]], THEME_IDS)
        self.assertEqual([theme["order"] for theme in TAXONOMY["themes"]], list(range(1, 8)))
        for theme in TAXONOMY["themes"]:
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
            self.assertEqual(assignment["review_status"], "reviewed")
            self.assertEqual(len(assignment["theme_ids"]), len(set(assignment["theme_ids"])))
            self.assertEqual(assignment["theme_ids"], sorted(assignment["theme_ids"], key=THEME_IDS.index))

    def test_secondary_review_covers_sample_edges_and_resolutions(self):
        dream_rows = sorted((row for row in DATA if row.get("dreams")), key=source_key)
        assignment_by_key = {
            (item["username"], item["created_time"]): item
            for item in self.assignments_doc["assignments"]
        }
        required = {source_key(row) for index, row in enumerate(dream_rows) if index % 5 == 0}
        required.update(
            key for key, item in assignment_by_key.items()
            if not item["theme_ids"] or len(item["theme_ids"]) >= 4
        )
        secondary = {
            (item["username"], item["created_time"]): item
            for item in self.review["secondary_reviews"]
        }
        self.assertEqual(self.review["review_method"], REVIEW_METHOD)
        self.assertEqual(self.review["sample_rule"], SAMPLE_RULE)
        self.assertEqual(set(secondary), required)
        self.assertTrue(self.review["all_disagreements_resolved"])

        resolutions = {}
        for item in self.review["resolutions"]:
            key = item["username"], item["created_time"]
            self.assertNotIn(key, resolutions)
            resolutions[key] = item
            self.assertNotEqual(item["primary_theme_ids"], item["secondary_theme_ids"])
            self.assertEqual(item["secondary_theme_ids"], secondary[key]["theme_ids"])
            self.assertEqual(item["resolved_theme_ids"], assignment_by_key[key]["theme_ids"])
        for key, secondary_item in secondary.items():
            if key not in resolutions:
                self.assertEqual(secondary_item["theme_ids"], assignment_by_key[key]["theme_ids"])

    def test_aggregate_counts_are_consistent(self):
        counts = {theme_id: 0 for theme_id in THEME_IDS}
        themed = 0
        for assignment in self.assignments_doc["assignments"]:
            if assignment["theme_ids"]:
                themed += 1
            for theme_id in assignment["theme_ids"]:
                counts[theme_id] += 1
        self.assertGreater(themed, 0)
        self.assertGreater(sum(counts.values()), themed)
        self.assertAlmostEqual(sum(count / sum(counts.values()) * 360 for count in counts.values()), 360)

    def test_generated_chart_is_accessible_additive_and_has_seven_rows(self):
        self.assertIn('id="dream-themes"', self.html)
        self.assertIn('aria-labelledby="dream-pie-title dream-pie-desc"', self.html)
        self.assertEqual(self.html.count('id="dream-pie-title"'), 1)
        self.assertEqual(self.html.count('id="dream-pie-desc"'), 1)
        section = self.html.split('<section id="dream-themes"', 1)[1].split(
            '<div class="mt-12 mx-auto max-w-prose flex', 1
        )[0]
        self.assertEqual(section.count("<li class="), 7)
        self.assertIn('id="stats"', self.html)
        for label in ("Venus sign", "Venus house", "North node sign", "North node house", "Saturn sign", "Saturn house"):
            self.assertEqual(self.html.count(f'["{label}"'), 1)

    def test_private_assignment_and_review_metadata_is_absent(self):
        for private_key in (
            '"source_digest"',
            '"review_status"',
            '"theme_ids"',
            REVIEW_METHOD,
            SAMPLE_RULE,
            "classification_guidance",
        ):
            self.assertNotIn(private_key, self.html)
        for theme in TAXONOMY["themes"]:
            self.assertEqual(self.html.count(theme["description"]), 1)
            self.assertNotIn(theme["classification_guidance"], self.html)

    def test_displayed_percentages_and_summary_counts_match_assignments(self):
        counts = {theme_id: 0 for theme_id in THEME_IDS}
        themed = 0
        for assignment in self.assignments_doc["assignments"]:
            themed += bool(assignment["theme_ids"])
            for theme_id in assignment["theme_ids"]:
                counts[theme_id] += 1
        total = sum(counts.values())
        for theme_id in THEME_IDS:
            percentage = counts[theme_id] / total * 100
            percentage_text = "0%" if percentage == 0 else f"{percentage:.1f}%"
            self.assertIn(f"{counts[theme_id]} · {percentage_text}", self.html)
        self.assertIn(
            f"{themed} of 238 reviewed Dream responses map to at least one theme · "
            f"{total} theme assignments",
            self.html,
        )

    def test_chart_does_not_add_filter_behavior(self):
        section = self.html.split('<section id="dream-themes"', 1)[1].split(
            '<div class="mt-12 mx-auto max-w-prose flex', 1
        )[0]
        self.assertNotIn("data-key", section)
        self.assertNotIn("addEventListener", section)

    def test_existing_interaction_blocks_and_startup_calls_are_unchanged(self):
        source = (ROOT / "build_page.py").read_text()
        expected = [
            ("const filters =", "const chipDef =", "17d5003599651956e524a38b9ef59a77cba44bb8579c6b2662c727db40a938bc"),
            ("const chipDef =", "const q =", "fece93c6a4b989b4785193822473671688084b2915632eb41efb89440ccbd5ef"),
            ("const q =", "const updatedEl =", "eed13ce3c38309d65ef5e69ff333b42e21e1ee9c06f339b2180f78e44c31ab59"),
        ]
        for start, end, digest in expected:
            block = source[source.index(start):source.index(end)]
            self.assertEqual(hashlib.sha256(block.encode()).hexdigest(), digest)
        startup = "\nrenderStats();\nrender();\n"
        self.assertEqual(source.count(startup), 1)
        self.assertEqual(self.html.count(startup), 1)


if __name__ == "__main__":
    unittest.main()
