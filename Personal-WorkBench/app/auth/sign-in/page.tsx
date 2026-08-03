import Link from "next/link";

export default function SignInPage() {
  return (
    <main className="auth-shell">
      <section className="card auth-card">
        <h1>欢迎回来</h1>
        <p>登录入口将在账户与隐私流程完成后启用。</p>
        <Link href="/">返回工作台</Link>
      </section>
    </main>
  );
}
