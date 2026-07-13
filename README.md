# Taurus Rising — TikTok Comment Dataset

Survey-style comment data collected from a TikTok post asking Taurus risings for
three placements (Venus, North Node, Saturn), their dreams, and the lessons
they've attracted.

## Source

- Post: https://www.tiktok.com/@thebaileygrind_/video/7660139501171395853
  (short link: https://www.tiktok.com/t/ZTSCSNEJn/)
- Collected: 2026-07-08/12 via stablesocial.dev `/api/tiktok/post-comments`
  (Data365 provider), paid through agentcash ($0.06/page). Incremental pulls
  on Jul 8 built up 91 comments; a 3-page re-pull on Jul 9 (~03:20 UTC) added
  52; a newest-first top-up (~04:50 UTC) added 9 more; a full 5-page re-pull
  on Jul 9 (~23:24 UTC) added 92 more; a newest-first top-up on Jul 10
  (~12:43 UTC) added 44 more; a complete eight-page cursor walk on Jul 12
  added 67 recent and previously missed comments
- Coverage: all 355 top-level comments returned by the complete cursor walk
  as of 20:28 UTC Jul 12, deduped on username + timestamp + verbatim text.
  TikTok's displayed comment count also includes reply threads, which the
  provider cannot reliably return (see caveats)

## Files

- `data/extracted.json` — one record per comment: author metadata, verbatim
  `text`, and extracted fields (`venus_sign/house`, `nn_sign/house`,
  `saturn_sign/house`, `dreams`, `lessons_attracted`, `life_events`, `notes`)
- `data/extracted.csv` — same data flattened for spreadsheets
- `data/new_batch6.json` — the 67 reviewed rows added by the Jul 12 refresh
- `data/new_batch6_page*_raw.json` — all eight provider pages from the Jul 12
  cursor walk, retained before normalization
- `data/new_batch6_reply_test_raw.json` — the empty reply-endpoint result for
  a parent comment reporting 10 replies
- `avatars/` — commenter profile pictures scraped from public TikTok profile
  pages by `fetch_avatars.py` (336/350 users; 14 profiles had no reachable
  avatar), plus Bailey's own and the Communion logo. Inlined into
  `index.html` as data URIs at build time.

Extraction was done by LLM reading of each comment, not regex. Paraphrased
fields (`dreams`, `lessons_attracted`, `life_events`) summarize the commenter's
own words; `text` is always verbatim for re-checking.

## Caveats

- **Reply threads missing.** The complete Jul 12 pull reports 64 parent
  comments with 105 replies. The provider returns every comment ID as a
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
- Four commenters have multiple rows: `shannaw987` (full comment plus a
  fragment follow-up, "In Gemini 1st house", 6 minutes later), `susspishiz`
  ("Me 🙋‍♀️" then her Venus placement 4 minutes later), `beloolaaa`
  (a curiosity note, then a fuller placement/dreams comment), and
  `saturdayaddamss` (three placement comments). 355 comments, 350 unique
  users.

## Quick stats (n=355, nulls excluded)

- Venus sign: Aries 45, Scorpio 33, Taurus 33, Sagittarius 32, Pisces 28
- Venus house: 12th 49, 7th 34, 8th 34, 10th 30, 1st 29
- North Node sign: Leo 38, Capricorn 36, Aries 32, Gemini 28, Taurus 28
- North Node house: 12th 33, 4th 31, 6th 31, 7th 31, 2nd 29
- Saturn sign: Aquarius 46, Pisces 44, Taurus 43, Aries 39, Capricorn 28
- Saturn house: 12th 55, 10th 44, 11th 43, 1st 33, 8th 28
- 238/355 shared dreams, 189/355 named lessons/attraction patterns, 161/355
  described hardships/life events

## Page

`index.html` — self-contained viewer (inline Tailwind via CDN, needs network
for styles/font). Regenerate after data changes with `python3 build_page.py`
(also rewrites `data/extracted.csv`).
