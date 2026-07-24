# srma-gap

**Is this systematic-review / meta-analysis topic worth locking in?**

Before committing months to a review, `srma-gap` runs the three evidence-gap
checks that actually matter — live, from public registries, with **zero
dependencies and zero API keys**:

| Check | Source | What it tells you |
|-------|--------|-------------------|
| **Saturation** | PubMed E-utilities | How many meta-analyses / systematic reviews already exist on the topic (prior-MA saturation) |
| **Overlap** | PROSPERO API | How many registered protocols would collide with yours (registration overlap) |
| **Pool** | PubMed E-utilities | Roughly how many primary studies (e.g. RCTs) are available to power the analysis |

The verdict follows the evidence-gap heuristic: a good SRMA topic has a
**sizeable primary-study pool** but **few existing MAs** and **few overlapping
registrations**. Large pool + thin MAs = real gap. Saturated MAs = the gap is
probably already filled.

## Install

No install. It's a single Python 3 script using only the standard library.

```bash
python3 srma_gap.py "your topic"
```

(Requires Python 3.8+. Tested on Windows / Linux via `python srma_gap.py`.)

## Usage

```bash
# Basic gap scan (multi-word topics are ANDed automatically)
python3 srma_gap.py "deep brain stimulation"

# Force an exact phrase by wrapping in quotes
python3 srma_gap.py '"deep brain stimulation"'

# Customize how the primary-study pool is sized
python3 srma_gap.py "your topic" --pool-pt "randomized controlled trial[pt]"
```

Example output:

```
Scanning gap for topic: 'deep brain stimulation'

  Prior MAs / systematic reviews (PubMed) : 778
  Overlapping PROSPERO registrations      : 1168
  Primary-study pool (randomized controlled trial[pt]) : 429

VERDICT: SATURATED - lots of MAs and registrations already exist. Only proceed if you can carve a distinct PICO slice.
```

Possible verdicts: `REAL GAP`, `SATURATED`, `MA-SATURATED, registry quiet`,
`WEAK POOL`, `POSSIBLE GAP`.

## Why this exists

Systematic-review teams routinely burn weeks on a topic that already has five
identical MAs and a dozen registered protocols. `srma-gap` is a 30-second
pre-flight that says *"stop, or carve a narrower PICO"* before the search
strategy is even written.

## Data sources & caveats

- **PubMed** (NCBI E-utilities) — public, no key. Counts are exact query hits;
  they reflect your formulation, so phrase the topic like a real search string.
- **PROSPERO** (University of York CRD) — the international prospective register
  of systematic reviews. The search endpoint is undocumented; this tool uses the
  same POST contract the PROSPERO web app uses (including its epoch-ms auth
  token). If York changes the API, this may break — that's the one fragile edge.
- Counts are a **signal, not a verdict**. Always open the top hits and skim
  titles before locking a topic.

## License

MIT — see [LICENSE](LICENSE).
