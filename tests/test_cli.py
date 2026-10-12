"""Offline tests for the CLI flags, retry helper and api-key handling.

Every test patches the network boundary (urllib.request.urlopen) or runs
srma_gap.main() against a fake esearch response, so the suite needs no
internet access. The secret redaction paths are asserted directly: the
api_key must reach the request params but must never appear in any output.
"""
import http.client
import io
import json
import urllib.error
import urllib.parse
import urllib.request

import pytest

import srma_gap
from srma_gap import main

ESEARCH_OK = json.dumps(
    {"esearchresult": {"count": "42"}}
).encode()


class FakeResponse:
    """Minimal context-manager stand-in for an http response."""

    def __init__(self, body: bytes, headers=None):
        self._body = io.BytesIO(body)
        self.headers = headers or {}

    def read(self, *args):
        return self._body.read(*args)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._body.close()
        return False


def test_json_flag_emits_valid_json_with_expected_keys(monkeypatch, capsys):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: FakeResponse(ESEARCH_OK),
    )
    # pubmed prior-MA, pubmed pool and PROSPERO all succeed offline.
    monkeypatch.setattr(srma_gap, "prospero_registrations", lambda topic, timeout=None: 7)
    monkeypatch.setattr("sys.argv", ["srma_gap.py", "my topic", "--json"])

    rc = main()
    out = capsys.readouterr().out

    assert rc == 0
    doc = json.loads(out)
    assert doc["topic"] == "my topic"
    assert doc["prior_ma"] == 42
    assert doc["pool"] == 42
    assert doc["registrations"] == 7
    assert doc["pool_pt"] == "randomized controlled trial[pt]"
    assert doc["verdict"] == srma_gap.verdict(42, 7, 42)
    assert doc["errors"] == []


def test_json_flag_reports_partial_failure_without_verdict(monkeypatch, capsys):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: (_ for _ in ()).throw(
            urllib.error.URLError("network down")
        ),
    )
    monkeypatch.setattr("sys.argv", ["srma_gap.py", "topic", "--json"])

    rc = main()
    doc = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert doc["prior_ma"] == -1 and doc["registrations"] == -1 and doc["pool"] == -1
    assert doc["verdict"] is None
    assert len(doc["errors"]) == 3


def test_retry_helper_retries_transient_failure_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("connection reset")
        return FakeResponse(ESEARCH_OK)

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    monkeypatch.setattr(srma_gap.time, "sleep", lambda s: None)

    data = srma_gap._fetch_json("https://example.test/x")
    assert data == json.loads(ESEARCH_OK)
    assert calls["n"] == 2


def test_retry_helper_retries_on_remote_disconnected(monkeypatch):
    calls = {"n": 0}

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise http.client.RemoteDisconnected("Remote end closed connection")
        return FakeResponse(ESEARCH_OK)

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    monkeypatch.setattr(srma_gap.time, "sleep", lambda s: None)

    assert srma_gap._fetch_json("https://example.test/x")["esearchresult"]["count"] == "42"
    assert calls["n"] == 3


