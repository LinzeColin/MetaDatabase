import { readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";
import {
  accountA,
  accountB,
  assertPrivateImageDenied,
  assertPrivateImageReadable,
  assertVerifiedSession,
  ensureSensitiveCloudConsent,
  json,
  origin,
  requireProductionInputs,
  signIn,
  uploadFoodImage,
} from "./production-helpers";

type RedeployState = {
  schemaVersion: 1;
  origin: string;
  createdAt: string;
  marker: string;
  todoId: string;
  fileId: string;
};

const phase = process.env.PWB_ACCEPTANCE_PHASE || "";

function stateFile() {
  const supplied = process.env.PWB_REDEPLOY_STATE_FILE?.trim() || "";
  if (!supplied || !path.isAbsolute(supplied)) {
    throw new Error("PWB_REDEPLOY_STATE_FILE must be an absolute private temporary path outside this repository.");
  }
  const resolved = path.resolve(supplied);
  const worktree = path.resolve(process.cwd());
  if (resolved === worktree || resolved.startsWith(`${worktree}${path.sep}`)) {
    throw new Error("PWB_REDEPLOY_STATE_FILE must stay outside the repository so acceptance data cannot be committed.");
  }
  return resolved;
}

function requireRedeployWitness(state: RedeployState) {
  const witness = process.env.PWB_REDEPLOYMENT_WITNESS?.trim() || "";
  const redeployedAt = process.env.PWB_REDEPLOYED_AT_UTC?.trim() || "";
  const createdAt = Date.parse(state.createdAt);
  const deployedAt = Date.parse(redeployedAt);
  if (!witness || Number.isNaN(deployedAt) || deployedAt <= createdAt) {
    throw new Error("PWB_REDEPLOYMENT_WITNESS and a later ISO PWB_REDEPLOYED_AT_UTC are required after the independent external redeploy.");
  }
}

test.describe("VPS3 persistence across an independently performed redeploy", () => {
  test.beforeAll(() => {
    requireProductionInputs();
    if (phase !== "pre-redeploy" && phase !== "post-redeploy") {
      throw new Error("PWB_ACCEPTANCE_PHASE must be pre-redeploy or post-redeploy.");
    }
    stateFile();
  });

  test("pre-redeploy creates server-owned todo and image evidence", async ({ browser }) => {
    test.skip(phase !== "pre-redeploy", "This checkpoint is run only before the independent deploy action.");
    const output = stateFile();
    const signedA = await signIn(browser, accountA);
    try {
      await assertVerifiedSession(signedA.context.request);
      await ensureSensitiveCloudConsent(signedA.context.request);
      const marker = `PWB-redeploy-${Date.now()}`;
      const todo = await json<{ data: { id: string } }>(signedA.context.request, "post", "/api/mydairy/todos", {
        title: marker,
        note: "",
        dueDate: new Date().toISOString().slice(0, 10),
        priority: "normal",
        completed: false,
        completedAt: null,
      });
      const fileId = await uploadFoodImage(signedA.context.request);
      await assertPrivateImageReadable(signedA.context.request, fileId);
      const state: RedeployState = {
        schemaVersion: 1,
        origin,
        createdAt: new Date().toISOString(),
        marker,
        todoId: todo.data.id,
        fileId,
      };
      await writeFile(output, `${JSON.stringify(state, null, 2)}\n`, { encoding: "utf8", mode: 0o600, flag: "wx" });
    } finally {
      await signedA.context.close();
    }
  });

  test("post-redeploy proves the prior todo and image survive and account B remains denied", async ({ browser }) => {
    test.skip(phase !== "post-redeploy", "This checkpoint is run only after the independent deploy action.");
    const output = stateFile();
    const state = JSON.parse(await readFile(output, "utf8")) as RedeployState;
    expect(state).toMatchObject({ schemaVersion: 1, origin, todoId: expect.any(String), fileId: expect.any(String) });
    requireRedeployWitness(state);
    const signedA = await signIn(browser, accountA);
    const signedB = await signIn(browser, accountB);
    try {
      await assertVerifiedSession(signedA.context.request);
      await assertVerifiedSession(signedB.context.request);
      await ensureSensitiveCloudConsent(signedA.context.request);
      await ensureSensitiveCloudConsent(signedB.context.request);
      const aTodos = await json<{ data: Array<{ id: string; title: string }> }>(signedA.context.request, "get", "/api/mydairy/todos");
      expect(aTodos.data.some((row) => row.id === state.todoId && row.title === state.marker)).toBeTruthy();
      await assertPrivateImageReadable(signedA.context.request, state.fileId);
      const bTodos = await json<{ data: Array<{ id: string }> }>(signedB.context.request, "get", "/api/mydairy/todos");
      expect(bTodos.data.some((row) => row.id === state.todoId)).toBeFalsy();
      await assertPrivateImageDenied(signedB.context.request, state.fileId);
      await json(signedA.context.request, "delete", `/api/mydairy/todos/${encodeURIComponent(state.todoId)}`);
      await json(signedA.context.request, "delete", `/api/mydairy/files/${encodeURIComponent(state.fileId)}`);
      await rm(output, { force: true });
    } finally {
      await signedB.context.close();
      await signedA.context.close();
    }
  });
});
