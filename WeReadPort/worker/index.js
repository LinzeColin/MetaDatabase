import { handleRequest } from "../src/server/handler.js";
export default { fetch(request, env, ctx) { return handleRequest(request, env, ctx); } };
