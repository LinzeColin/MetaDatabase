import assert from "node:assert/strict";
import test from "node:test";
import {
  createMailPort,
  createNitroSendMailPort,
  createResendMailPort,
  type TransactionalMail,
} from "../server/auth/mail.ts";

const message: TransactionalMail = {
  to: "member@example.test",
  subject: "Verify your email",
  text: "Verify at https://workbench.example.test/verify",
  html: "<p>Verify</p>",
};

function recordingFetcher(calls: Array<{ url: string; init: RequestInit | undefined }>): typeof fetch {
  return async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(null, { status: 202 });
  };
}

test("Resend MailPort keeps its frozen HTTPS request shape", async () => {
  const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
  await createResendMailPort({
    apiKey: "test-resend-key",
    from: "noreply@example.test",
    fetcher: recordingFetcher(calls),
  }).send(message);

  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.url, "https://api.resend.com/emails");
  assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), {
    from: "noreply@example.test",
    to: ["member@example.test"],
    subject: message.subject,
    text: message.text,
    html: message.html,
  });
});

test("NitroSend MailPort uses only the provider REST contract and preserves message data", async () => {
  const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
  await createNitroSendMailPort({
    apiKey: "test-nitrosend-key",
    from: "noreply@example.test",
    fetcher: recordingFetcher(calls),
  }).send(message);

  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.url, "https://api.nitrosend.com/v1/my/messages");
  assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), {
    channel: "email",
    from: "noreply@example.test",
    to: "member@example.test",
    subject: message.subject,
    body: message.text,
    html: message.html,
  });
});

test("MailPort dispatches explicitly and returns a generic provider error", async () => {
  const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
  await createMailPort({
    provider: "nitrosend",
    apiKey: "test-nitrosend-key",
    from: "noreply@example.test",
    fetcher: recordingFetcher(calls),
  }).send(message);
  assert.equal(calls[0]?.url, "https://api.nitrosend.com/v1/my/messages");

  const failingFetcher: typeof fetch = async () => new Response(null, { status: 503 });
  await assert.rejects(
    createResendMailPort({
      apiKey: "test-resend-key",
      from: "noreply@example.test",
      fetcher: failingFetcher,
    }).send(message),
    /Transactional mail service unavailable\./,
  );
});
