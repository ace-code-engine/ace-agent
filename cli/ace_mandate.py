#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_mandate（操作者工具）—— 签一张授权令，或检查已有的令。

    python -m cli.ace_mandate issue --intents file_write,file_delete \
        --roots . --floor snapshot --quota 1 --allow-irreversible terminal_exec --ttl 3600
    python -m cli.ace_mandate show --file mandate.json

签出来的 JSON 贴进 `~/.ai_code.json` 的 `"mandate"` 键即可生效（`ace --doctor` 之外无需重启）。
**默认不配令 = 行为与以前逐字相同**；配了之后，令能把"本来会问人"的两处
（项目外对象确认、`CONFIRM_TOOLS` 逐次确认）变成放行，但**不能**覆盖硬拒绝、外发确认与权限等级。

密钥来自**锚**（`core.guardian.anchor_dir_for`，可用 `ACE_ANCHOR_DIR` 换位置）—— 与快照签名、
台账签名域分离。令里带 `expiresAt` 与 `usedIrreversible`，额度用掉之后会重新签名。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import ace_mandate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="ACE 授权令（RG-05）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    iss = sub.add_parser("issue", help="签一张令")
    iss.add_argument("--id", default="", help="令的标识（默认按时间生成）")
    iss.add_argument("--intents", default="", help="允许的意图/工具名，逗号分隔")
    iss.add_argument("--roots", default=".", help="允许的路径前缀，逗号分隔（默认当前目录）")
    iss.add_argument("--floor", default=ace_mandate.DEFAULT_FLOOR,
                     choices=["git", "snapshot", "regenerable", "unknown", "never"],
                     help="可逆性下限（默认 snapshot：只有 git 内与有快照的算达标）")
    iss.add_argument("--quota", type=int, default=0, help="不可逆动作额度")
    iss.add_argument("--allow-irreversible", default="",
                     help="点名放行的不可逆目标或工具名，逗号分隔")
    iss.add_argument("--ttl", type=int, default=3600, help="有效期（秒）")
    iss.add_argument("--project-root", default=".", help="锚归属的项目（默认当前目录）")
    iss.add_argument("--out", default="", help="写到文件（默认打到 stdout）")

    sh = sub.add_parser("show", help="检查一张令")
    sh.add_argument("--file", required=True)
    sh.add_argument("--project-root", default=".")

    args = ap.parse_args()
    _split = lambda s: [x.strip() for x in str(s or "").split(",") if x.strip()]  # noqa: E731

    if args.cmd == "issue":
        try:
            key = ace_mandate.mandate_key(project_root=args.project_root)
        except OSError as e:
            print(f"FAIL: 拿不到锚里的密钥（{e}）—— 用 ACE_ANCHOR_DIR 指到可写位置", file=sys.stderr)
            return 1
        mid = args.id or ("md_" + time.strftime("%Y%m%d_%H%M%S"))
        mand = ace_mandate.issue(key, mandate_id=mid, intents=_split(args.intents),
                                 roots=_split(args.roots), recovery_floor=args.floor,
                                 irreversible_quota=args.quota,
                                 allow_irreversible=_split(args.allow_irreversible),
                                 ttl_s=args.ttl)
        text = json.dumps(mand, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"已写出 {args.out}")
        else:
            print(text)
        print(f"\n# 生效方式：把上面的对象贴进 ~/.ai_code.json 的 \"mandate\" 键。"
              f"有效期到 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mand['expiresAt']))}；"
              f"不可逆额度 {mand['irreversibleQuota']}。", file=sys.stderr)
        return 0

    # show
    try:
        mand = json.loads(Path(args.file).read_text(encoding="utf-8"))
        key = ace_mandate.mandate_key(project_root=args.project_root)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: 读不到令或拿不到密钥：{e}", file=sys.stderr)
        return 1
    status, why = ace_mandate.verify(key, mand)
    print(f"令 {mand.get('mandateId')}: {status} —— {why}")
    print(f"  意图: {', '.join(mand.get('intents') or []) or '（无）'}")
    print(f"  范围: {', '.join(mand.get('roots') or []) or '（无）'}")
    print(f"  可逆性下限: {mand.get('recoveryFloor')} · 不可逆额度: "
          f"{mand.get('usedIrreversible', 0)}/{mand.get('irreversibleQuota', 0)}")
    print(f"  点名放行: {', '.join(mand.get('allowIrreversible') or []) or '（无）'}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
