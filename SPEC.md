# Lastkey vault format, version 2

This document describes exactly how Lastkey seals a vault and how to open one. It is written so that anyone can recover a vault **without Lastkey**, using only this document and standard tools. [`recover.py`](recover.py) is an independent implementation of it, and [`test-vectors/`](test-vectors/) holds sample vaults that every implementation must open.

The key words MUST and MUST NOT are used as in RFC 2119.

## 1. Overview

A vault is a short UTF-8 text sealed with AES-256-GCM. The 32-byte AES key is derived from up to two secrets:

| Secret | Size | Protected by |
| --- | --- | --- |
| `Ks`, the share secret | 32 bytes | Shamir's secret sharing: split into `n` shares, any `t` of which rebuild it |
| `Kt`, the time-lock secret (optional) | 32 bytes | drand tlock: encrypted to a future round of the drand quicknet beacon |

Each guardian receives one **card**. Every card carries the full encrypted vault, the time-locked `Kt` (if any), and that guardian's share of `Ks`. To open a vault you need `t` distinct cards from the same vault and, if it is time-locked, the drand signature for its round.

```
            ┌──── Shamir (t of n) ────► share 1, share 2, … share n   (one per card)
  Ks ───────┤
            └───┐
                ├── SHA-256("lastkey/v2" ‖ Ks ‖ Kt) ──► vault key ──► AES-256-GCM(vault JSON)
  Kt ───────────┘
   └──── tlock to drand round R ──► age file                      (copied onto every card)
```

## 2. Card encoding

A card is the ASCII string

```
"LK2." ‖ base64url(card_bytes)
```

`base64url` is the URL-safe alphabet of RFC 4648 §5 (`A–Z a–z 0–9 - _`) **without padding**. Readers SHOULD ignore whitespace and any text around the card, and MUST reject a card whose prefix is not `LK2.`. (Cards beginning `LK1.` came from a pre-release format and cannot be opened.)

`card_bytes` is the concatenation of these fields. All integers are unsigned, big-endian.

| Field | Size (bytes) | Contents |
| --- | --- | --- |
| `header_len` | 2 | Length `H` of the header |
| `header` | `H` | UTF-8 JSON object, see §3 |
| `share` | 32 | This card's Shamir share of `Ks` (the y-values) |
| `iv` | 12 | AES-GCM nonce for the vault |
| `tlock_len` | 2 | Length `L` of the time-lock data; 0 if the vault has no time-lock |
| `tlock` | `L` | Binary (unarmored) age file holding `Kt`, see §6 |
| `vault` | rest | AES-GCM ciphertext of the vault, with the 16-byte tag appended |

## 3. Card header

The header is a JSON object. Unknown members MUST be ignored.

| Member | Type | Meaning |
| --- | --- | --- |
| `id` | string | Vault ID: 8 lowercase hex characters (4 random bytes). Identical on every card of a vault. Also the AES-GCM associated data (§5). |
| `title` | string | Vault name chosen by the owner (not secret) |
| `owner` | string | Owner's name (not secret, may be empty) |
| `n` | integer | Number of cards issued, 2 to 10 |
| `t` | integer | Number of cards needed, 2 to `n` |
| `x` | integer | This card's Shamir x-coordinate, 1 to `n` |
| `g` | string | This card's guardian name |
| `all` | array of strings | All guardian names, in card order (`all[x-1] == g`) |
| `tl` | object or `null` | `null` if no time-lock; otherwise `{ "round": R, "at": T }` |

In `tl`, `round` is the drand quicknet round the vault is locked to, and `at` is the time that round is published, in milliseconds since the Unix epoch (informational; the round is authoritative).

The header is **not encrypted or authenticated**. Implementations MUST treat it as untrusted. Tampering with it cannot reveal the vault; at worst it makes opening fail.

## 4. Shamir secret sharing

`Ks` is split byte by byte over GF(2⁸) with the reduction polynomial x⁸ + x⁴ + x³ + x + 1 (`0x11B`, the AES field).

To split, for each byte position `j` (0 to 31) the sealer picks a random polynomial of degree `t − 1` whose constant term is `Ks[j]`:

```
f_j(x) = Ks[j] + a_1·x + a_2·x² + … + a_(t−1)·x^(t−1)
```

Card `x` (for `x = 1 … n`) gets `share[j] = f_j(x)`. Addition in GF(2⁸) is XOR.

