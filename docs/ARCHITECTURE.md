# 架构

## 两条显式管线

```text
/yulu:create-character
    → 先停用当前角色（普通配置模式）
    → 读取用户原文 → agent 灵活提议片段 → 快速来源核验
    → 原文与 corpus.json 存入项目 → 渲染自包含 Skill

/yulu:<id> [chat|translate|strict]
    → 显式激活/切换模式 → 当前会话持续注入规则
    → Stop：脚本快速通道 → 未决项交给 LLM 语义复核

/yulu:<id> help → 展示 README，不退出
/yulu:<id> off  → 显式退出，恢复普通 agent
```

没有隐式唤起、普通文本模式切换或隐式退出。`create-character` 必须显式触发，并在开始吸收前退出角色。

## 资料与自包含性

`characters/<id>/source.txt` 保存完整原文；`corpus.json` 保存可跨原行、也可在原行内部的片段；`policy.md` 描述三种模式；`character.json` 保存身份、默认 `chat` 和回退片段 ID。

原文换行不构成切分限制。切分由 agent 根据语义提议，脚本核验空白归一化后来自原文连续内容。导入后 `source.txt`、`corpus.json` 和脚本全部复制到 `skills/<id>/`，运行不再依赖原始外部目录。

`corpus.json` 是字符串数组，允许片段内换行，避免把原行格式误当角色边界。非空片段库必须指定库内回退；空库不可激活。导入在暂存目录完成核验，再交换源文件与角色包。

## 会话状态

Skill 设置 `disable-model-invocation: true`。显式调用时动态 shell 执行 `activate/off/help`，使用 `CLAUDE_SESSION_ID` 和事件 `session_id`，将角色根路径、输出模式和停用标记保存在 `CLAUDE_PLUGIN_DATA/sessions/`。

`UserPromptSubmit` 只在当前角色激活时注入对应模式的规则与片段。再次显式调用同角色只切换明确指定的模式，未指定则沿用。显式调用其他角色后，旧角色钩子因状态不匹配跳过。`off` 或生成角色的动态前置命令设置停用标记，直到重新显式唤起。

帮助读取插件 README，属于普通控制输出，不要求语料格式。`/clear`、`/resume` 卸载钩子后需要重新显式唤起。

## 输出模式

- `translate`：仅以合适的语料片段转译用户输入，不加括号释义。
- `chat`（默认）：正常交互，可不含语料；引用语料后紧跟中文括号释义。
- `strict`：每句话必须包含至少一条语料片段并紧跟中文括号释义，允许自然语言衔接。

## 软校验

同一 `agent` Stop 钩子先执行 `stop` 脚本。快速通道返回：

- `pass`：脚本足以判定，例如纯转译片段、合规引用、普通无引用对话、停用角色。
- `review`：脚本未匹配，交给 LLM 结合 `last_assistant_message`、当前模式、项目内原文与片段判断。

语义符合当前模式必须放行，即使换行不同或快速匹配未命中。明确不符合才返回 `ok:false` 和修改意见。括号释义的语义准确度、片段适合度由 LLM 判断；脚本不能证明语义质量。

## 限制

Skill/Stop 不能在助手文本显示前撤回内容。模型复核和重答是尽力约束，不是安全保证。实验性 agent 钩子要求目标 Claude Code 版本支持，脚本单测与 manifest 校验不能代替钩子端到端测试。大量语料逐轮注入有上下文成本，后续可增加检索，但不能牺牲项目内自包含性。
