import {
  CANONICAL_MYDAIRY_ORIGIN,
  isRetiredCompatibilityHost,
} from "../../_components/workbench/canonical-domain";

export const runtime = "edge";

function redirect(destination: URL): Response {
  return new Response(null, {
    status: 302,
    headers: {
      "Cache-Control": "no-store",
      Location: destination.toString(),
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex",
    },
  });
}

/**
 * Direct Google links hand off to the sign-in page with an explicit fallback
 * request. After hydration, the page starts Better Auth's normal OAuth code
 * flow, so a blocked browser-identity button cannot return to this same page
 * without ever reaching Google's account selection.
 */
export async function GET(request: Request): Promise<Response> {
  let requestUrl: URL;
  try {
    requestUrl = new URL(request.url);
  } catch {
    return new Response(null, { status: 400 });
  }

  if (isRetiredCompatibilityHost(requestUrl.host)) {
    return redirect(new URL("/auth/sign-in?google=1", CANONICAL_MYDAIRY_ORIGIN));
  }

  return redirect(new URL("/auth/sign-in?google=1", requestUrl.origin));
}
