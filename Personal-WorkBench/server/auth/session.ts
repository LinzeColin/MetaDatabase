import { requireVerifiedIdentity, type SessionIdentity } from "@/server/security/tenant";

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
