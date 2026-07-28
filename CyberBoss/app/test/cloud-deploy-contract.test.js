"use strict";

// 部署脚本的红线测试。
//
// 起因是一次真实的事故：部署脚本每次都报"部署完成"，systemctl 也报 active，
// 但服务实际上连着好几天跑的都是几个版本之前的那个 release。原因是 systemd 的
// 入口脚本读的是 CB_RELEASE_ROOT / CB_EXPECTED_RELEASE_ID 两个环境变量，而这
// 两行由 .service.d/ 下的 drop-in 提供，主 unit 文件里根本没有——脚本却用 sed
// 去改主 unit 文件，改了个空。current 指针照常移动，所以肉眼看什么都对。
//
// 这个文件不测业务，只测部署脚本这几条不能再犯的约束。它读的是脚本文本本身：
// 真跑一次部署需要那台服务器，而这些约束在文本层面就能钉死。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const OPS = path.join(__dirname, "..", "..", "ops");
const deployScript = fs.readFileSync(path.join(OPS, "deploy-to-cloud.sh"), "utf8");
const logsScript = fs.readFileSync(path.join(OPS, "cloud-logs.sh"), "utf8");

test("发布绑定写进 drop-in，而不是去改主 unit 文件", () => {
  assert.match(
    deployScript,
    /^CB_RELEASE_ROOT=/m,
    "部署脚本必须自己写 CB_RELEASE_ROOT，否则 systemd 用的还是旧绑定",
  );
  assert.match(deployScript, /^CB_EXPECTED_RELEASE_ID=/m);
  assert.match(
    deployScript,
    /\.service\.d/,
    "绑定必须落在 .service.d/ drop-in 目录里",
  );
  assert.doesNotMatch(
    deployScript,
    /sed -i[^\n]*\/etc\/systemd\/system\/\$SERVICE\b/,
    "主 unit 文件里没有这两行，sed 改它是空操作——正是当初那次事故",
  );
});

test("drop-in 的文件名要排在已有的 90- 绑定之后", () => {
  const match = deployScript.match(/DROPIN="\$DROPIN_DIR\/([0-9]+)-/);
  assert.ok(match, "drop-in 路径必须以数字前缀开头");
  assert.ok(
    Number(match[1]) > 90,
    `drop-in 前缀 ${match[1]} 必须大于 90：systemd 按文件名排序，序号小的会被 90-cb5xx-release-binding.conf 压掉`,
  );
});

test("新 release 要补齐入口脚本会核对的三个发布契约文件", () => {
  // run-cyberboss.sh 会逐个核对这三个，缺一个就 exit 2 且服务起不来。
  // 它们都是部署期产物，不在仓库里，所以只能由部署脚本生成或带过去。
  assert.match(deployScript, /write-release-manifest\.js/, "必须生成 release-manifest.json");
  assert.match(deployScript, /health-contract\.json/, "必须提供 health-contract.json");
  assert.match(deployScript, /process-tree\.txt/, "必须提供 process-tree.txt");
  assert.match(deployScript, /implementation-kit/, "必须带上 implementation-kit");
});

test("channel 激活模式要设成 required，否则 supervisor 永远不拉起 bridge", () => {
  // pending 模式下 cloud-supervisor 打一行 component_pending 就 await 一个
  // 永不 resolve 的 Promise：微信、后台页面、整个 app 一个都不会启动，而
  // systemctl 依然显示 active。
  assert.match(deployScript, /^CB_CHANNEL_ACTIVATION_MODE=required$/m);
});

test("状态目录指向真正存着账号和密钥的那个目录", () => {
  assert.match(
    deployScript,
    /^CYBERBOSS_STATE_DIR=\$STATE_DIR$/m,
    "50- 那个 drop-in 把状态目录改到了子目录，必须显式覆盖回来",
  );
  assert.match(deployScript, /^STATE_DIR="?\/var\/lib\/cyberboss"?$/m);
});

test("覆盖值走 EnvironmentFile，不走 Environment=", () => {
  // systemd 的规则：EnvironmentFile 里的设置覆盖 Environment= 的设置，和 drop-in
  // 的排序无关。主 unit 和 drop-in 50 各引了一个 env 文件，里面有旧的
  // CYBERBOSS_WORKSPACE_ROOT 和 CYBERBOSS_STATE_DIR；用 Environment= 写的覆盖
  // 值会被它们悄悄盖掉，而 `systemctl show -p Environment` 不展开
  // EnvironmentFile，所以查出来一切正常、进程里却是旧值。这一条曾经让
  // workspace_root_not_allowlisted 反复出现在一个"看起来已经改对了"的配置上。
  assert.match(deployScript, /EnvironmentFile=\$LIVE_ENV/, "drop-in 必须引用自己的 env 文件");
  assert.match(deployScript, /^LIVE_ENV=/m);
  assert.doesNotMatch(
    deployScript,
    /^Environment=(CYBERBOSS_WORKSPACE_ROOT|CYBERBOSS_STATE_DIR|CB_RELEASE_ROOT)=/m,
    "这些值一旦用 Environment= 写就会被已有的 EnvironmentFile 覆盖",
  );
});

test("部署后的验证必须核对真实运行的版本号和后台端口", () => {
  // 只看 systemctl is-active 是不够的：绑定错的时候它照样 active。
  assert.match(deployScript, /verify_live/);
  assert.match(deployScript, /grep -q 'release=\$short'/, "必须核对进程报出来的 release 号");
  assert.match(deployScript, /healthz/, "必须确认后台端口真的在应答");
});

test("查日志必须带上独立的 journal namespace", () => {
  // unit 文件写了 LogNamespace=cyberboss。不带 --namespace 查出来是空的，
  // 会被误读成"程序没打印任何东西"。
  const commands = logsScript.match(/journalctl[^"]*/g) || [];
  assert.ok(commands.length > 0, "脚本里应当有 journalctl 调用");
  for (const command of commands) {
    assert.match(command, /--namespace=cyberboss/, `缺 namespace：${command}`);
  }
  assert.match(deployScript, /journalctl --namespace=cyberboss/);
});

test("绑定之前先确认目标 release 的契约是全的", () => {
  // 一次真实的连锁事故：新版本验证失败 → 自动回滚 → 回滚目标缺
  // release-manifest.json → 服务从"跑着旧版本"变成"彻底起不来"。
  assert.match(
    deployScript,
    /sudo test -f \$APP_ROOT\/releases\/\$sha\/release-manifest\.json/,
    "write_binding 必须先确认目标 release 有 manifest",
  );
});

test("回滚目标取自绑定，不取自 current 指针", () => {
  // 事故期间这两者可以差好几个版本：current 每次部署都动，绑定却没动。
  // 照着 current 回滚，等于把服务推到一个从来没跑起来过的版本上。
  assert.match(
    deployScript,
    /OLD_SHA="\$\(remote "sudo sed -n 's\|\^CB_EXPECTED_RELEASE_ID=\|\|p' \$LIVE_ENV/,
    "OLD_SHA 必须从绑定文件里的 CB_EXPECTED_RELEASE_ID 读出来",
  );
});
