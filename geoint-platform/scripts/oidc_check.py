#!/usr/bin/env python3
"""Validate IdP OIDC discovery + JWKS reachability before production cutover."""

from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--issuer", required=True, help="Issuer base, e.g. https://idp/realms/x")
    p.add_argument("--jwks-url", default=None, help="Override JWKS URL")
    args = p.parse_args()
    issuer = args.issuer.rstrip("/")
    discovery = f"{issuer}/.well-known/openid-configuration"
    with httpx.Client(timeout=15.0) as client:
        if args.jwks_url:
            jwks_url = args.jwks_url
            print(f"Using explicit JWKS {jwks_url}")
        else:
            r = client.get(discovery)
            print(f"discovery HTTP {r.status_code}")
            if r.status_code != 200:
                print(r.text[:300], file=sys.stderr)
                return 1
            data = r.json()
            jwks_url = data.get("jwks_uri")
            print(f"issuer={data.get('issuer')} jwks_uri={jwks_url}")
            if not jwks_url:
                print("No jwks_uri in discovery", file=sys.stderr)
                return 1
        r = client.get(jwks_url)
        print(f"jwks HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text[:300], file=sys.stderr)
            return 1
        keys = r.json().get("keys") or []
        print(f"JWKS keys: {len(keys)}")
        if not keys:
            return 1
    print("OIDC check OK — set JWT_JWKS_URL to the jwks_uri above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
