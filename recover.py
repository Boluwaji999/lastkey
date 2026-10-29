#!/usr/bin/env python3
"""Open a Lastkey vault without Lastkey.

An independent implementation of SPEC.md (vault format version 2). It needs
Python 3.8+ and the `cryptography` package (pip install cryptography).
Time-locked vaults also need drand's `tle` tool, or any other tlock decrypter,
to recover the time-lock secret once its round is published.

Usage:
  python recover.py card1.txt card2.txt          # files holding guardian cards
  python recover.py < cards.txt                  # or paste cards on stdin
  python recover.py cards.txt --tle path/to/tle  # time-locked: let tle fetch the beacon
  python recover.py cards.txt --kt-file kt.bin   # time-locked: Kt already decrypted
  python recover.py --check test-vectors/vectors.json
"""
import argparse
import base64
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    sys.exit("recover.py needs the 'cryptography' package. Install it with: pip install cryptography")

CARD_RE = re.compile(r"LK(\d+)\.([A-Za-z0-9_-]+)")
KEY_LABEL = b"lastkey/v2"
QUICKNET = {
    "hash": "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971",
    "genesis": 1692803367,
    "period": 3,
}


class VaultError(Exception):
    """A problem the person opening the vault can act on."""


# ---------- cards (SPEC §2, §3) ----------

def b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def parse_card(version, payload):
    if version != "2":
        raise VaultError(f"Card format LK{version} is not supported (only LK2).")
    try:
        data = b64url_decode(payload)
        pos = 0

        def take(n):
            nonlocal pos
            if pos + n > len(data):
                raise ValueError("card is truncated")
            chunk = data[pos:pos + n]
            pos += n
            return chunk

        (header_len,) = struct.unpack(">H", take(2))
        header = json.loads(take(header_len).decode("utf-8"))
        share = take(32)
        iv = take(12)
        (tlock_len,) = struct.unpack(">H", take(2))
        tlock = take(tlock_len)
        vault = data[pos:]
        if not vault:
            raise ValueError("card has no vault data")
    except (ValueError, KeyError, struct.error) as e:
        raise VaultError(f"A card is damaged or incomplete ({e}).") from None
    return {
        "id": header["id"], "title": header.get("title", ""), "owner": header.get("owner", ""),
        "n": int(header["n"]), "t": int(header["t"]), "x": int(header["x"]),
        "guardian": header.get("g", ""), "tl": header.get("tl"),
        "share": share, "iv": iv, "tlock": tlock, "vault": vault,
    }


def find_cards(text):
    return [parse_card(v, p) for v, p in CARD_RE.findall(text)]


# ---------- Shamir over GF(2^8), polynomial 0x11B (SPEC §4) ----------

def gf_mul(a, b):
    product = 0
    while b:
        if b & 1:
            product ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11B
        b >>= 1
    return product


def gf_inv(a):
    # a^254 is the inverse of a in GF(2^8)
    result, power, exp = 1, a, 254
    while exp:
        if exp & 1:
            result = gf_mul(result, power)
        power = gf_mul(power, power)
        exp >>= 1
    return result


def combine_shares(points):
    """points: list of (x, share_bytes). Returns the secret (Lagrange at 0)."""
    xs = [x for x, _ in points]
    if len(set(xs)) != len(xs):
        raise VaultError("Two of the cards have the same card number. Use cards from different guardians.")
    secret = bytearray(len(points[0][1]))
    for i, (xi, yi) in enumerate(points):
        basis = 1
        for k, (xk, _) in enumerate(points):
            if k != i:
                basis = gf_mul(basis, gf_mul(xk, gf_inv(xk ^ xi)))
        for j, byte in enumerate(yi):
            secret[j] ^= gf_mul(byte, basis)
    return bytes(secret)


# ---------- time-lock (SPEC §6) ----------

def armor(age_bytes):
    b64 = base64.b64encode(age_bytes).decode("ascii")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN AGE ENCRYPTED FILE-----\n" + "\n".join(lines) + "\n-----END AGE ENCRYPTED FILE-----\n"


def round_time(r):
    return QUICKNET["genesis"] + (r - 1) * QUICKNET["period"]


def run_tle(tle, age_bytes):
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "vault.age"), os.path.join(d, "kt.bin")
        with open(src, "w", encoding="ascii", newline="\n") as f:
            f.write(armor(age_bytes))
        res = subprocess.run([tle, "--decrypt", "--output", out, src], capture_output=True, text=True)
        if res.returncode != 0:
            raise VaultError(f"tle could not open the time-lock: {(res.stderr or res.stdout).strip()}")
        with open(out, "rb") as f:
            return f.read()


# ---------- opening (SPEC §5, §7) ----------

