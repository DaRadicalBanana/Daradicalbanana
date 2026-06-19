"""Security hardening tests: headers, debug gating, no secret leakage."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)


def test_security_headers_present():
    for path in ("/", "/api/health"):
        r = c.get(path)
        h = r.headers
        assert "content-security-policy" in {k.lower() for k in h}
        assert h.get("x-content-type-options") == "nosniff"
        assert h.get("x-frame-options") == "DENY"
        assert h.get("referrer-policy") == "no-referrer"


def test_csp_blocks_inline_and_framing():
    csp = c.get("/").headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp  # no inline scripts/handlers needed
    assert "frame-ancestors 'none'" in csp


def test_csp_img_src_is_restricted_to_hosts():
    csp = c.get("/").headers["content-security-policy"]
    assert "img-src 'self' data:" in csp
    assert "img-src 'self' data: https:;" not in csp  # not a blanket https:
    assert "anilist.co" in csp  # specific cover hosts listed


def test_hsts_header_present():
    h = c.get("/").headers
    assert h.get("strict-transport-security", "").startswith("max-age=")


def test_debug_endpoint_disabled_by_default():
    # APP_DEBUG is unset in tests -> /api/debug must not expose internals.
    assert c.get("/api/debug").status_code == 404


def test_health_does_not_leak_token_value():
    body = c.get("/api/health").json()
    assert "animeschedule_token" not in body
    assert body.get("animeschedule_token_present") in (True, False)
    # the literal token value must never appear in the response text
    assert "Bearer" not in c.get("/api/health").text


def test_schedule_rejects_out_of_range_params():
    # Invalid week/year are rejected (422) instead of triggering a 500.
    assert c.get("/api/schedule?year=2026&week=999").status_code == 422
    assert c.get("/api/schedule?year=1800&week=10").status_code == 422
    assert c.get("/api/schedule?year=2026&week=25").status_code == 200


def test_releases_clamps_far_anchor():
    # A far-future anchor is clamped (no 500, no unbounded fan-out) and paging
    # forward is disabled at the bound.
    r = c.get("/api/releases?range=monthly&anchor=9999-01-01")
    assert r.status_code == 200
    body = r.json()
    assert body["anchor"] < "9999-01-01"  # clamped toward today
    assert body["has_next"] is False  # can't page past the window
    # a far-past anchor disables paging backward
    past = c.get("/api/releases?range=monthly&anchor=1000-01-01").json()
    assert past["has_prev"] is False
    # today is freely navigable both ways
    now = c.get("/api/releases?range=daily").json()
    assert now["has_prev"] is True and now["has_next"] is True
    # malformed anchor falls back to today (still 200)
    assert c.get("/api/releases?range=daily&anchor=not-a-date").status_code == 200


def test_no_inline_onerror_in_app_js():
    js = (os.path.join(os.path.dirname(__file__), "..", "app", "static", "app.js"))
    with open(js) as f:
        src = f.read()
    assert "onerror=" not in src  # CSP-incompatible inline handler removed
