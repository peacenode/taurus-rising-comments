#!/usr/bin/env python3
"""Embed data/extracted.json into a self-contained index.html (inline Tailwind)."""
import base64
import json
import csv
from pathlib import Path

root = Path(__file__).parent
data = json.loads((root / "data/extracted.json").read_text())

# keep the CSV in sync
fields = ["username","display_name","created_time","digg_count","reply_count",
          "venus_sign","venus_house","nn_sign","nn_house","saturn_sign","saturn_house",
          "dreams","lessons_attracted","life_events","notes","text"]
with open(root / "data/extracted.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(data)

# inline avatars (fetched by fetch_avatars.py) as data URIs
for r in data:
    p = root / "avatars" / f"{r['username']}.jpg"
    r["avatar"] = ("data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()) if p.exists() else None

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Taurus Dreamscapes</title>
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
  const fields = [
    ...chipDef.map(([label, , sk, hk]) => [label, fmtPlacement(r[sk], r[hk])]),
    ["Dreams", r.dreams && esc(r.dreams)],
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

function render() {
  const term = q.value.trim().toLowerCase();
  const active = Object.entries(filters).filter(([, v]) => v != null);
  clearBtn.classList.toggle("hidden", !active.length && !term);
  const shown = DATA.filter(r => {
    for (const [k, v] of active) if (r[k] !== v) return false;
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
  renderStats();
  render();
});

const updatedEl = document.getElementById("updated");
updatedEl.textContent = rel(updatedEl.dataset.time) + " ago";

renderStats();
render();
</script>
</body>
</html>
"""

bailey = root / "avatars" / "thebaileygrind_.jpg"
bailey_img = (f'<img src="data:image/jpeg;base64,{base64.b64encode(bailey.read_bytes()).decode()}" alt="" '
              'class="size-5 rounded-full object-cover">') if bailey.exists() else ""

logo = root / "avatars" / "communion_logo.png"
logo_b64 = base64.b64encode(logo.read_bytes()).decode() if logo.exists() else ""
logo_img = (f'<img src="data:image/png;base64,{logo_b64}" alt="Communion" class="size-10 mx-auto">') if logo_b64 else ""
logo_sm = (f'<img src="data:image/png;base64,{logo_b64}" alt="" class="size-7">') if logo_b64 else ""

# newest comment in the set = how current the data is; rendered relative by rel()
updated = max(r["created_time"] for r in data)

html = (TEMPLATE
        .replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__BAILEY_AVATAR__", bailey_img)
        .replace("__COMMUNION_LOGO_SM__", logo_sm)
        .replace("__COMMUNION_LOGO__", logo_img)
        .replace("__UPDATED__", updated)
        .replace("__COUNT__", str(len(data))))
(root / "index.html").write_text(html)
print(f"wrote index.html ({len(html):,} bytes, {len(data)} records)")
