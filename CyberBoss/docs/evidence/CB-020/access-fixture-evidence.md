# Access Deny/Allow Fixture Evidence

Both PNGs were captured from
`implementation-kit/tests/access-policy-fixture.html` through a temporary
static server bound only to `127.0.0.1`. The server was stopped immediately
after capture.

| File | Fixture request | Expected decision | Real provider |
|---|---|---|---|
| `access-deny.fixture.png` | anonymous / unauthorized | deny | no |
| `access-allow.fixture.png` | approved `.invalid` owner | allow | no |

The fixture contains no real identity, account identifier, service-token
secret or provider response. Executable policy semantics are verified by
`access-policy-contract.test.js`; screenshot pixels are supporting visual
evidence, not the sole Oracle.
