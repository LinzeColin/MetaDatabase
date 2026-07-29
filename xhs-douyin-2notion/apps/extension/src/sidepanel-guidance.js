export const PLATFORM_NAMES = Object.freeze({
  bilibili: "哔哩哔哩",
  douyin: "抖音",
  kuaishou: "快手",
  taobao: "淘宝",
  weibo: "微博",
  xiaohongshu: "小红书",
});

const EXTERNALLY_GATED_DETAIL_PLATFORMS = new Set([
  "bilibili",
  "kuaishou",
  "taobao",
  "weibo",
]);

export function unavailableDetailGuidance(platform) {
  if (platform === "douyin") {
    return Object.freeze({
      eyebrow: "下一步",
      kicker: "抖音内容",
      note: "当前详情页不会触发保存。",
      platformStatus: "当前详情页不会保存；本轮不会自动翻页或读取其他内容。",
      status: "请在收藏或喜欢清单中开始",
      steps: Object.freeze({ first: "打开收藏或喜欢", second: "查看清单提示", third: "按提示继续", active: 0 }),
      title: "先打开“收藏”或“喜欢”",
      copy: "返回抖音个人页后，手动打开收藏或喜欢清单。清单可用时，这里会显示下一步。",
    });
  }

  if (!EXTERNALLY_GATED_DETAIL_PLATFORMS.has(platform)) return null;
  const platformName = PLATFORM_NAMES[platform];
  return Object.freeze({
    eyebrow: "正在准备中",
    kicker: platformName,
    note: "开放前，x2n 不会读取、下载或改变账号状态。",
    platformStatus: "这篇内容已经识别到；本轮不会读取、下载或保存它。",
    status: `${platformName}暂时还不能保存`,
    steps: Object.freeze({ first: "已经打开内容", second: "等待开放", third: "无需继续操作", active: 1 }),
    title: `${platformName}还在准备中`,
    copy: "这不是你的操作有问题。当前版本还没有打开这个平台的保存功能，因此不用换页面或找按钮。",
  });
}
