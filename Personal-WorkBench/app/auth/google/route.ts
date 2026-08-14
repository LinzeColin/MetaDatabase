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
 * The browser identity route is the registered Google flow for this public
 * domain. A normal navigation therefore returns to that same page instead of
 * starting an incompatible server redirect with a different callback type.
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
