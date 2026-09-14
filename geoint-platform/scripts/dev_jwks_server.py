#!/usr/bin/env python3
"""Lab-only JWKS HTTP server for staging when no real IdP is available.

Generates an RSA keypair, serves:
  GET /jwks.json
  GET /.well-known/openid-configuration
  POST /token  (issues RS256 JWT for local tests)

NOT for production. Bind to localhost by default.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError as e:
    raise SystemExit("pip install cryptography") from e

try:
    import jwt as pyjwt
except ImportError as e:
    raise SystemExit("pip install PyJWT") from e


def _b64url_uint(val: int) -> str:
    length = (val.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(val.to_bytes(length, "big")).rstrip(b"=").decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--audience", default="geoint-api")
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--roles", default="admin,operator")
    args = ap.parse_args()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "geoint-lab-1",
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(pub.n),
        "e": _b64url_uint(pub.e),
    }
    issuer = f"http://{args.host}:{args.port}/"
    jwks = {"keys": [jwk]}

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *a) -> None:  # noqa: A003
            print("[%s] %s" % (self.log_date_time_string(), fmt % a))

        def _json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/jwks.json", "/.well-known/jwks.json"):
                self._json(200, jwks)
            elif self.path == "/.well-known/openid-configuration":
                self._json(
                    200,
                    {
                        "issuer": issuer,
                        "jwks_uri": f"{issuer}jwks.json",
                        "token_endpoint": f"{issuer}token",
                    },
                )
            elif self.path == "/health":
                self._json(200, {"status": "ok", "lab_jwks": True})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/token":
                self._json(404, {"error": "not found"})
                return
            now = int(time.time())
            token = pyjwt.encode(
                {
                    "iss": issuer.rstrip("/"),
                    "aud": args.audience,
                    "sub": "lab-user",
                    "tenant_id": args.tenant,
                    "roles": [r.strip() for r in args.roles.split(",") if r.strip()],
                    "iat": now,
                    "exp": now + 3600,
                },
                priv_pem,
                algorithm="RS256",
                headers={"kid": "geoint-lab-1"},
            )
            self._json(200, {"access_token": token, "token_type": "bearer", "expires_in": 3600})

    print(f"Lab JWKS at http://{args.host}:{args.port}/jwks.json")
    print(f"Set JWT_JWKS_URL=http://{args.host}:{args.port}/jwks.json")
    print(f"    JWT_ISSUER={issuer.rstrip('/')}")
    print(f"    JWT_AUDIENCE={args.audience}")
    HTTPServer((args.host, args.port), H).serve_forever()


if __name__ == "__main__":
    main()
