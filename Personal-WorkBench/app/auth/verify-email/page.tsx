import { AuthForm } from "../_components/auth-form";
import { LegacyAuthHandoff } from "../_components/legacy-auth-handoff";
import { isRetiredAuthHost } from "../_components/retired-auth-host";

export const dynamic = "force-dynamic";

export default async function VerifyEmailPage() {
  if (await isRetiredAuthHost()) return <LegacyAuthHandoff />;
  return <AuthForm mode="verify-email" turnstileSiteKey={null} />;
}
