import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import test from "node:test";
import { createEdgeBridge, parseEdgeBridgeConfig } from "../../service/edge-bridge.mjs";

test("edge bridge requires a private Docker host and loopback account service", () => {
  assert.throws(() => parseEdgeBridgeConfig({ WRP_EDGE_BRIDGE_HOST: "0.0.0.0" }), /Docker 私网/);
  assert.throws(() => parseEdgeBridgeConfig({ WRP_EDGE_BRIDGE_HOST: "10.0.1.1", WRP_SERVICE_HOST: "0.0.0.0" }), /回环地址/);
  assert.deepEqual(parseEdgeBridgeConfig({ WRP_EDGE_BRIDGE_HOST: "10.0.1.1", WRP_EDGE_BRIDGE_PORT: "8789", WRP_SERVICE_HOST: "127.0.0.1", WRP_SERVICE_PORT: "8788" }), {
    listenHost: "10.0.1.1", listenPort: 8789, upstreamHost: "127.0.0.1", upstreamPort: 8788, peerPrefix: "10.0.1.",
  });
});

test("edge bridge preserves Worker credentials while refusing non-private peers", async () => {
  let observedSecret = "";
  const upstream = http.createServer((request, response) => {
    observedSecret = request.headers["x-wrp-internal-secret"] || "";
    response.writeHead(204, { "x-upstream": "ok" });
    response.end();
  });
  upstream.listen(0, "127.0.0.1");
  await once(upstream, "listening");
  const upstreamPort = upstream.address().port;
  let acceptsPeer = false;
  const bridge = createEdgeBridge({ listenHost: "10.0.1.1", listenPort: 8789, upstreamHost: "127.0.0.1", upstreamPort, peerPrefix: "10.0.1." }, {
    peerAllowed: () => acceptsPeer,
  });
  bridge.listen(0, "127.0.0.1");
  await once(bridge, "listening");
  const bridgePort = bridge.address().port;
  const denied = await request(bridgePort, { "x-wrp-internal-secret": "must-not-arrive" });
  assert.equal(denied.status, 403);
  assert.equal(observedSecret, "");
  acceptsPeer = true;
  const proxied = await request(bridgePort, { "x-wrp-internal-secret": "worker-secret" });
  assert.equal(proxied.status, 204);
  assert.equal(proxied.headers["x-upstream"], "ok");
  assert.equal(observedSecret, "worker-secret");
  await close(bridge);
  await close(upstream);
});

function request(port, headers) {
  return new Promise((resolve, reject) => {
    const request = http.request({ host: "127.0.0.1", port, path: "/v1/session", headers }, response => {
      response.resume();
      response.once("end", () => resolve({ status: response.statusCode, headers: response.headers }));
    });
    request.once("error", reject);
    request.end();
  });
}

function close(server) { return new Promise(resolve => server.close(resolve)); }
