export type TransactionalMail = {
  to: string;
  subject: string;
  text: string;
  html: string;
};

export type MailPort = {
  send(message: TransactionalMail): Promise<void>;
};

type ResendMailOptions = {
  apiKey: string;
  from: string;
  fetcher?: typeof fetch;
};

/**
 * The provider response is deliberately not logged: it can contain recipient
 * and delivery metadata. Caller-visible auth messages stay enumeration-safe.
 */
export function createResendMailPort({
  apiKey,
  from,
  fetcher = fetch,
}: ResendMailOptions): MailPort {
  return {
    async send(message) {
      const response = await fetcher("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from,
          to: [message.to],
          subject: message.subject,
          text: message.text,
          html: message.html,
        }),
      });

      if (!response.ok) {
        throw new Error("Transactional mail service unavailable.");
      }
    },
  };
}

function emailMarkup(title: string, body: string, url: string): string {
  const safeUrl = url.replaceAll('"', "&quot;");
  return `<p>${title}</p><p>${body}</p><p><a href="${safeUrl}">继续</a></p>`;
}

export function verificationMail(to: string, url: string): TransactionalMail {
  return {
    to,
    subject: "请验证你的邮箱",
    text: `请打开此链接完成邮箱验证：${url}`,
    html: emailMarkup("验证邮箱", "请点击下方链接完成验证。", url),
  };
}

export function passwordResetMail(to: string, url: string): TransactionalMail {
  return {
    to,
    subject: "重设你的密码",
    text: `请打开此链接重设密码：${url}`,
    html: emailMarkup("重设密码", "请点击下方链接设置新密码。", url),
  };
}
