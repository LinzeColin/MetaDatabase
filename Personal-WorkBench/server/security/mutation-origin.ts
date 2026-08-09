export class SameOriginRequiredError extends Error {
  status = 403;
  code = "SAME_ORIGIN_REQUIRED";

  constructor() {
    super("A same-origin request is required.");
  }
}

function normalizedOrigin(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (parsed.pathname !== "/" || parsed.search || parsed.hash) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function normalizedOrigins(value: string | readonly string[] | undefined): string[] {
  const candidates = typeof value === "string" ? [value] : value ?? [];
  return [...new Set(candidates.map((entry) => normalizedOrigin(entry)).filter((entry): entry is string => Boolean(entry)))];
}

/**
 * Custom JSON/form mutation routes do not share Better Auth's endpoint
 * middleware. Require a configured first-party Origin and reject browser
 * cross-site fetch metadata when it is present. Together with HttpOnly,
 * Secure, SameSite cookies this is the CSRF boundary for those routes.
 */
export function assertSameOriginMutation(
  request: Request,
  expectedAppOrigins: string | readonly string[] | undefined,
): void {
  const expected = normalizedOrigins(expectedAppOrigins);
  const actual = normalizedOrigin(request.headers.get("origin"));
  const fetchSite = request.headers.get("sec-fetch-site");
  if (expected.length === 0 || !actual || !expected.includes(actual) || (fetchSite && fetchSite !== "same-origin")) {
    throw new SameOriginRequiredError();
  }
}
