# 工程债与交接（Hand-off）

> 从 README 迁出。这是**交接清单**，不是待办的第二份副本：每行只说一句"欠什么"，
> 真正的证据、决定与边界都在那份**立项卡**里 —— **别把这张表当完整说明，点进去看卡**。

## 还没做完的（附权威记录）

| 欠什么 | 一句话 | 权威记录 |
|---|---|---|
| **验收门槛还剩收尾** | 四道 ACC 门槛的机器那一半、A0b（`measured_*` 聚合）、**阈值判据**（`token_verdict`，暂用阈值 50%）都已落地；**只剩** `benchmarks/results/` 接校验器（要等 WP-10 的"下沉前/后可复核数据"） | [`docs/design/ACC-GATES.md`](design/ACC-GATES.md) §7.5 / §8.6 / §10.4 |
| **脊柱全落地（仅 HL-04 的 ACC 接线待 WP-10）** | `RL-01~04` · `DL-01~04` · `HL-01/02/03/05` 已落地；`HL-04` 的可判定机器也已落地（§9.14：`MaterialIncomplete` + `build_material` + `[73]` 五种偷换），只剩「接 ACC 门槛」仍被 WP-10 的 before/after 数据卡着 | [`docs/design/THREE-LAYERS.md`](design/THREE-LAYERS.md) §9 |
| **只剩批次 6 与 WP-10** | 批次 −1…5 已关闭；**批次 6** = 非 URL 出网通道（WP-8 后半）＋ CubeSandbox 沙箱后端（WP-9）；**WP-10** = Rust 核心化（**快照哈希下沉已实测否决**，见 engine/README.md；剩 流式客户端 / grep / LSP / 路径判定下沉） | [`docs/ROADMAP.md`](ROADMAP.md) §7.2 |

## 仍未验证

- **真 TTY 下的 Textual 全屏界面**、以及任何**非 Windows 控制台**。（CI 已装 `textual` 跑通 headless `run_test` 那几段；但"人在真终端里打字"这件事，无头 runner 验不了，仍需一台真机。）
- ~~darwin/amd64 执行器原生冒烟~~ —— 已补：`release-executor.yml` 的 `native-smoke` 加 `macos-13`（Intel runner）。

## 为什么停在这里

作者要上学。这份清单就是交接 —— 每一行都指到那张卡，卡里写着证据、边界，以及"下一步该做什么"。
