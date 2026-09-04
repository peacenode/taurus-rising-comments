# Taurus Rising — TikTok Comment Dataset

Survey-style comment data collected from a TikTok post asking Taurus risings for
three placements (Venus, North Node, Saturn), their dreams, and the lessons
they've attracted.

## Source

- Post: https://www.tiktok.com/@thebaileygrind_/video/7660139501171395853
  (short link: https://www.tiktok.com/t/ZTSCSNEJn/)
- Collected: 2026-07-08/12 and 2026-09-04 via stablesocial.dev `/api/tiktok/post-comments`
  (Data365 provider), paid through agentcash ($0.06/page). Incremental pulls
  on Jul 8 built up 91 comments; a 3-page re-pull on Jul 9 (~03:20 UTC) added
  52; a newest-first top-up (~04:50 UTC) added 9 more; a full 5-page re-pull
  on Jul 9 (~23:24 UTC) added 92 more; a newest-first top-up on Jul 10
  (~12:43 UTC) added 44 more; a complete eight-page cursor walk on Jul 12
  added 67 recent and previously missed comments; a 3-page newest-first
  overlap walk on Sep 4 added 112 more top-level comments, stopping after the
  first overlap with the Jul 12 set
- Coverage: 467 top-level comments accounted for through the Sep 4 overlap
  walk, deduped on username + timestamp + verbatim text. TikTok's displayed
  comment count also includes reply threads, which the provider cannot
  reliably return (see caveats)

## Files

- `data/extracted.json` — one record per comment: author metadata, verbatim
  `text`, and extracted fields (`venus_sign/house`, `nn_sign/house`,
  `saturn_sign/house`, `dreams`, `lessons_attracted`, `life_events`, `notes`)
- `data/extracted.csv` — same data flattened for spreadsheets
- `data/dream_themes_v2.json` — current seven-theme dominant-outcome taxonomy,
  public descriptions, scoring rubric, and private classification boundaries
- `data/dream_theme_calibration_v2.json` — 38 source-linked calibration anchors;
  these rows are excluded from the 200-response agreement evaluation set
- `data/dream_theme_assignments_v2.json` — current primary, co-dominant, and
  private supporting classifications for the reviewed July Dream responses
- `data/dream_theme_review_v2.json` — both full independent passes, the baseline
  and calibrated reconsideration trail, agreement metrics, adjudications, and
  source/taxonomy/calibration digests
- `data/dream_themes.json`, `data/dream_theme_assignments.json`, and
  `data/dream_theme_review.json` — preserved version 1 multi-label provenance;
  the page no longer reads these files
- `data/new_batch6.json` — the 67 reviewed rows added by the Jul 12 refresh
- `data/new_batch6_page*_raw.json` — all eight provider pages from the Jul 12
  cursor walk, retained before normalization
- `data/new_batch7.json` — the 112 extracted rows added by the Sep 4 refresh
- `data/new_batch7_page*_raw.json` — the three provider pages from the Sep 4
  newest-first overlap walk, retained before normalization
- `data/new_batch6_reply_test_raw.json` — the empty reply-endpoint result for
  a parent comment reporting 10 replies
- `avatars/` — commenter profile pictures scraped from public TikTok profile
  pages by `fetch_avatars.py` for the original July dataset (336/350 users; 14
  profiles had no reachable avatar), plus Bailey's own and the Communion logo.
  Newer Sep 4 users fall back to placeholders until the avatar refresh is run.
  Inlined into `index.html` as data URIs at build time.

Extraction was done by LLM reading of each comment, not regex. Paraphrased
fields (`dreams`, `lessons_attracted`, `life_events`) summarize the commenter's
own words; `text` is always verbatim for re-checking.

Dream themes are assigned by reading each response, not by keyword search.
Version 2 gives each qualifying response one primary outcome and adds a
co-dominant theme only for a separate, comparably emphasized aspiration; weaker
means, settings, beneficiaries, and consequences remain private supporting
evidence. The pie therefore shows the share of themed responses by primary
theme, while each response lists its primary and any co-dominant themes as a
clean comma-separated line. Theme descriptions appear once in the chart list;
scores, evidence, rejected candidates, and detailed boundaries stay out of the
page and deployment. The Sep 4 rows are displayed and included in placement,
search, CSV, and response counts, but their Dream-theme assignments remain
pending; theme filters and the pie chart only include the audited July v2
review set.

## Caveats

- **Reply threads missing.** The complete Jul 12 pull reports 64 parent
  comments with 105 replies. The Sep 4 top-level refresh adds 15 new parent
  comments reporting 23 replies. The provider returns every comment ID as a
  float-rounded number (trailing zeros), so the comment-replies endpoint
  cannot match them; a fresh test against a parent reporting 10 replies
  returned zero items.
  Notably `thethirdperspectiv` and `ila9030` both have reply threads where
  the story continues.
- **House systems are mixed.** Most commenters appear to use whole-sign; two
  (`__drw___`, `queridasiulmariam`) gave both whole-sign and Placidus. Where
  both were given, the whole-sign value is in the main columns and Placidus in
  `notes`.
- **Missing halves are inferred.** When a commenter gave only a house (or only
  a sign), the other value was filled in assuming whole-sign houses for a
  Taurus rising (Taurus=1st … Aries=12th). ~18% of respondents who gave both
  values use Placidus, so a similar share of the 57 inferred values may be off
  by one. The verbatim `text` field always preserves exactly what was stated.
- **Self-reported and uneven.** Some rows are placements-only, one is a proxy
  answer for a boyfriend (`ila9030`), one interpreted "dreams" as literal sleep
  dreams (`destenylazo6`), one gave no placements (`pidepeterpiper`),
  one is technically an Aries rising at 28° (`kellynn.danae`).
- Five commenters have multiple rows: `ana974562` (two Portuguese follow-ups),
  `shannaw987` (full comment plus a
  fragment follow-up, "In Gemini 1st house", 6 minutes later), `susspishiz`
  ("Me 🙋‍♀️" then her Venus placement 4 minutes later), `beloolaaa`
  (a curiosity note, then a fuller placement/dreams comment), and
  `saturdayaddamss` (three placement comments). 467 comments, 461 unique
  users.

## Quick stats (n=467, nulls excluded)

- Venus sign: Aries 56, Scorpio 45, Taurus 41, Sagittarius 38, Capricorn 37
- Venus house: 12th 60, 7th 48, 8th 39, 10th 39, 11th 39
- North Node sign: Leo 55, Capricorn 40, Aries 37, Gemini 37, Taurus 36
- North Node house: 4th 49, 12th 38, 6th 37, 1st 36, 2nd 36
- Saturn sign: Taurus 58, Pisces 55, Aquarius 51, Aries 51, Capricorn 37
- Saturn house: 12th 65, 11th 55, 10th 51, 1st 48, 8th 35
- 319/467 shared dreams, 245/467 named lessons/attraction patterns, 217/467
  described hardships/life events
- Dream themes: 193/238 reviewed July Dream responses have a qualifying
  primary theme — Freedom 70, Self-Sufficiency 36, Home / Belonging 33,
  Cultivation 26, Service 14, Transmission 9, and Stewardship 5. Another 63
  reviewed responses have one co-dominant theme, and 17 have two. The 81 Sep 4
  Dream responses are pending v2 theme review.

## Page

`index.html` — self-contained viewer (inline Tailwind via CDN, needs network
for styles/font). It keeps the six existing placement graphs and adds an
interactive reviewed-primary-theme pie with a selectable theme list. Choosing
either a theme row or its pie slice filters the same response list by that
reviewed primary theme and composes with placement filters and search;
co-dominant themes remain visible on reviewed responses. Both run from the
smallest, lightest group to the largest, fully solid group, using one even
color step per theme. Regenerate after data or theme changes with
`python3 build_page.py` (also rewrites `data/extracted.csv`). The build fails
if reviewed-theme source evidence, provenance, agreement gates, or adjudication
records are incomplete or stale.
