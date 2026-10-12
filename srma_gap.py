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
    python srma_gap.py "your topic" --json --ncbi-api-key KEY --timeout 15

Data sources:
    * PubMed E-utilities  (esearch, public, optional api_key for 10 req/s)
    * PROSPERO API        (CRD, York - the international SRMA registry)

This is a single, focused tool. One contribution, one job.

"""

import argparse
import base64
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PROSPERO_SEARCH = "https://www.crd.york.ac.uk/PROSPERO/api/search"

UA = "Mozilla/5.0 (srma-gap/1.1; systematic-review gap checker)"

# HTTP statuses worth another attempt (429 = rate limited, 5xx = server-side).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BACKOFF_BASE = 1.0  # seconds; attempt n sleeps BACKOFF_BASE * 2**n


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _scrub(text: str, secret: str) -> str:
    """Redact a secret from a string so it never reaches stdout/stderr."""
    if secret and secret in text:
        return text.replace(secret, "[REDACTED]")
    return text


def _scrub_error(err: BaseException, secret: str) -> BaseException:
    """Redact a secret from an exception so it is never printed or logged.

    URLError renders ``self.reason`` and HTTPError renders ``self.msg``, so
    both carriers are scrubbed alongside ``args``. If the secret somehow
    survives in str(err), the error is replaced by a RuntimeError whose
    message is redacted - leaking the key is not an option.
    """
    if not secret or secret not in str(err):
        return err
    redacted = _scrub(str(err), secret)
    for attr in ("args", "reason", "msg", "filename", "url"):
        value = getattr(err, attr, None)
        if isinstance(value, str) and secret in value:
            setattr(err, attr, value.replace(secret, "[REDACTED]"))
        elif isinstance(value, tuple):
            setattr(err, attr, tuple(
                v.replace(secret, "[REDACTED]") if isinstance(v, str) else v
                for v in value
            ))
    if secret in str(err):  # last-resort safety net: never leak the key
        return RuntimeError(redacted)
    return err


def _fetch_json(url, params=None, *, data=None, headers=None,
                timeout=30, retries=3, secret=None):
    """Fetch a JSON document (GET with `params`, or POST with `data`).

    Transient failures - urllib.error.URLError,
    http.client.RemoteDisconnected, TimeoutError and HTTP 429/5xx - are
    retried up to `retries` times with exponential backoff (1s, 2s, 4s ...).
    A Retry-After header on 429 is honoured. Non-retryable errors (e.g. any
    4xx other than 429) propagate immediately.

    `secret` (typically the NCBI api_key) is redacted from any exception
    message before it escapes, so it is never printed or logged.
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_STATUS:
                raise _scrub_error(e, secret)
            last_err = _scrub_error(e, secret)
            delay = BACKOFF_BASE * (2 ** attempt)
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:  # HTTP-date form; keep the backoff delay
                        pass
        except (urllib.error.URLError, http.client.RemoteDisconnected,
                TimeoutError) as e:
            last_err = _scrub_error(e, secret)
            delay = BACKOFF_BASE * (2 ** attempt)
        if attempt < retries - 1:
            time.sleep(delay)
    raise last_err


# --------------------------------------------------------------------------- #
# PubMed (prior-MA saturation + primary-study pool)
# --------------------------------------------------------------------------- #
def _pubmed_count(term: str, api_key=None, timeout: float = 30) -> int:
    """Return the number of PubMed hits for an exact-ish query."""
    params = {"db": "pubmed", "retmode": "json", "retmax": "1", "term": term}
    if api_key:
        params["api_key"] = api_key
    data = _fetch_json(
        PUBMED_ESEARCH,
        params,
        headers={"User-Agent": UA, "Accept-Encoding": "identity"},
        timeout=timeout,
        secret=api_key,
    )
    return int(data["esearchresult"]["count"])


def pubmed_prior_ma(topic: str, api_key=None, timeout: float = 30) -> int:
    """Count existing meta-analyses / systematic reviews on the topic.

    The topic is passed through verbatim (no forced quoting): multi-word
    topics are ANDed by PubMed by default, which is the correct pre-flight
    behaviour. If you want an exact phrase, wrap it in quotes yourself,
    e.g.  python srma_gap.py '"deep brain stimulation"'.
    """
    q = f"{topic} AND (meta-analysis[pt] OR systematic review[sb])"
    return _pubmed_count(q, api_key, timeout)


def pubmed_pool(topic: str, pool_pt: str, api_key=None,
                timeout: float = 30) -> int:
    """Count the primary-study pool (e.g. RCTs) available for the topic."""
    q = f"{topic} AND {pool_pt}"
    return _pubmed_count(q, api_key, timeout)


# --------------------------------------------------------------------------- #
# PROSPERO (registration overlap)
# --------------------------------------------------------------------------- #
def _prospero_token() -> str:
    """PROSPERO's search endpoint requires a base64 epoch-ms auth token."""
    return base64.b64encode(str(int(time.time() * 1000)).encode()).decode()


def prospero_registrations(topic: str, timeout: float = 30) -> int:
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
    data = _fetch_json(
        PROSPERO_SEARCH,
        data=body,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "prospero-auth-token": _prospero_token(),
        },
        timeout=timeout,
    )
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
    ap.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit a machine-readable JSON document instead of the text report",
    )
    ap.add_argument(
        "--ncbi-api-key",
        default=None,
        help="NCBI API key; raises the PubMed rate limit from 3 to 10 req/s "
             "(never printed or logged)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="HTTP timeout in seconds for each request (default: 30)",
    )
    args = ap.parse_args()

    topic = args.topic.strip()
    if not topic:
        ap.error("topic must not be empty")

    if not args.as_json:
        print(f"Scanning gap for topic: {topic!r}\n")

    errors = []

    def _run(label: str, fn) -> int:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            message = _scrub(f"{label}: {e}", args.ncbi_api_key)
            if not args.as_json:
                print(f"[!] {message}", file=sys.stderr)
            errors.append(message)
            return -1

    prior_ma = _run(
        "PubMed saturation query failed",
        lambda: pubmed_prior_ma(topic, api_key=args.ncbi_api_key,
                                timeout=args.timeout),
    )
    registrations = _run(
        "PROSPERO overlap query failed",
        lambda: prospero_registrations(topic, timeout=args.timeout),
    )
    pool = _run(
        "PubMed pool query failed",
        lambda: pubmed_pool(topic, args.pool_pt, api_key=args.ncbi_api_key,
                            timeout=args.timeout),
    )

    if args.as_json:
        partial = -1 in (prior_ma, registrations, pool)
        document = {
            "topic": topic,
            "pool_pt": args.pool_pt,
            "prior_ma": prior_ma,
            "registrations": registrations,
            "pool": pool,
            "verdict": None if partial else verdict(prior_ma, registrations, pool),
            "errors": errors,
        }
        print(json.dumps(document, indent=2))
        return 1 if partial else 0

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
