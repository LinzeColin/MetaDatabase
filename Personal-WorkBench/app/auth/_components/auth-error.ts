export type AuthErrorRecovery = {
  message: string;
  primaryHref: string;
  primaryLabel: string;
  title: string;
};

/**
 * OAuth providers may return an arbitrary error description. Keep the browser
 * recovery screen to a small, product-owned set of safe instructions instead
 * of reflecting provider text or query values into the page.
 */
export function authErrorRecovery(value: unknown): AuthErrorRecovery {
  const code = typeof value === "string" ? value : "";

  switch (code) {
    case "access_denied":
      return {
        title: "已取消本次 Google 登录",
        message: "本次没有登录，也没有写入任何记录。返回登录页后可重新选择 Google，或使用邮箱和密码登录。",
        primaryHref: "/auth/sign-in",
        primaryLabel: "返回登录",
      };
    case "email_doesn't_match":
      return {
        title: "Google 连接未完成",
        message: "当前账户与所选 Google 账号不一致。请回到账户页，再点击“连接 Google”并选择要关联的账号。",
        primaryHref: "/account",
        primaryLabel: "返回账户",
      };
    case "account_not_linked":
      return {
        title: "Google 尚未关联",
        message: "这个邮箱已有独立账户。为保护多账号数据不会自动合并；请先用邮箱密码确认该账户，随后会继续你主动发起的 Google 连接。",
        primaryHref: "/auth/sign-in?link_google=1",
        primaryLabel: "使用邮箱登录并连接 Google",
      };
    case "state_not_found":
    case "state_mismatch":
    case "invalid_code":
    case "no_code":
      return {
        title: "本次登录已过期",
        message: "请从个人工作台的登录页重新开始 Google 登录，不要在中途切换标签页或复制回调链接。",
        primaryHref: "/auth/sign-in",
        primaryLabel: "重新登录",
      };
    case "email_not_found":
      return {
        title: "Google 未提供可用邮箱",
        message: "请在 Google 中选择允许提供邮箱的账号后重试，或使用邮箱和密码登录。",
        primaryHref: "/auth/sign-in",
        primaryLabel: "返回登录",
      };
    case "account_already_linked_to_different_user":
      return {
        title: "该 Google 账号已被使用",
        message: "该 Google 账号已经关联到另一个个人工作台账户。请返回登录并选择正确的账号。",
        primaryHref: "/auth/sign-in",
        primaryLabel: "返回登录",
      };
    default:
      return {
        title: "登录没有完成",
        message: "请返回登录页后重新尝试。若仍无法继续，可使用邮箱和密码登录或找回密码。",
        primaryHref: "/auth/sign-in",
        primaryLabel: "返回登录",
      };
  }
}
