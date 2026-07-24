#!/usr/bin/env python3
"""
srma-gap  -  Is this systematic-review / meta-analysis topic worth locking?

Before you commit months to a review, srma-gap answers three questions from
live public registries (no API key, no installs, just Python 3 stdlib):

  1. SATURATION  - how many meta-analyses / systematic reviews already exist
                    on PubMed for this topic? (prior-MA saturation check)
  2. OVERLAP     - how many PROSPERO protocols are already registered that
                    would collide with yours? (registration overlap check)
  3. POOL        - roughly how many primary studies (RCTs) are available to
                    feed the analysis? (evidence-base size)

The verdict logic follows the evidence-gap heuristic: a good SRMA topic has
a SIZEABLE primary-study pool but FEW existing MAs and FEW overlapping
registrations. If the pool is large but MAs/registrations are thin, that is a
real gap. If MAs are already saturated, the gap is probably filled.

Usage:
    python srma_gap.py "deep brain stimulation"
    python srma_gap.py "your topic" --pool-pt "randomized controlled trial[pt]"

Data sources:
    * PubMed E-utilities  (esearch, public, no key)
    * PROSPERO API        (CRD, York - the international SRMA registry)

This is a single, focused tool. One contribution, one job.
"""

import argparse
import base64
import json
import sys
import time
import urllib.parse
import urllib.request

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PROSPERO_SEARCH = "https://www.crd.york.ac.uk/PROSPERO/api/search"

UA = "Mozilla/5.0 (srma-gap/0.1; systematic-review gap checker)"


# --------------------------------------------------------------------------- #
# PubMed (prior-MA saturation + primary-study pool)
# --------------------------------------------------------------------------- #
def _pubmed_count(term: str) -> int:
    """Return the number of PubMed hits for an exact-ish query."""
    params = urllib.parse.urlencode(
        {"db": "pubmed", "retmode": "json", "retmax": "1", "term": term}
    )
    url = f"{PUBMED_ESEARCH}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return int(data["esearchresult"]["count"])


def pubmed_prior_ma(topic: str) -> int:
    """Count existing meta-analyses / systematic reviews on the topic."""
    q = f'"{topic}" AND (meta-analysis[pt] OR systematic review[sb])'
    return _pubmed_count(q)


def pubmed_pool(topic: str, pool_pt: str) -> int:
    """Count the primary-study pool (e.g. RCTs) available for the topic."""
    q = f'"{topic}" AND {pool_pt}'
    return _pubmed_count(q)


# --------------------------------------------------------------------------- #
# PROSPERO (registration overlap)
# --------------------------------------------------------------------------- #
def _prospero_token() -> str:
    """PROSPERO's search endpoint requires a base64 epoch-ms auth token."""
    return base64.b64encode(str(int(time.time() * 1000)).encode()).decode()


def prospero_registrations(topic: str) -> int:
    """Count PROSPERO-registered (or published) reviews matching the topic."""
    payload = {
        "term": topic,
        "actual": topic,
        "page": 1,
        "nperpage": 1,
        "sort": "relevance",
        "sortorder": "asc",
        "filters": {},
        "download": False,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        PROSPERO_SEARCH,
        data=body,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "prospero-auth-token": _prospero_token(),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    # Response is a list; the hits total lives here:
    return int(data[0]["retvals"]["hits"]["total"]["value"])


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #
def verdict(prior_ma: int, registrations: int, pool: int) -> str:
    saturated_ma = prior_ma >= 100
    saturated_reg = registrations >= 100
    thin_pool = pool < 20

    if thin_pool:
        return ("WEAK POOL - too few primary studies to power a credible MA. "
                "Reconsider the PICO or widen inclusion.")
    if saturated_ma and saturated_reg:
        return ("SATURATED - lots of MAs and registrations already exist. "
                "Only proceed if you can carve a distinct PICO slice.")
    if saturated_ma and not saturated_reg:
        return ("MA-SATURATED, registry quiet - MAs exist but few new "
                "registrations. Likely incremental unless you add a novel angle.")
    if (not saturated_ma) and pool >= 50:
        return ("REAL GAP - sizeable study pool, few existing MAs. "
                "Strong candidate to lock in.")
    return ("POSSIBLE GAP - thin on MAs, but check the pool is genuinely "
            "extractable before committing.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check whether a systematic-review / meta-analysis topic is a real evidence gap."
    )
    ap.add_argument("topic", help='topic phrase, e.g. "deep brain stimulation"')
    ap.add_argument(
        "--pool-pt",
        default="randomized controlled trial[pt]",
        help="PubMed publication-type filter used to size the primary-study pool "
             "(default: randomized controlled trial[pt])",
    )
    args = ap.parse_args()

    topic = args.topic.strip()
    if not topic:
        ap.error("topic must not be empty")

    print(f"Scanning gap for topic: {topic!r}\n")

    try:
        prior_ma = pubmed_prior_ma(topic)
    except Exception as e:  # noqa: BLE001
        print(f"[!] PubMed saturation query failed: {e}", file=sys.stderr)
        prior_ma = -1

    try:
        registrations = prospero_registrations(topic)
    except Exception as e:  # noqa: BLE001
        print(f"[!] PROSPERO overlap query failed: {e}", file=sys.stderr)
        registrations = -1

    try:
        pool = pubmed_pool(topic, args.pool_pt)
    except Exception as e:  # noqa: BLE001
        print(f"[!] PubMed pool query failed: {e}", file=sys.stderr)
        pool = -1

    print("  Prior MAs / systematic reviews (PubMed) :", prior_ma)
    print("  Overlapping PROSPERO registrations      :", registrations)
    print("  Primary-study pool (" + args.pool_pt + ") :", pool)
    print()

    if -1 in (prior_ma, registrations, pool):
        print("Partial results - a source failed (see errors above).")
        return 1

    print("VERDICT:", verdict(prior_ma, registrations, pool))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
