"""Tests for per-IP rate limiting."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.throttle import IPRateLimiter  # noqa: E402


def test_limiter_allows_then_blocks_then_resets():
    rl = IPRateLimiter(limit=3, window=60)
    t = 1000.0
    assert [rl.check("1.2.3.4", now=t)[0] for _ in range(3)] == [True, True, True]
    allowed, retry = rl.check("1.2.3.4", now=t)
    assert allowed is False and retry > 0
    # different IP is independent
    assert rl.check("9.9.9.9", now=t)[0] is True
    # window reset
    assert rl.check("1.2.3.4", now=t + 61)[0] is True


def test_api_returns_429_when_over_limit(monkeypatch):
    c = TestClient(main.app)
    orig = main._api_limiter.limit
    main._api_limiter.limit = 2
    main._api_limiter._hits.clear()
    try:
        codes = [c.get("/api/health").status_code for _ in range(4)]
        assert codes[:2] == [200, 200]
        assert 429 in codes[2:]
        r = c.get("/api/health")
        # rate-limited responses still carry security headers + Retry-After
        if r.status_code == 429:
            assert r.headers.get("retry-after")
            assert r.headers.get("x-frame-options") == "DENY"
    finally:
        main._api_limiter.limit = orig
        main._api_limiter._hits.clear()
