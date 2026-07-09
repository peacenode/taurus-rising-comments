# Taurus Rising — TikTok Comment Dataset

Survey-style comment data collected from a TikTok post asking Taurus risings for
three placements (Venus, North Node, Saturn), their dreams, and the lessons
they've attracted.

## Source

- Post: https://www.tiktok.com/@thebaileygrind_/video/7660139501171395853
  (short link: https://www.tiktok.com/t/ZTSCSNEJn/)
- Collected: 2026-07-08/09 via stablesocial.dev `/api/tiktok/post-comments`
  (Data365 provider), paid through agentcash ($0.06/page). Incremental pulls
  on Jul 8 built up 91 comments; a 3-page re-pull on Jul 9 (~03:20 UTC) added
  52; a newest-first top-up (~04:50 UTC) added 9 more; a full 5-page re-pull
  on Jul 9 (~23:24 UTC) added 92 more
- Coverage: all 244 top-level comments as of ~23:24 UTC Jul 9, deduped on
  username + timestamp. TikTok's displayed comment count also includes
  reply threads, which the provider cannot return (see caveats)

## Files

- `data/extracted.json` — one record per comment: author metadata, verbatim
  `text`, and extracted fields (`venus_sign/house`, `nn_sign/house`,
  `saturn_sign/house`, `dreams`, `lessons_attracted`, `life_events`, `notes`)
- `data/extracted.csv` — same data flattened for spreadsheets
- `avatars/` — commenter profile pictures scraped from public TikTok profile
  pages by `fetch_avatars.py` (231/241 users; 10 profiles had no reachable
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
- Three commenters have two rows each: `shannaw987` (full comment plus a
  fragment follow-up, "In Gemini 1st house", 6 minutes later), `susspishiz`
  ("Me 🙋‍♀️" then her Venus placement 4 minutes later), and `beloolaaa`
  (a curiosity note, then a fuller placement/dreams comment). 244 comments,
  241 unique users.

## Quick stats (n=244, nulls excluded)

- Venus sign: Aries 30, Aquarius 22, Scorpio 22, Virgo 19, Gemini 18
- Venus house: 12th 30, 10th 24, 7th 21, 8th 21, 11th 20
- North Node sign: Capricorn 26, Libra 22, Aries 22, Leo 20, Gemini 19
- North Node house: 6th 25, 12th 22, 7th 22, 9th 22, 2nd 20
- Saturn sign: Aquarius 35, Pisces 32, Aries 27, Taurus 21, Capricorn 21
- Saturn house: 12th 38, 11th 34, 10th 33, 8th 20, 9th 17
- 164/244 shared dreams, 127/244 named lessons/attraction patterns, 115/244
  described hardships/life events

## Page

`index.html` — self-contained viewer (inline Tailwind via CDN, needs network
for styles/font). Regenerate after data changes with `python3 build_page.py`
(also rewrites `data/extracted.csv`).
