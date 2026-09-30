"""表现层：终端渲染与交互（调色板 / 选择器 / 卡片 / 滚动 / i18n）。不参与权限裁决。

**冻结（`WP-0` W0-C · P-08）**：`frontend/`（Ink）是主外壳，`ui/` 是**无 Node 环境下的
fallback** —— 只修 bug，不加功能。新功能一律落 `frontend/`。本标记由 `test_all [10]`
复核：`ui/__init__.py` 与 `tui/__init__.py` 必须都带着"只修 bug"这句话，否则红。
"""
