"use client";

import { LegacyDomainRedirect } from "../../_components/workbench/legacy-domain-redirect";
import { CANONICAL_MYDAIRY_ORIGIN } from "../../_components/workbench/canonical-domain";

/**
 * Authentication must never begin on the retired hostname: Better Auth keeps
 * its state cookie host-only, so an old-host Google start cannot complete on
 * the canonical callback domain. Reuse the bounded legacy handoff before
 * rendering any credential or provider control.
 */
export function LegacyAuthHandoff() {
  return (
    <>
      <LegacyDomainRedirect />
      <main className="auth-shell">
        <section className="card auth-card auth-card-expanded" aria-labelledby="legacy-auth-handoff-title">
          <h1 id="legacy-auth-handoff-title">正在打开个人工作台</h1>
          <p className="auth-message" role="status">
            正在将你带到新的个人工作台地址，随后即可继续登录。
          </p>
          <a className="auth-primary-link" href={`${CANONICAL_MYDAIRY_ORIGIN}/auth/sign-in`}>
            如果没有自动打开，继续登录
          </a>
        </section>
      </main>
    </>
  );
}
