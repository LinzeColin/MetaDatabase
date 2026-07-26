# CB-030 WeChat Screenshot Evidence

- File: `wechat-roundtrip.fixture.png`
- Dimensions: `1280×720`
- Format: PNG
- Claim level: `fixture`
- Real WeChat activation: `activation_pending`
- Real account/session/token/QR/private chat present: `false`

The screenshot was captured from the loopback-only
`weixin-ilink-simulator.mjs` fixture after synthetic `ping` injection and a
synthetic `pong — simulator contract passed` receipt. Its yellow banner says
`SIMULATOR FIXTURE — NOT REAL WECHAT`, and the page repeats
`claim_level=fixture`.

This is the TaskPack-authorized screenshot fallback while QR/account activation
is unavailable. It is not AC-001 real evidence and cannot be used to mark the
real channel verified.