To rebuild `Ks` from `t` cards with distinct x-coordinates `x_1 … x_t` and shares `s_1 … s_t`, evaluate the Lagrange interpolation at zero for each byte `j`:

```
Ks[j] = Σ_i  s_i[j] · Π_(k≠i)  x_k / (x_k ⊕ x_i)
```

Any `t` cards rebuild the same `Ks`. Fewer than `t` reveal nothing about it. Cards with the same `x` MUST NOT be combined. A wrong or altered share produces a wrong `Ks`, which §5's authentication tag detects.

## 5. Vault key and contents

```
vault_key = SHA-256( UTF-8("lastkey/v2") ‖ Ks ‖ Kt )
```

When the vault has no time-lock, `Kt` is the empty string, so the input is just the 10-byte label followed by `Ks`.

The vault is encrypted with AES-256-GCM using `vault_key`, the 12-byte `iv` from the card, and **associated data** `UTF-8(id)` (the 8-character vault ID). The ciphertext is followed by a 16-byte tag. Decryption MUST fail if the tag does not verify. Implementations MUST NOT show any part of a vault that fails verification.

The plaintext is a UTF-8 JSON object:

| Member | Type | Meaning |
| --- | --- | --- |
| `title` | string | Vault name (authenticated copy) |
| `owner` | string | Owner's name (authenticated copy) |
| `body` | string | The message for the guardians, up to 1,200 characters |
| `sealedAt` | integer | When it was sealed, milliseconds since the Unix epoch |

## 6. Time-lock

`Kt` is encrypted with drand's **tlock** scheme ([drand/tlock](https://github.com/drand/tlock), [tlock-js](https://github.com/drand/tlock-js)) to round `R` of the drand **quicknet** beacon:

| Parameter | Value |
| --- | --- |
| Chain hash | `52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971` |
| Scheme | `bls-unchained-g1-rfc9380` |
| Genesis | 1692803367 (Unix seconds) |
| Period | 3 seconds |
| Public key | `83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a` |

The `tlock` field is the age file that tlock produces, with its ASCII armor removed. To use it with standard tlock tools, re-armor it:

```
-----BEGIN AGE ENCRYPTED FILE-----
<base64 (standard alphabet, with padding) of the tlock bytes, in lines of 64 characters>
-----END AGE ENCRYPTED FILE-----
```

The binary form is also a valid age file, so tools that accept unarmored input can read it as is. Decrypting it with any tlock implementation once round `R` is published yields the 32 bytes of `Kt`. For example, with drand's command-line tool:

```
tle --decrypt --output kt.bin vault.age
```

### Choosing the round

A vault meant to open at Unix time `U` (seconds) is locked to

```
R = ⌈(U − genesis) / period⌉ + 1
```

which is the first round published at or after `U`. Round `R` is published at `genesis + (R − 1) · period`.

### Getting the round's signature

The signature for round `R` is public once published. Any drand relay serves it, for example:

```
https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/R
```

The response is JSON. Its `signature` member is 96 hex characters (a compressed BLS12-381 G1 point). Relays cannot forge it: tlock decryption fails with any signature other than the real one for round `R`.

## 7. Opening a vault, step by step

1. Decode each card (§2). Keep only cards with the same `id`. Reject duplicate `x` values.
2. Stop if fewer than `t` cards remain.
3. Rebuild `Ks` from any `t` cards (§4).
4. If the header's `tl` is not `null`: obtain `Kt` by tlock-decrypting the card's `tlock` field (§6). This is only possible after round `R` is published.
5. Compute `vault_key` (§5) and decrypt the `vault` field with the card's `iv` and `id`.
6. If decryption fails, one of the cards is damaged or edited, or `Kt` is wrong. Try a different set of `t` cards.
7. Parse the plaintext JSON and show `body`.

The `vault`, `iv` and `tlock` fields are identical on every card of a vault, so they may be taken from any one card.

## 8. Security notes

- **Not audited.** This format has not had an independent security review.
- **Metadata is public.** The header (vault name, owner, guardian names, card count, threshold, unlock round) is readable by anyone who holds a card.
- **Randomness.** `Ks`, `Kt`, the vault ID, the IV and every Shamir coefficient come from the browser's cryptographically secure generator (`crypto.getRandomValues`).
- **Trust in drand.** A time-lock relies on the drand network not publishing round `R` early, which needs a threshold of its members to collude. Without a time-lock, Lastkey depends on no outside service at all.
- **Integrity.** AES-GCM authentication covers the vault contents and binds them to the vault ID. It does not authenticate the header.
