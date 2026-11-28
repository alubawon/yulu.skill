# 验证记录

## 历史验证（旧 schema，已被替换）

- 2026-11-23/24 曾验证显式激活、转译和 off；当时 chat 使用括号释义、Stop 语义复核与全量片段注入，不代表当前行为。
- 早期“661 个去重片段”只表示字符串不同，不表示信息不重叠，已不能作为语料去重标准。

## 当前 persona/schema v3

- 2026-11-24：11 项 unittest 通过，覆盖人格来源与草案确认、证据复制、重复折叠、来源位置、跨段拒绝、相关检索、无匹配不注入、默认无 Stop、运行包自包含。
- `claude plugin validate --strict .` 通过。
- 刘斌 612 个输入片段、611 个唯一字符串、241 个跨行组合归并为 287 个唯一原子行；原文保持不变，每行 occurrence 可校验。
- 原始 549 个非空行有 306 个唯一行；规范化排除《歌曲名》元数据行，得到 287 个语言单元。
- 2026-11-24：用户确认刘斌为 `real_person`，明确“谦和、幽默、叛逆的朋克老登，但身份是金属乐手”及现场安全问候；另录入用户提供的 NF《盛大的狂欢》发布时乐队访谈。七维 persona 共 13 条均为 confirmed，访谈中的集体创作态度保留乐队语境，未发布单曲等后续事实不推断。
- 默认运行没有 Stop 和复核 LLM；每轮渲染已确认 persona 和完整语言库存，不再截断为最多 6 条或过滤低相关条目。
- 2026-11-24：刘斌人格更新后重新运行全部 11 项 unittest 和 `claude plugin validate --strict .`，均通过；源角色与运行包 `validate --ready` 均通过。persona 和歌词源/运行副本逐字节一致，shared 与 liu-bin 脚本逐字节一致。
- 脚本 `invoke liu-bin-persona-smoke-test 'chat;聊聊创作'` 成功返回 `real_person` 人格和访谈创作观上下文；这是激活上下文测试，不是实际模型扮演的口吻验收。

## 待验证/限制

- 2026-11-25：用户报告每条输入出现 `UserPromptSubmit hook error: /bin/sh: /scripts/yulu.py: No such file or directory`。根因是 Skill frontmatter hook 中 `${CLAUDE_SKILL_DIR}` 未注入，路径展开为空。官方 hook 文档仅支持以 `${CLAUDE_PROJECT_DIR}`、`${CLAUDE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_DATA}` 引用路径；现已改为插件级共享 hook，并移除 Skill 内的重复注册。新增无 `CLAUDE_SKILL_DIR` 的真实 subprocess 回归测试。
- 2026-11-27：修复并完成真实 CLI 2.1.186 回归。显式唤起后，普通输入的 `UserPromptSubmit` 返回 `exit_code=0 / outcome=success`，并实际注入刘斌人格和完整 287 条语言库存，不再出现 `/scripts/yulu.py`。16 项 unittest 和严格插件校验通过，覆盖无 `CLAUDE_SKILL_DIR`、旧 `.runtime`、发布后保留激活状态、未激活静默退出、完整库存。旧宿主仍属兼容路径，不替代 2.1.304+ 目标版本验证。
- 角色行为是提示层软约束，不能保证完全消除通用助手口吻；不声称覆盖高优先级系统/开发者指令。
- 2026-11-25：用户明确 translate 的目标是把输入用语料翻译再表述，不是通用有效回答。经 Git blame 确证旧 `limit=6` 和 `[:limit]` 来自提交 `76731bd`，是实现时加入的默认值，不是 Claude Code 限制。现已移除所有模式的数量上限与相关性过滤。
- 2026-11-25：translate 改为全库语义选句，可多行承接/对照/推进，无高置信候选仍须输出，不得固定回退或自造/拼接新句；chat/strict 保留可选引用语义。11 项 unittest 和严格插件校验通过；三模式的 invoke/prompt 均实测注入刘斌全部 287 条库存。真实模型转译质量尚需会话体验。
- 用户提供的刘斌人格设定已确认，但缺少独立人物传记或刘斌个人访谈；真实多轮人格一致性、creator 交互及事后补充仍需用户体验验证。
- 专用 roleplay subagent 未实现，需另行评估有状态会话与上下文成本。
