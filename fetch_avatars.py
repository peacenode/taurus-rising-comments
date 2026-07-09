#!/usr/bin/env python3
"""Fetch commenter avatars from public TikTok profile pages into avatars/.

Signed CDN URLs expire, so images are downloaded once and kept locally.
Re-running skips usernames that already have a file (delete to refresh).
"""
import json
import re
import subprocess
import time
from pathlib import Path

root = Path(__file__).parent
out = root / "avatars"
out.mkdir(exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15")

def curl(url, dest=None):
    cmd = ["curl", "-s", "-L", "--max-time", "20", "-A", UA, url]
    if dest:
        cmd += ["-o", str(dest)]
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout.decode("utf-8", "replace") if not dest else r.returncode == 0

usernames = sorted({r["username"] for r in json.loads((root / "data/extracted.json").read_text())})
print(f"{len(usernames)} unique usernames")

missing = []
for i, u in enumerate(usernames, 1):
    dest = out / f"{u}.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        continue
    html = curl(f"https://www.tiktok.com/@{u}")
    m = re.search(r'"avatarThumb":"([^"]+)"', html)
    if not m:
        print(f"[{i}/{len(usernames)}] {u}: no avatar found")
        missing.append(u)
        continue
    url = m.group(1).encode().decode("unicode_escape")
    ok = curl(url, dest)
    size = dest.stat().st_size if dest.exists() else 0
    if not ok or size < 500:  # tiny/failed downloads are junk
        dest.unlink(missing_ok=True)
        print(f"[{i}/{len(usernames)}] {u}: download failed")
        missing.append(u)
    else:
        print(f"[{i}/{len(usernames)}] {u}: {size:,} bytes")
    time.sleep(0.8)

print(f"done — {len(usernames) - len(missing)} avatars, {len(missing)} missing: {missing}")
