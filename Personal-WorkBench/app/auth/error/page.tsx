import Link from "next/link";
import { authErrorRecovery } from "../_components/auth-error";
import { LegacyAuthHandoff } from "../_components/legacy-auth-handoff";
import { isRetiredAuthHost } from "../_components/retired-auth-host";

export const dynamic = "force-dynamic";

type AuthErrorPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/** A product-owned, value-safe landing page for failed OAuth callbacks. */
export default async function AuthErrorPage({ searchParams }: AuthErrorPageProps) {
  if (await isRetiredAuthHost()) return <LegacyAuthHandoff />;
  const params = await searchParams;
  const recovery = authErrorRecovery(params.error);

  return (
    <main className="auth-shell">
      <section className="card auth-card auth-card-expanded" aria-labelledby="auth-error-title">
        <Link className="auth-back" href="/" aria-label="返回个人工作台">←</Link>
        <h1 id="auth-error-title">{recovery.title}</h1>
        <p className="auth-message" role="status">{recovery.message}</p>
        <Link className="auth-primary-link" href={recovery.primaryHref}>{recovery.primaryLabel}</Link>
        <Link className="auth-secondary-link" href="/auth/forgot-password">忘记密码？</Link>
      </section>
    </main>
  );
}
