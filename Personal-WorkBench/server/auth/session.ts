import {
  requireFreshVerifiedIdentity,
  requireVerifiedIdentity,
  type SessionIdentity,
} from "@/server/security/tenant";
import { assertSameOriginMutation } from "@/server/security/mutation-origin";
import { readAuthRuntimeConfig, type AuthRuntimeEnv } from "@/server/auth/runtime";

type SessionReader = {
  api: {
    getSession(input: { headers: Headers }): Promise<unknown>;
  };
};

export async function requireVerifiedSession(
  auth: SessionReader,
  headers: Headers,
): Promise<SessionIdentity> {
  const session = await auth.api.getSession({ headers });
  return requireVerifiedIdentity(session);
}

export async function requireFreshVerifiedSession(
  auth: SessionReader,
  headers: Headers,
): Promise<SessionIdentity> {
  const session = await auth.api.getSession({ headers });
  return requireFreshVerifiedIdentity(session);
}

export function assertConfiguredSameOriginMutation(request: Request, env: AuthRuntimeEnv): void {
  assertSameOriginMutation(request, readAuthRuntimeConfig(env)?.trustedOrigins);
}

export async function requireVerifiedMutationSession(
  auth: SessionReader,
  request: Request,
  env: AuthRuntimeEnv,
): Promise<SessionIdentity> {
  const identity = await requireVerifiedSession(auth, request.headers);
  assertConfiguredSameOriginMutation(request, env);
  return identity;
}
