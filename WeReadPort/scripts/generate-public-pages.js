import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { APP_NAME } from "../src/core/constants.js";
import { legalMainHtml, legalTitle, standaloneDocument, statusMainHtml } from "../src/core/public-pages.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export async function generatePublicPages() {
  for (const [route, html] of Object.entries(expectedPublicPages())) {
    const target = path.join(root, route, "index.html");
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, html, "utf8");
  }
  console.log("已生成隐私政策、使用条款和系统状态静态入口。");
}

export function expectedPublicPages() {
  return {
    privacy: standaloneDocument({
      title: `${legalTitle("privacy")}｜${APP_NAME}`,
      description: "了解微信读书笔记迁移如何处理、传输、清除与保护数据。",
      body: legalMainHtml("privacy"),
    }),
    terms: standaloneDocument({
      title: `${legalTitle("terms")}｜${APP_NAME}`,
      description: "了解微信读书笔记迁移的允许用途、禁止用途、服务边界和责任。",
      body: legalMainHtml("terms"),
    }),
    status: standaloneDocument({
      title: `系统状态｜${APP_NAME}`,
      description: "查看微信读书笔记迁移的公开应用、静态资源、微信读书代理合同与运维入口状态。",
      body: statusMainHtml(),
    }),
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) await generatePublicPages();
