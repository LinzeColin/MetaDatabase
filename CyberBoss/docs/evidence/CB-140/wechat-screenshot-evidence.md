# CB-140 WeChat Fixture PNG Evidence

- File: `wechat-roundtrip.fixture.png`
- Dimensions: `1280×720`
- PNG SHA-256:
  `42c0bcb42f3e0e5c4ed83c6877b64d758991318553141a440738f5c229f551b8`
- Accepted fixture HTML SHA-256:
  `a716755010f90e6ece09c4c31ea72611aa12be6038ed453795bcabc6b3f80aaa`
- Claim level: `fixture`
- Browser capture: `false`
- Deterministic static evidence render: `true`
- Real WeChat activation: `activation_pending`
- Real account/session/token/QR/private chat present: `false`

The exact target acceptance runner generated a redacted simulator fixture after
the synthetic `CB140-SIMULATOR-SCREENSHOT` round trip. Its accepted HTML
contained `SIMULATOR FIXTURE — NOT REAL WECHAT`, matching synthetic inbound
and outbound markers, and `claim_level=fixture`.

The in-app browser correctly blocked direct `file://` navigation under its URL
security policy and prohibited browser workarounds. The PNG was therefore
rendered without executing the HTML: the already inspected fixed strings were
placed into a deterministic SVG audit plate and converted by the local system
graphics library. The plate visibly discloses `DETERMINISTIC STATIC EVIDENCE
RENDER — NOT A BROWSER CAPTURE`.

This is the TaskPack-authorized simulator fallback. It is not AC-001 real or
AC-010 real evidence, and it cannot be used to claim a real QR scan, account,
message, Runtime turn or provider activation.
