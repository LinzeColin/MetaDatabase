export type TransactionalMail = {
  to: string;
  subject: string;
  text: string;
  html: string;
};

export type MailPort = {
  send(message: TransactionalMail): Promise<void>;
};

export type MailProvider = "resend" | "nitrosend";

type ProviderMailOptions = {
  apiKey: string;
  from: string;
  fetcher?: typeof fetch;
};

export type MailPortOptions = ProviderMailOptions & {
  provider: MailProvider;
};

/**
 * The provider response is deliberately not logged: it can contain recipient
 * and delivery metadata. Caller-visible auth messages stay enumeration-safe.
 */
export function createResendMailPort({
  apiKey,
  from,
  fetcher = fetch,
}: ProviderMailOptions): MailPort {
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

/**
 * NitroSend remains behind the same narrow MailPort as the frozen Resend
 * default. It is selected only by the runtime configuration; no provider SDK,
 * credential, recipient, or delivery metadata is retained or logged here.
 */
export function createNitroSendMailPort({
  apiKey,
  from,
  fetcher = fetch,
}: ProviderMailOptions): MailPort {
  return {
    async send(message) {
      const response = await fetcher("https://api.nitrosend.com/v1/my/messages", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          channel: "email",
          from,
          to: message.to,
          subject: message.subject,
          body: message.text,
          html: message.html,
        }),
      });

      if (!response.ok) {
        throw new Error("Transactional mail service unavailable.");
      }
    },
  };
}

export function createMailPort({
  provider,
  apiKey,
  from,
  fetcher,
}: MailPortOptions): MailPort {
  if (provider === "nitrosend") {
    return createNitroSendMailPort({ apiKey, from, fetcher });
  }

  return createResendMailPort({ apiKey, from, fetcher });
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
