#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener = urllib.request.build_opener(NoRedirect)
base = (sys.argv[1] if len(sys.argv) > 1 else "https://tools.mirkwood.casa").rstrip("/")


def request(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        response = opener.open(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.code, response.headers, response.read()


status, _, body = request("/api/v1/health")
assert status == 200, (status, body)
assert json.loads(body)["status"] == "healthy", body

for path, payload in [
    ("/api/auth/session", None),
    ("/api/auth/register", {"username": "unauthorized-test", "password": "not-a-real-password"}),
    ("/api/auth/login", {"username": "admin", "password": "admin"}),
]:
    status, _, body = request(path, payload)
    assert status == 401, (path, status, body)

status, headers, _ = request("/api/auth/oidc/login")
assert status == 302, status
assert headers["Location"].startswith("https://auth.mirkwood.casa/application/o/authorize/?"), headers["Location"]
assert "redirect_uri=https%3A%2F%2Ftools.mirkwood.casa%2Fapi%2Fauth%2Foidc%2Fcallback" in headers["Location"], headers["Location"]
assert "Secure" in headers.get("Set-Cookie", ""), "OIDC state cookie must be secure"
print("PASS: HTTPS health, unauthenticated denial, default password rejection, Authentik SSO redirect")
