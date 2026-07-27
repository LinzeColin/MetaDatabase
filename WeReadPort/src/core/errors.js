/** Safe typed errors. Messages may be displayed and never include a key or raw note body. */
export class WeReadPortError extends Error {
  /** @param {string} code @param {string} message @param {{retryable?:boolean,status?:number,errcode?:number,details?:Record<string,unknown>,cause?:unknown}} [options] */
  constructor(code, message, options = {}) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = "WeReadPortError";
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.status = options.status;
    this.errcode = options.errcode;
    this.details = options.details ?? {};
  }
}

export class UpgradeRequiredError extends WeReadPortError {
  /** @param {Record<string,unknown>} upgradeInfo */
  constructor(upgradeInfo) {
    const message = typeof upgradeInfo.message === "string" && upgradeInfo.message.trim()
      ? upgradeInfo.message.trim()
      : "微信读书官方接口要求升级客户端契约，已停止后续调用和制品生成。";
    super("BLOCKED_UPGRADE", message, { details: { upgradeInfo } });
    this.name = "UpgradeRequiredError";
    this.upgradeInfo = upgradeInfo;
  }
}

/** @param {unknown} error */
export function toSafeFailure(error) {
  if (error instanceof WeReadPortError) {
    return { code: error.code, message: error.message, retryable: error.retryable, status: error.status, errcode: error.errcode };
  }
  return { code: "UNEXPECTED", message: "发生未预期错误，系统未生成虚假成功结果。", retryable: false };
}
