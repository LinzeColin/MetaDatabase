/** Returns only a valid configured first-party auth origin. */
export function configuredAuthOrigin(rawOrigin: string | undefined): string | null {
  const configuredOrigin = rawOrigin?.trim();
  if (!configuredOrigin) return null;

  try {
    const configured = new URL(configuredOrigin);
    const localHttp = configured.protocol === "http:"
      && (configured.hostname === "localhost" || configured.hostname === "127.0.0.1");
    if (
      (!localHttp && configured.protocol !== "https:")
      || configured.pathname !== "/"
      || configured.search
      || configured.hash
    ) {
      return null;
    }

    return configured.origin;
  } catch {
    return null;
  }
}

/**
 * Rebuilds an incoming auth request at the configured public origin when a
 * reverse proxy has exposed an internal container bind address as Request.url.
 * The configured origin remains the only authority: no request host or
 * forwarded header can become a callback origin.
 */
export function requestAtConfiguredOrigin(request: Request, rawOrigin: string | undefined): Request {
  const configuredOrigin = configuredAuthOrigin(rawOrigin);
  if (!configuredOrigin) return request;

  try {
    const configured = new URL(configuredOrigin);
    const incoming = new URL(request.url);
    if (configured.origin === incoming.origin) return request;

    const headers = new Headers(request.headers);
    headers.set("host", configured.host);
    headers.set("x-forwarded-host", configured.host);
    headers.set("x-forwarded-proto", configured.protocol.slice(0, -1));
    return new Request(new URL(`${incoming.pathname}${incoming.search}`, configured.origin), {
      method: request.method,
      headers,
      body: request.body,
      redirect: request.redirect,
      signal: request.signal,
      // Node's Request constructor requires duplex for a streamed POST body.
      duplex: "half",
    } as RequestInit);
  } catch {
    return request;
  }
}