def open_vault(cards, kt=None):
    if not cards:
        raise VaultError("No Lastkey cards found. Cards start with LK2.")
    ids = {c["id"] for c in cards}
    if len(ids) > 1:
        raise VaultError(f"These cards come from different vaults ({', '.join(sorted(ids))}). Use cards from one vault.")
    by_x = {}
    for c in cards:
        by_x.setdefault(c["x"], c)
    first = cards[0]
    t = first["t"]
    if len(by_x) < t:
        raise VaultError(f"This vault needs {t} different cards; only {len(by_x)} found.")
    chosen = [by_x[x] for x in sorted(by_x)][:t]
    ks = combine_shares([(c["x"], c["share"]) for c in chosen])

    if first["tl"]:
        if kt is None:
            raise VaultError("This vault is time-locked. Provide --kt-file or --tle.")
        if len(kt) != 32:
            raise VaultError(f"The time-lock secret should be 32 bytes, got {len(kt)}.")
    else:
        kt = b""

    key = hashlib.sha256(KEY_LABEL + ks + kt).digest()
    try:
        plain = AESGCM(key).decrypt(first["iv"], first["vault"], first["id"].encode("utf-8"))
    except InvalidTag:
        raise VaultError("These cards don't open the vault. One may be damaged or edited, "
                         "or the time-lock secret is wrong. Try a different set of cards.") from None
    contents = json.loads(plain.decode("utf-8"))
    contents["cards_used"] = [c["guardian"] for c in chosen]
    return contents


# ---------- command line ----------

def check_vectors(path):
    with open(path, encoding="utf-8") as f:
        vectors = json.load(f)
    failures = 0
    for v in vectors["vectors"]:
        kt = bytes.fromhex(v["kt"]) if v.get("kt") else None
        try:
            cards = [c for text in v["cards"] for c in find_cards(text)]
            got = open_vault(cards, kt)
            ok = "expect_body" in v and got["body"] == v["expect_body"]
            detail = "opened" if ok else "opened, but the contents differ"
        except VaultError as e:
            ok = "expect_error" in v and v["expect_error"] in str(e)
            detail = f"refused: {e}"
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {v['name']}: {detail}")
    print(f"\n{len(vectors['vectors']) - failures} of {len(vectors['vectors'])} vectors passed.")
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description="Open a Lastkey vault from its guardian cards.")
    ap.add_argument("files", nargs="*", help="files containing cards (default: read stdin)")
    ap.add_argument("--kt-file", help="file with the 32-byte time-lock secret, already decrypted")
    ap.add_argument("--tle", help="path to drand's tle tool; used to open the time-lock")
    ap.add_argument("--export-tlock", metavar="FILE", help="write the time-lock as an armored age file and stop")
    ap.add_argument("--check", metavar="VECTORS", help="run the test vectors in this JSON file")
    args = ap.parse_args()

    if args.check:
        return check_vectors(args.check)

    text = "".join(open(p, encoding="utf-8").read() for p in args.files) if args.files else sys.stdin.read()
    try:
        cards = find_cards(text)
        if not cards:
            raise VaultError("No Lastkey cards found. Cards start with LK2.")
        first = cards[0]
        tl = first["tl"]
        if args.export_tlock:
            if not tl:
                raise VaultError("This vault has no time-lock.")
            with open(args.export_tlock, "w", encoding="ascii", newline="\n") as f:
                f.write(armor(first["tlock"]))
            print(f"Wrote {args.export_tlock}. Decrypt it after round {tl['round']} with: "
                  f"tle --decrypt --output kt.bin {args.export_tlock}")
            return 0
        kt = None
        if tl:
            opens = datetime.fromtimestamp(round_time(tl["round"]), timezone.utc)
            if args.kt_file:
                kt = open(args.kt_file, "rb").read()
            elif args.tle:
                kt = run_tle(args.tle, first["tlock"])
            else:
                raise VaultError(
                    f"This vault is time-locked until drand round {tl['round']} "
                    f"({opens:%Y-%m-%d %H:%M} UTC). Run again with --tle path/to/tle, or use "
                    f"--export-tlock vault.age and decrypt that file with any tlock tool.")
        v = open_vault(cards, kt)
    except VaultError as e:
        print(f"Could not open the vault: {e}", file=sys.stderr)
        return 2

    sealed = datetime.fromtimestamp(v["sealedAt"] / 1000, timezone.utc)
    print(f"{v['title']}")
    print(f"From {v['owner'] or 'unknown'}, sealed {sealed:%Y-%m-%d %H:%M} UTC, "
          f"opened with the cards of {', '.join(v['cards_used'])}\n")
    print(v["body"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
