from __future__ import annotations
import argparse,json
PLAN=['确认最新 main 与 clean working tree','生成并核对 .env 与 0600 secrets','docker compose build 并记录 image digest','新目录启动并运行 /health','逐平台只读 Canary','对象存储 probe 与恢复 Fixture','配置 Cloudflare Zero Trust 后切换反向代理','保留上一部署与回滚命令','独立 Verifier 绑定 commit/image/deployment identity']
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--plan',action='store_true');args=ap.parse_args();print(json.dumps({'status':'PLAN_ONLY','steps':PLAN,'side_effects':False},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
