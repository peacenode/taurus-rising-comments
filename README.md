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
  52; a newest-first top-up (~04:50 UTC) added 9 more
- Coverage: all 152 top-level comments as of ~04:45 UTC Jul 9, deduped on
  username + timestamp. TikTok's displayed comment count also includes
  reply threads, which the provider cannot return (see caveats)

## Files

- `data/extracted.json` — one record per comment: author metadata, verbatim
  `text`, and extracted fields (`venus_sign/house`, `nn_sign/house`,
  `saturn_sign/house`, `dreams`, `lessons_attracted`, `life_events`, `notes`)
- `data/extracted.csv` — same data flattened for spreadsheets
- `avatars/` — commenter profile pictures scraped from public TikTok profile
  pages by `fetch_avatars.py` (142/149 users; 7 profiles had no reachable
  avatar), plus Bailey's own and the Communion logo. Inlined into
  `index.html` as data URIs at build time.

Extraction was done by LLM reading of each comment, not regex. Paraphrased
fields (`dreams`, `lessons_attracted`, `life_events`) summarize the commenter's
own words; `text` is always verbatim for re-checking.

## Caveats

- **Reply threads missing.** 8 comments have replies (12 total). The provider
  returns comment IDs as float-rounded numbers (trailing zeros), so the
  comment-replies endpoint can't match them — a test lookup returned empty.
  Notably `thethirdperspectiv` (3 replies, story continues) and `ila9030`
  (3 replies).
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
- Two commenters have two rows each: `shannaw987` (full comment plus a fragment
  follow-up, "In Gemini 1st house", 6 minutes later) and `susspishiz` ("Me 🙋‍♀️"
  then her Venus placement 4 minutes later). 152 comments, 149 unique users.

## Quick stats (n=152, nulls excluded)

- Venus sign: Aries 22, Scorpio 16, Aquarius 16, Leo 12, Virgo 11
- Venus house: 12th 22, 7th 16, 10th 15, 11th 13, 6th 12
- North Node sign: Capricorn 18, Leo 14, Sag 13, Libra 13, Virgo 12
- North Node house: 9th 16, 6th 16, 5th 13, 8th 12, 12th 12
- Saturn sign: Aquarius 29, Aries 21, Pisces 17, Taurus 13, Scorpio 13
- Saturn house: 10th 26, 12th 26, 11th 20, 9th 13, 1st 10
- 102/152 shared dreams, 79/152 named lessons/attraction patterns, 78/152
  described hardships/life events

## Page

`index.html` — self-contained viewer (inline Tailwind via CDN, needs network
for styles/font). Regenerate after data changes with `python3 build_page.py`
(also rewrites `data/extracted.csv`).
