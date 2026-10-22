#!/usr/bin/env python3
"""AniList home mirror seeder (2026-10-22).

Why: since 2026-10-18 AniList manually 403-blocks Cloudflare Workers egress IPs, so
cortanime.eu runs on the Kitsu backup catalog. This script fetches the exact home
GraphQL body the worker uses (cxHomeQuery) from a non-blocked egress and writes it as
`home-<SEASON>-<year>.json` (+ `_mirrorFetchedAt`). The `al-mirror` branch of
TibikeYH120/cortexanime-native-private is the mirror store; the Worker's alHomeMirror()
reads it from raw.githubusercontent.com when live AniList fails. A GitHub Actions cron
(.github/workflows/al-mirror.yml) runs this every 30 minutes — no secrets required
(GITHUB_TOKEN only). Never stores or prints credentials.
"""
from pathlib import Path
import argparse, datetime, json, urllib.request

SEASON = ["WINTER", "SPRING", "SUMMER", "FALL"]
FIELDS = ("id idMal title{romaji english native} coverImage{large extraLarge} bannerImage "
          "description(asHtml:false) episodes averageScore genres season seasonYear format "
          "status nextAiringEpisode{episode airingAt} studios(isMain:true){nodes{name}}")
# Verbatim from worker.js cxHomeQuery() (CX_HOME_FIELDS expanded). Byte-compatible
# with the worker request body — kept as a plain string so braces survive.
QUERY = 'query($s:MediaSeason,$y:Int){trending:Page(page:1,perPage:25){media(type:ANIME,sort:TRENDING_DESC,status:RELEASING,isAdult:false){id idMal title{romaji english native} coverImage{large extraLarge} bannerImage description(asHtml:false) episodes averageScore genres season seasonYear format status nextAiringEpisode{episode airingAt} studios(isMain:true){nodes{name}}}}seasonal:Page(page:1,perPage:24){media(type:ANIME,season:$s,seasonYear:$y,sort:POPULARITY_DESC,isAdult:false){id idMal title{romaji english native} coverImage{large extraLarge} bannerImage description(asHtml:false) episodes averageScore genres season seasonYear format status nextAiringEpisode{episode airingAt} studios(isMain:true){nodes{name}}}}}'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default='.')
    ap.add_argument('--now-utc', default=None, help='ISO time override (tests)')
    args = ap.parse_args()

    now = datetime.datetime.fromisoformat(args.now_utc) if args.now_utc else datetime.datetime.now(datetime.timezone.utc)
    season = SEASON[(now.month - 1) // 3]
    year = now.year
    body = json.dumps({"query": QUERY, "variables": {"s": season, "y": year}}, separators=(',', ':'))
    req = urllib.request.Request(
        'https://graphql.anilist.co', data=body.encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'User-Agent': 'CortexAnime/0.4.4 (AniList client 54597; cortanime.eu)'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = json.loads(resp.read())
    trend = ((root.get('data') or {}).get('trending') or {}).get('media') or []
    seas = ((root.get('data') or {}).get('seasonal') or {}).get('media') or []
    assert trend and seas, f'AniList returned incomplete home data: trend={len(trend)} seas={len(seas)}'
    assert all(isinstance(m.get('id'), int) and m.get('title') for m in trend[:5]), 'bad media rows'
    root['_mirrorFetchedAt'] = now.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    out = Path(args.out_dir) / f'home-{season}-{year}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(root, ensure_ascii=False, separators=(',', ':')))
    print(f'WROTE {out} trend={len(trend)} seas={len(seas)} season={season} year={year}')

if __name__ == '__main__':
    main()
