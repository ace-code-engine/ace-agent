# 体检清单（repo-audit）

> 每一项都要有结论：`正常` / `有问题` / `没查（原因）`。没有问题也是结论 —— 空着不算。

## 1. 结构与入口
- [ ] 构建/依赖文件有哪些（`package.json` / `pyproject.toml` / `Cargo.toml` / `Makefile`）？
- [ ] 入口在哪（CLI 入口 / 服务入口 / 库的公开 API）？
- [ ] README 里写的用法与实际入口**一致**吗？（不一致就是一条问题）

## 2. 测试与 CI
- [ ] 测试目录/框架是什么？测试文件数？
- [ ] **能不能一条命令跑起来**？（跑不起来要写清缺什么）
- [ ] CI 配置存在吗？它跑的命令与本地文档一致吗？

## 3. 可疑信号（grep 取证）
- [ ] `TODO|FIXME|HACK|XXX`：数量与分布（集中在哪里）
- [ ] 空异常：`except: pass` / `except Exception: pass` / 吞掉错误的 `catch {}`
- [ ] 危险调用：`eval(` / `exec(` / `shell=True` / `subprocess.*shell` / `verify=False`
- [ ] 硬编码凭据形状：`sk-` / `AKIA` / `ghp_` / `-----BEGIN .* PRIVATE KEY`
- [ ] 明显的调试残留：`print(` 在库代码里、`debugger`、`console.log`

## 4. 依赖与供应链
- [ ] 锁文件在吗（`package-lock.json` / `poetry.lock` / `Cargo.lock`）？
- [ ] 有没有钉住版本？（全是 `*` / `latest` 就是一条风险）
- [ ] 有没有已经明确废弃/重命名的依赖？（只报**能取证**的，不猜）

## 5. 文档与约定
- [ ] 变更记录（CHANGELOG）在吗？最近一次更新是什么时候？
- [ ] 许可证文件在吗？与构建文件里声明的许可证一致吗？
- [ ] 有无"给 agent 的约定文件"（AGENTS.md / CLAUDE.md / CONTRIBUTING）？

## 6. 结论怎么写
- [ ] 每条问题：`位置` + `原文片段` + `为什么是问题` + `建议动作`（可小可大，但要说清）
- [ ] 每条"待确认"：缺哪一处证据、补上它需要跑什么
- [ ] 报告顶栏写清：审计的 commit、时间、范围（哪些目录没看）