def test_retry_helper_honours_retry_after_on_429(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            err = urllib.error.HTTPError(
                "https://example.test/x", 429, "Too Many Requests",
                {"Retry-After": "7"}, None,
            )
            raise err
        return FakeResponse(ESEARCH_OK)

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    monkeypatch.setattr(srma_gap.time, "sleep", sleeps.append)

    srma_gap._fetch_json("https://example.test/x")
    assert sleeps == [7.0]  # Retry-After beats the 1s default backoff


def test_retry_helper_gives_up_after_max_attempts(monkeypatch):
    calls = {"n": 0}

    def always_fails(req, timeout=None):
        calls["n"] += 1
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", always_fails)
    monkeypatch.setattr(srma_gap.time, "sleep", lambda s: None)

    with pytest.raises(TimeoutError):
        srma_gap._fetch_json("https://example.test/x", retries=3)
    assert calls["n"] == 3


def test_retry_helper_does_not_retry_non_transient_http_error(monkeypatch):
    calls = {"n": 0}

    def bad_request(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError("https://example.test/x", 400, "Bad Request", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", bad_request)

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        srma_gap._fetch_json("https://example.test/x")
    assert excinfo.value.code == 400
    assert calls["n"] == 1


def test_ncbi_api_key_reaches_params_and_never_reaches_output(monkeypatch, capsys):
    secret = "supersecretncbi12345"
    seen = {}

    def capture(req, timeout=None):
        seen["url"] = req.full_url
        return FakeResponse(ESEARCH_OK)

    monkeypatch.setattr(urllib.request, "urlopen", capture)
    monkeypatch.setattr(srma_gap, "prospero_registrations", lambda topic, timeout=None: 5)
    monkeypatch.setattr("sys.argv", ["srma_gap.py", "topic", "--json",
                                     "--ncbi-api-key", secret])

    rc = main()
    out = capsys.readouterr().out

    assert rc == 0
    # the key is genuinely sent, in the URL params
    assert f"api_key={urllib.parse.quote(secret)}" in seen["url"]
    # and it never appears anywhere in the output
    doc = json.loads(out)  # happy path output is valid JSON
    assert doc["prior_ma"] == 42
    assert secret not in out
    assert "[REDACTED]" not in out


def test_api_key_is_redacted_from_error_output(monkeypatch, capsys):
    secret = "supersecretncbi12345"

    def leak(req, timeout=None):
        # urllib.error.URLError embeds the request URL in its str()
        raise urllib.error.URLError(
            "failed to open " + req.full_url + ": temporary failure"
        )

    monkeypatch.setattr(urllib.request, "urlopen", leak)
    monkeypatch.setattr(srma_gap, "prospero_registrations", lambda topic, timeout=None: 5)
    monkeypatch.setattr("sys.argv", ["srma_gap.py", "topic", "--ncbi-api-key", secret])

    rc = main()
    captured = capsys.readouterr()

    assert rc == 1
    assert secret not in captured.out
    assert secret not in captured.err
    assert "[!] PubMed saturation query failed" in captured.err
    assert "api_key=%5BREDACTED%5D" in captured.err or "api_key=[REDACTED]" in captured.err


def test_api_key_is_redacted_from_json_error_field(monkeypatch, capsys):
    secret = "supersecretncbi12345"

    def leak(req, timeout=None):
        raise urllib.error.URLError("failed to open " + req.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", leak)
    monkeypatch.setattr("sys.argv", ["srma_gap.py", "topic", "--json",
                                     "--ncbi-api-key", secret])

    main()
    out = capsys.readouterr().out
    doc = json.loads(out)

    assert secret not in out
    assert any("[REDACTED]" in e for e in doc["errors"])


def test_timeout_argument_is_threaded_to_http_calls(monkeypatch):
    timeouts = []

    def capture(req, timeout=None):
        timeouts.append(timeout)
        return FakeResponse(ESEARCH_OK)

    monkeypatch.setattr(urllib.request, "urlopen", capture)
    monkeypatch.setattr("sys.argv", ["srma_gap.py", "topic", "--timeout", "5"])

    main()
    assert timeouts and set(timeouts) == {5.0}


def test_default_text_output_is_unchanged(monkeypatch, capsys):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: FakeResponse(ESEARCH_OK),
    )
    monkeypatch.setattr(srma_gap, "prospero_registrations", lambda topic, timeout=None: 7)
    monkeypatch.setattr("sys.argv", ["srma_gap.py", "my topic"])

    rc = main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "Scanning gap for topic: 'my topic'" in out
    assert "  Prior MAs / systematic reviews (PubMed) : 42" in out
    assert "  Overlapping PROSPERO registrations      : 7" in out
    assert "  Primary-study pool (randomized controlled trial[pt]) : 42" in out
    assert "VERDICT: " + srma_gap.verdict(42, 7, 42) in out
