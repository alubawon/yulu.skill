# 架构

## 生产与运行两条管线

```text
create-character
  → 收集对象类型、传记/访谈/用户设定、语言原文
  → evidence-add 自包含保存 → persona 草案 → 用户确认
  → persona-set --confirm
  → 原子语料规范化/来源校验 → 发布自包含 Skill

角色显式唤起
  → 保存会话模式 → 每轮注入已确认 persona + 最多 6 条相关语言样例
  → 主 agent 第一人称扮演 → off 退出
```

creator 和运行时共享 `skills/shared/scripts/yulu.py` 的 schema、persona 渲染与发布函数，不分别维护不兼容的产物。

## 人格与证据

`character.json` schema v3 指向 `persona.json`、原文、原子语料和模式规则。人格七维条目包含 `source_type/source_ref/confidence/status`；真人事实与作品叙述者/语言风格分开。推断不能直接标 confirmed，未知维度为空。

`persona.md` 只渲染 confirmed，草案用于用户修订。`interaction_state` 单独保存经确认的互动事实与偏好，不自动记录模型臆测。证据原文件只进 `characters/<id>/evidence/`，不进运行包。

## 语料分层

- `source.txt` 是不可变原文。
- `corpus.json` 是原子语言单元：每个唯一非空原文行一个稳定 ID，歌曲/段落/行号组成 occurrence 列表。
- 重复副歌及平行出现只保留一个单元；组合不是新库存。导入时输入组合必须是原文连续行，运行时不保存所有邻接排列。
- 结构化位置验证代替全空白归一化。旧 `segments.json` 可留作审计，但不作为运行时输入。
- 运行时通过确定性关键词/二元片段评分对完整库存排序，不设置召回上限，不过滤低相关条目；translate 必须全库选择有意义的原文组合，无高置信候选也不能拒答或固定回退。无向量库、无额外模型请求；完整库存增加上下文成本。

## 模式与提示优先级

chat 是第一人称扮演，默认无括号释义；translate 是用完整原文行转译输入，可多行承接、对照或推进，不要求每条单独相关，禁止自造或拼接新句；strict 是每句原文的特殊风格。人格和语料来源隔离，语言样例不作为人格事实。

用户显式激活状态使用 schema v3。插件级 `hooks/hooks.json` 只注册一个 UserPromptSubmit 共享 hook，以文档支持的 `${CLAUDE_PLUGIN_ROOT}` 定位 `skills/shared/scripts/yulu.py`；Skill frontmatter 不再重复注册，也不使用 hook 不支持的 `CLAUDE_SKILL_DIR`。旧 CLI 不会向 hook 子进程注入可靠的插件环境，因此共享脚本以自身真实路径推导插件根，读取唤起时保存的角色路径；未激活静默退出，兼容旧角色 `.runtime` 状态。发布角色包时保留 `.runtime`，不删除激活状态。提示明确人格行为优先于通用助手反射，但不能覆盖系统/开发者指令。默认主 agent 执行，不默认使用无状态 roleplay subagent。

## 无运行时复核

生成器和角色包均无 Stop，不提供开关。离线 `check` 仅用于测试，不参与运行时。
