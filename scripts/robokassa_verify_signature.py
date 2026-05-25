#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import sys

# Usage: ROBOKASSA_PASSWORD2=... ./scripts/robokassa_verify_signature.py OutSum InvId SignatureValue [Shp_key=value ...]
# Matches ResultURL signature: HASH(OutSum:InvId:Password2:sorted Shp_*).

out_sum, inv_id, provided, *shp = sys.argv[1:]
password2 = os.environ["ROBOKASSA_PASSWORD2"]
algo = os.getenv("ROBOKASSA_HASH_ALGORITHM", "sha256").lower()
parts = [out_sum, inv_id, password2] + sorted(shp)
raw = ":".join(parts).encode("utf-8")
digest = getattr(hashlib, algo)(raw).hexdigest().upper()
print(digest)
print("OK" if digest == provided.upper() else "MISMATCH")
