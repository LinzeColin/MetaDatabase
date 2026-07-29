import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("Traefik bridge is a single private socket-proxy path", () => {
  const socket = fs.readFileSync(new URL("../../service/systemd/weread-port-traefik-bridge.socket", import.meta.url), "utf8");
  const service = fs.readFileSync(new URL("../../service/systemd/weread-port-traefik-bridge.service", import.meta.url), "utf8");
  assert.match(socket, /^ListenStream=10\.0\.1\.1:8789$/m);
  assert.match(socket, /^Service=weread-port-traefik-bridge\.service$/m);
  assert.match(service, /^ExecStart=\/usr\/lib\/systemd\/systemd-socket-proxyd 127\.0\.0\.1:8788$/m);
  assert.match(service, /^NoNewPrivileges=true$/m);
  assert.match(service, /^ProtectSystem=strict$/m);
  assert.match(service, /^ProtectHome=true$/m);
  assert.match(service, /^RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX$/m);
});
