const mockUrl = new URL("./cloudflare-workers-mock.mjs", import.meta.url).href;

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "cloudflare:workers") return { url: mockUrl, shortCircuit: true };
  return nextResolve(specifier, context);
}
