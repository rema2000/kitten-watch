#!/usr/bin/env python3
"""Watch Dyrenes Beskyttelse Aarhus and report what is new.

Two kinds of alert:
  * urgent - a name resembling one we are hunting for (Robina / Ally)
  * normal - any animal that was not on the list last time

The second exists because matching only on the name is fragile: the shelter may
list the cat under a different name entirely, and then a name-only watcher stays
silent forever. New-arrival alerts are low volume - the list holds ~15 animals
and turns over slowly - so they cost little and close that hole.

Verified against the live page 2026-09-04: server-rendered, no JS needed.
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
        if name:
            listings.setdefault(BASE + href if href.startswith("/") else href, name)
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


def push(title: str, body: str, click: str, priority: str = "default", tags: str = "cat") -> None:
    """Send one ntfy notification. Headers stay ASCII - ntfy sends them latin-1."""
    if not NTFY_TOPIC:
        print(f"  NTFY_TOPIC not set - would have sent: {title} / {body}", file=sys.stderr)
        return
    resp = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Tags": tags, "Click": click},
        timeout=30,
    )
    resp.raise_for_status()


def main() -> int:
    try:
        listings = fetch_listings()
    except requests.RequestException as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    if not listings:
        # Fail loudly rather than sitting silent for weeks because the markup
        # changed and the watcher quietly matches nothing.
        print("no listings found - the page markup may have changed", file=sys.stderr)
        return 1

    seen = load_seen()
    first_run = not seen
    print(f"{len(listings)} dyr fundet" + ("  (foerste koersel)" if first_run else ""))

    matches, arrivals = [], []
    for url, name in sorted(listings.items(), key=lambda kv: kv[1].lower()):
        ratio, want = best_match(name)
        is_new = name.lower() not in seen
        hit = ratio >= THRESHOLD

        mark = f"  <-- MATCH {want}" if hit else ("  <-- ny" if is_new else "")
        print(f"  {name:<26} {ratio:.2f}{mark}")

        if hit and is_new:
            matches.append((name, want, ratio, url))
        elif is_new:
            arrivals.append((name, url))

    if first_run:
        # Do not fire 15 pushes the first time - just say the watch is running.
        push(
            "kitten-watch koerer",
            f"Overvaager {len(listings)} dyr hos Dyrenes Beskyttelse Aarhus.\n"
            f"Du faar besked ved hvert nyt dyr, og en hoejlydt alarm hvis et navn "
            f"ligner {' eller '.join(WANTED)}.",
            URL,
            tags="eyes",
        )
        print("  (foerste koersel - sendte kun en opsummering)")
    else:
        for name, want, ratio, url in matches:
            push(f"MATCH: {name}", f"{name} ligner {want} ({ratio:.0%})\n{url}",
                 url, priority="urgent", tags="rotating_light")
            print(f"  alarm sendt: {name}")
        for name, url in arrivals:
            push("Nyt dyr paa internatet", f"{name}\n{url}", url)
            print(f"  besked sendt: {name}")

    seen.update(n.lower() for n in listings.values())
    save_seen(seen)
    print(f"{len(matches)} match, {len(arrivals)} nye dyr")
    return 0


if __name__ == "__main__":
    sys.exit(main())
