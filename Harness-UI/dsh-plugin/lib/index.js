const name = "dsh-harness-ui-skins";
const inject = [];

function apply(ctx) {
  ctx.logger?.("harness-ui")?.info?.("Harness UI adapter uses http://127.0.0.1:3099");
}

export { apply, inject, name };
