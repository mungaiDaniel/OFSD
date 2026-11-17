"""Every API route except login/registration/health must reject anonymous requests."""
import re

import pytest

PUBLIC = {("POST", "/api/v1/login"), ("POST", "/api/v1/users"), ("GET", "/api/v1/health")}


def _concrete(rule: str) -> str:
    return re.sub(r"<[^>]+>", lambda m: "1" if m.group(0).startswith(("<int", "<float")) else "x", rule)


def _protected_routes(app):
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1"):
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            if (method, rule.rule) not in PUBLIC:
                yield method, rule.rule


def test_all_routes_require_authentication(app, client):
    unprotected = []
    for method, rule in _protected_routes(app):
        res = client.open(_concrete(rule), method=method)
        if res.status_code != 401:
            unprotected.append(f"{method} {rule} -> {res.status_code}")
    assert not unprotected, "Routes reachable without a JWT:\n" + "\n".join(unprotected)


def test_health_is_public(client):
    assert client.get("/api/v1/health").status_code == 200


def test_errors_are_json(client):
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.is_json and res.get_json()["status"] == 404
