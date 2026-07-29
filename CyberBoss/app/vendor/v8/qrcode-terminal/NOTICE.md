# qrcode-terminal vendored QR encoder

- Upstream: https://github.com/gtanner/qrcode-terminal
- Version: 0.12.0
- License: Apache-2.0 (bundled `LICENSE`); bundled `vendor/QRCode` source includes its original MIT notice.
- Reuse scope: QR matrix generation only. Terminal rendering is not used.
- Reason: production QR rendering must work in a clean offline install without adding a runtime registry dependency.
