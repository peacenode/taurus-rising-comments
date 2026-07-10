# Taurus Rising — TikTok Comment Dataset

Survey-style comment data collected from a TikTok post asking Taurus risings for
three placements (Venus, North Node, Saturn), their dreams, and the lessons
they've attracted.

## Source

- Post: https://www.tiktok.com/@thebaileygrind_/video/7660139501171395853
  (short link: https://www.tiktok.com/t/ZTSCSNEJn/)
- Collected: 2026-07-08/10 via stablesocial.dev `/api/tiktok/post-comments`
  (Data365 provider), paid through agentcash ($0.06/page). Incremental pulls
  on Jul 8 built up 91 comments; a 3-page re-pull on Jul 9 (~03:20 UTC) added
  52; a newest-first top-up (~04:50 UTC) added 9 more; a full 5-page re-pull
  on Jul 9 (~23:24 UTC) added 92 more; a newest-first top-up on Jul 10
  (~12:43 UTC) added 44 more
- Coverage: all 288 top-level comments as of ~12:43 UTC Jul 10, deduped on
  username + timestamp. TikTok's displayed comment count also includes
  reply threads, which the provider cannot return (see caveats)

## Files

- `data/extracted.json` — one record per comment: author metadata, verbatim
  `text`, and extracted fields (`venus_sign/house`, `nn_sign/house`,
  `saturn_sign/house`, `dreams`, `lessons_attracted`, `life_events`, `notes`)
- `data/extracted.csv` — same data flattened for spreadsheets
- `avatars/` — commenter profile pictures scraped from public TikTok profile
  pages by `fetch_avatars.py` (271/284 users; 13 profiles had no reachable
  avatar), plus Bailey's own and the Communion logo. Inlined into
  `index.html` as data URIs at build time.

Extraction was done by LLM reading of each comment, not regex. Paraphrased
fields (`dreams`, `lessons_attracted`, `life_events`) summarize the commenter's
own words; `text` is always verbatim for re-checking.

## Caveats

- **Reply threads missing.** Some comments have replies. The provider
  returns comment IDs as float-rounded numbers (trailing zeros), so the
  comment-replies endpoint can't match them — a test lookup returned empty.
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
- Four commenters have two rows each: `shannaw987` (full comment plus a
  fragment follow-up, "In Gemini 1st house", 6 minutes later), `susspishiz`
  ("Me 🙋‍♀️" then her Venus placement 4 minutes later), `beloolaaa`
  (a curiosity note, then a fuller placement/dreams comment), and
  `saturdayaddamss` (two near-duplicate Venus placement comments). 288
  comments, 284 unique users.

## Quick stats (n=288, nulls excluded)

- Venus sign: Aries 34, Scorpio 26, Sagittarius 24, Aquarius 24, Capricorn 23
- Venus house: 12th 35, 8th 29, 10th 27, 7th 25, 6th 24
- North Node sign: Capricorn 29, Libra 26, Leo 25, Aries 24, Gemini 23
- North Node house: 6th 29, 2nd 25, 9th 24, 7th 24, 12th 24
- Saturn sign: Aquarius 39, Pisces 36, Aries 32, Taurus 29, Capricorn 24
- Saturn house: 12th 45, 11th 37, 10th 36, 1st 22, 8th 22
- 194/288 shared dreams, 158/288 named lessons/attraction patterns, 137/288
  described hardships/life events

## Page

`index.html` — self-contained viewer (inline Tailwind via CDN, needs network
for styles/font). Regenerate after data changes with `python3 build_page.py`
(also rewrites `data/extracted.csv`).
