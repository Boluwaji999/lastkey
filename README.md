# Lastkey

Leave your keys with the people you trust.

Lastkey is an inheritance vault that runs entirely in your browser. You write down what your family needs (where the will is, how to reach the hardware wallet, which accounts to close). Lastkey encrypts it, splits the key between your guardians, and can also lock it until a date you choose.

There is no server, no account and no company to trust. The whole app is one HTML file that works offline, so it keeps working even if this repository disappears.

## How it works

1. **Seal.** Your text is encrypted in the browser with AES-256-GCM. It is never uploaded.
2. **Split.** The key is split with Shamir's secret sharing into one card per guardian. Any group smaller than the threshold you pick (for example 2 of 3) learns nothing about the contents.
3. **Time-lock (optional).** Part of the key is encrypted to a future round of the [drand](https://drand.love) randomness beacon using drand's own [tlock](https://github.com/drand/tlock-js) format. Until the drand network publishes that round, nobody can open the vault, not even all guardians together.

To open a vault, the guardians bring their cards (as text or as a photo of the QR code) to Lastkey. Opening a time-locked vault needs one public number: the drand signature for its round. Lastkey fetches it automatically, or you can paste it from the beacon page.

## Use it

- **Online:** open the GitHub Pages site for this repository.
- **Offline (recommended):** download `docs/Lastkey.html` and keep it with the guardian cards. Double-click to open it in any modern browser.

After sealing, use **Print cards, one per page** to give each guardian a paper card with a QR code and plain instructions.

## Check that your copy is genuine

Every release publishes the SHA-256 fingerprint of `Lastkey.html` in [`docs/SHA256SUMS.txt`](docs/SHA256SUMS.txt). Compare it with your copy before trusting it with anything real.

Windows (PowerShell):

```powershell
(Get-FileHash .\Lastkey.html -Algorithm SHA256).Hash.ToLower()
```

macOS / Linux:

```sh
shasum -a 256 Lastkey.html
```

## Status

Lastkey is a working prototype. The cryptography comes from well-known building blocks (the browser's Web Crypto API and drand's tlock-js), but the way Lastkey combines them has **not been independently audited**. Don't rely on it as the only copy of anything you can't afford to lose.

Things to know:

- The vault name, your name and the guardians' names are visible on every card. Only the contents are encrypted.
- Cards are tied to the version that made them. Cards from early test versions (`LK1.`) can't be opened.

## Building from source

`lastkey.html` is the source. The libraries it uses are vendored in `lib/`.

```powershell
powershell -ExecutionPolicy Bypass -File build-standalone.ps1
```

This inlines every library and font into `dist/Lastkey.html`, copies it to `docs/` for GitHub Pages, and writes the fingerprint to `docs/SHA256SUMS.txt`. `serve.ps1` serves the folder at http://localhost:8765 for testing.

`lib/prepare-libs.ps1` turns the downloaded vendor files into the embeddable versions. It only needs to run again when a library is updated.

## Third-party code

| Library | Version | License |
| --- | --- | --- |
| [tlock-js](https://github.com/drand/tlock-js) (bundled with its dependencies, including noble-curves and noble-hashes) | 0.9.0 | Apache-2.0 / MIT |
| [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) | 1.4.4 | MIT |
| [jsQR](https://github.com/cozmo/jsQR) | 1.4.0 | Apache-2.0 |
| Bricolage Grotesque, Manrope, JetBrains Mono (Google Fonts) | | SIL Open Font License 1.1 |
