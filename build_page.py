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


def render_dream_theme_pie(summary):
    center = 160
    radius = 128
    angle = -90.0
    paths = []
    markers = []

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
        sweep = count / summary["total_theme_assignments"] * 360
        end = angle + sweep
        label = html_lib.escape(theme["label"])
        percent = theme["percentage"]
        percent_text = "0%" if percent == 0 else f"{percent:.1f}%"
        title = html_lib.escape(f"{theme['label']}: {count} assignments, {percent_text}")
        theme_id = html_lib.escape(theme["id"])
        interaction_attrs = (
            f'class="dream-theme-slice cursor-pointer transition-opacity duration-150 focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-600 [-webkit-tap-highlight-color:transparent]" '
            f'data-dream-theme="{theme_id}" data-chart-opacity="{opacity:.3f}" '
            'role="button" tabindex="0" '
            f'aria-label="Select {label}" aria-pressed="false" aria-controls="list"'
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
        sweep_radians = math.radians(sweep)
        marker_distance = (
            0
            if len(nonzero) == 1
            else 4 * radius * math.sin(sweep_radians / 2) / (3 * sweep_radians)
        )
        marker_x, marker_y = point(middle, marker_distance)
        text_color = "#ffffff" if opacity >= 0.7 else "#000000"
        markers.append(
            f'<text x="{marker_x:.3f}" y="{marker_y + 0.5:.3f}" text-anchor="middle" '
            f'dominant-baseline="middle" fill="{text_color}" fill-opacity="0.5" '
            f'data-dream-theme-percent="{theme_id}" data-chart-text-color="{text_color}" '
            'font-size="10" font-weight="600" '
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
  <section id="dream-themes" class="mt-16 border-t border-neutral-200 pt-12">
    <div class="mx-auto max-w-prose text-center">
      <h2 class="font-serif text-2xl font-normal tracking-tight">Themes</h2>
      <p class="mt-2 text-sm text-neutral-500 text-balance">Select a theme or pie slice to explore the responses it appears in. A response can belong to more than one theme.</p>
    </div>
    <div class="mt-8 grid items-start gap-8 md:grid-cols-[minmax(0,20rem)_1fr] md:gap-10">
      <div class="mx-auto w-full max-w-xs">
        <svg viewBox="0 0 320 320" role="group" aria-labelledby="dream-pie-title dream-pie-desc" class="block h-auto w-full overflow-visible">
          <title id="dream-pie-title">Dream theme assignment distribution</title>
          <desc id="dream-pie-desc">A seven-part interactive pie chart ordered from the smallest, lightest theme to the largest, darkest theme, with evenly stepped color intensity. Each semi-transparent percentage label sits at the visual center of its slice. Select a slice to filter the responses and its matching theme in the list.</desc>
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

  <div id="count" class="mt-10 py-2 mx-auto max-w-prose text-center text-xs font-semibold text-neutral-900"></div>

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
    label.setAttribute("fill", selected ? "#ffffff" : label.dataset.chartTextColor);
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
    if (activeDreamTheme && !r.dream_theme_ids.includes(activeDreamTheme)) return false;
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
    dream_theme_summary = load_dream_theme_summary(data, project_root=project_root)
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

    assignment_doc = json.loads((project_root / "data/dream_theme_assignments.json").read_text())
    theme_ids_by_source = {
        (assignment["username"], assignment["created_time"]): assignment["theme_ids"]
        for assignment in assignment_doc["assignments"]
    }
    for row in data:
        row["dream_theme_ids"] = theme_ids_by_source.get(source_key(row), [])

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
