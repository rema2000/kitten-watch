#!/usr/bin/env python3
"""Watch Dyrenes Beskyttelse Aarhus for cats whose name resembles Robina or Ally.

Verified against the live page on 2026-09-04: it is server-rendered, so plain
requests + BeautifulSoup is enough, no browser needed.
"""
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = ("https://www.dyrenesbeskyttelse.dk/adopter-et-dyr"
       "?species%5B1139%5D=1139&shelter%5B83626%5D=83626")
BASE = "https://www.dyrenesbeskyttelse.dk"
LINK_RE = re.compile(r"/adopter/dyrenes-beskyttelse-aarhus/d-\d+$")

WANTED = ["Robina", "Ally"]
THRESHOLD = 0.75
SEEN_FILE = Path("seen_names.json")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
UA = "kitten-watch/1.0 (personal adoption alert)"

# The link text carries furniture around the name. Real examples:
#   "Sven Internat Dyrenes Beskyttelse Aarhus"
#   "Paa vej til nyt hjem Seb Internat Dyrenes Beskyttelse Aarhus"
#   "Luna Har ventet paa nyt hjem (dage) 14 Internat Dyrenes Beskyttelse Aarhus"
STATUS_PREFIX = re.compile(r"^(På vej til nyt hjem|Reserveret|Nyhed)\s+", re.I)
TAIL = re.compile(r"\s*(?:Har ventet på nyt hjem|Internat)\b", re.I)


def clean_name(text: str) -> str:
    """Pull the animal's name out of a listing link's text."""
    s = " ".join(text.split())
    s = STATUS_PREFIX.sub("", s)
    s = TAIL.split(s)[0].strip()
    # Some listings repeat the name ("Sven Sven ..."). Collapse that if it
    # happens, but do not assume it: as of Sept 2026 they do not.
    words = s.split()
    if words and len(words) % 2 == 0:
        half = len(words) // 2
        if [w.lower() for w in words[:half]] == [w.lower() for w in words[half:]]:
            return " ".join(words[:half])
    return s


def fetch_listings() -> dict:
    """Return {absolute_url: name} for every animal on the page."""
    resp = requests.get(URL, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].split("?")[0].rstrip("/")
        if not LINK_RE.search(href):
            continue
        name = clean_name(anchor.get_text(" ", strip=True))
        if not name:
            continue
        url = BASE + href if href.startswith("/") else href
        listings.setdefault(url, name)
    return listings


def best_match(name: str):
    """Closest wanted name and its similarity ratio."""
    best_ratio, best_name = 0.0, None
    for want in WANTED:
        ratio = SequenceMatcher(None, name.lower(), want.lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_name = ratio, want
    return best_ratio, best_name


def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            print(f"  could not read {SEEN_FILE} ({exc}) - starting fresh", file=sys.stderr)
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def notify(name: str, want: str, ratio: float, url: str) -> None:
    """Push to ntfy. Headers stay ASCII - ntfy sends them as latin-1."""
    if not NTFY_TOPIC:
        print("  NTFY_TOPIC is not set - skipping notification", file=sys.stderr)
        return
    body = f"{name} ligner {want} ({ratio:.0%})\n{url}"
    resp = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={
            "Title": "Muligt match paa internatet",
            "Priority": "urgent",
            "Tags": "cat",
            "Click": url,
        },
        timeout=30,
    )
    resp.raise_for_status()
    print(f"  notified: {name}")


def main() -> int:
    try:
        listings = fetch_listings()
    except requests.RequestException as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    if not listings:
        # Better to fail loudly than to sit silent for weeks because the markup
        # changed and the watcher quietly matches nothing.
        print("no listings found - the page markup may have changed", file=sys.stderr)
        return 1

    seen = load_seen()
    print(f"{len(listings)} dyr fundet")
    new = 0
    for url, name in sorted(listings.items(), key=lambda kv: kv[1].lower()):
        ratio, want = best_match(name)
        hit = ratio >= THRESHOLD
        flag = f"  <-- MATCH {want}" if hit else ""
        print(f"  {name:<26} {ratio:.2f}{flag}")
        if hit and name.lower() not in seen:
            notify(name, want, ratio, url)
            seen.add(name.lower())
            new += 1

    save_seen(seen)
    print(f"{new} ny(e) notifikation(er)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
