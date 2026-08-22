import { registerHarnessMenu } from "./menu.js";

const name = "dsh-harness-ui-skins";
const inject = ["desktopRuntime"];

function apply(ctx) {
  ctx.logger?.("harness-ui")?.info?.("Harness UI adapter uses http://127.0.0.1:3099");
  ctx.effect(() => registerHarnessMenu(ctx), "dsh-harness-ui-skins: native synchronized skin menu");
}

export { apply, inject, name };
