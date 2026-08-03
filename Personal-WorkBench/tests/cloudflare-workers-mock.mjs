// The frozen UI test does not execute binding-backed routes. This mock lets its
// Node loader import the generated Worker while production keeps the native
// Cloudflare module binding.
export const env = {};
