# Contributing to srma-gap

Thanks for your interest in improving `srma-gap`! This is a small, focused tool,
and we'd like to keep it that way.

## Ways to contribute

- **Bug reports & feature ideas** — open a GitHub issue. Keep it concrete: what
  you ran, what you expected, what happened.
- **Code** — see the workflow below.
- **Docs** — typos, clearer examples, and better explanations are always welcome.

## Development setup

```bash
git clone https://github.com/harisawan-bit/srma-gap.git
cd srma-gap
python -m venv .venv && source .venv/bin/activate   # optional
pip install -e .
pip install pytest
```

## Local checks before you push

The CI runs `pip install -e .` then `pytest -q` against Python 3.8 / 3.11 /
3.12. Run the same locally:

```bash
pip install -e .
pytest -q
```

All `verdict()` tests are **offline** (pure functions, no network), so they run
anywhere. Do not add tests that require network access in CI.

## Pull-request guidelines

1. Branch from `master`: `git checkout -b feat/your-thing`.
2. Keep changes scoped — one logical change per PR.
3. Make sure `pytest -q` is green locally.
4. Open the PR against `master`. A maintainer will review and merge once CI is
   fully green.

## Design constraints

- **Stdlib only.** No third-party runtime dependencies. Adding one needs a
  strong justification and maintainer sign-off.
- **No network in tests.** The verdict logic is a pure function; keep it that
  way so CI never depends on PubMed/PROSPERO being up.
- **Single job.** This tool does one thing: decide whether an SRMA topic is a
  real evidence gap. Don't bolt on unrelated features.

## Code style

Follow PEP 8. The existing code uses 4-space indentation and `snake_case`. Keep
it consistent with the surrounding file.
