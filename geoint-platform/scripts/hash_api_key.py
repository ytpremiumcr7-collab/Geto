#!/usr/bin/env python3
"""Genera entrada API_KEY_HASHES: sha256hex:tenant:roles"""

import hashlib
import sys


def main():
    if len(sys.argv) < 3:
        print("Usage: hash_api_key.py <raw_secret> <tenant> [roles]", file=sys.stderr)
        sys.exit(1)
    raw, tenant = sys.argv[1], sys.argv[2]
    roles = sys.argv[3] if len(sys.argv) > 3 else "operator"
    h = hashlib.sha256(raw.encode()).hexdigest()
    print(f"{h}:{tenant}:{roles}")


if __name__ == "__main__":
    main()
