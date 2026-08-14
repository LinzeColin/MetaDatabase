import { AuthForm } from "../_components/auth-form";
import { LegacyAuthHandoff } from "../_components/legacy-auth-handoff";
import { publicAuthGoogleClientId, publicAuthTurnstileSiteKey } from "../_components/public-auth-page-config";
import { isRetiredAuthHost } from "../_components/retired-auth-host";

export const dynamic = "force-dynamic";

export default async function SignInPage() {
  if (await isRetiredAuthHost()) return <LegacyAuthHandoff />;
  return (
    <AuthForm
      mode="sign-in"
      turnstileSiteKey={publicAuthTurnstileSiteKey()}
      googleClientId={publicAuthGoogleClientId()}
    />
  );
}
