import {
  requireFreshVerifiedIdentity,
  requireVerifiedIdentity,
  type SessionIdentity,
} from "@/server/security/tenant";
import { assertSameOriginMutation } from "@/server/security/mutation-origin";

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

export async function requireVerifiedMutationSession(
  auth: SessionReader,
  request: Request,
  expectedAppOrigin: string | undefined,
): Promise<SessionIdentity> {
  const identity = await requireVerifiedSession(auth, request.headers);
  assertSameOriginMutation(request, expectedAppOrigin);
  return identity;
}
