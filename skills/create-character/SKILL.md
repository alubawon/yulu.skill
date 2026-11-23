---
name: create-character
description: "显式进入语料吸收与角色生成流程；触发时退出当前角色。"
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" off)
argument-hint: "[角色说明或角色 ID]"
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" off`

# 语料吸收与角色生成

这是显式启动的**普通配置流程**，不是角色对话。上方的退出结果必须成功才能继续；此时不再以任何角色口吻回答。只有用户再次显式调用 `/yulu:<id>` 才进入角色。

运行脚本：`${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py`，需要 Python 3.9+。不调用外部模型或网络服务，不擅自补写、翻译、修正语料。

## 收集与灵活切分

1. 确认显示名和 ASCII ID，例如“刘斌”使用 `liu-bin`。询问用户自己的 UTF-8 原始语料文件路径和可选规则路径。
2. **原文换行不是切分边界。** 读取完整原文后，按可表达的意思、语气、适合引用长度灵活提议片段。可以跨原行、在原行内部切分；不要改写文字、续写歌词或加入解释。片段以 JSON 字符串数组保存，单个片段可含换行；相邻且适合一起引用的短句可合并成一个片段。
3. 若用户提供自己的片段 JSON 数组，也可使用；若需要 agent 提议，把 JSON 写入用户明确同意的工作文件。使用 `segments` 快速核验（去除空白后必须来自原文连续内容）：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" segments \
     "<原始语料路径>" --parts '["片段一", "跨行或行内的片段二"]'
   ```

   数组只是命令参数示意，必须替换为从用户原文提议的真实片段，不能编造示例歌词。该核验只证明来源，不评价切分质量；无法确定的边界交还用户决定。
4. 新角色先执行（已有角色只有用户明确要求重建才追加 `--replace`）：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" new <id> "<显示名>" \
     --plugin-root "${CLAUDE_PLUGIN_ROOT}"
   ```

   如用户指定规则文件，追加 `--policy "<规则路径>"`。默认 manifest 支持 `translate`、`chat`、`strict`，默认 `chat`。
5. 对已存在角色，确认将替换片段和原文后执行：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" import \
     "${CLAUDE_PLUGIN_ROOT}/characters/<id>" "<片段文件路径>" \
     --source "<原始语料路径>" --output "${CLAUDE_PLUGIN_ROOT}/skills/<id>" --replace
   ```

   默认第一条片段为回退。指定其他回退时从 manifest 获取片段 ID，使用 `--fallback <ID>`，不得另写回退台词。
6. 验证并报告结果：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/<id>/scripts/yulu.py" validate --ready
   ```

   说明原文、片段文件和调用命令。让用户 `/reload-plugins` 后显式唤起，不要自动进入角色。没有原文或有效片段时保留 `empty`，不生成可激活角色。

## 角色使用与产物

- `characters/<id>/source.txt`：完整原文；`corpus.json`：灵活切分的片段数组；`policy.md`：三种模式规则。
- `skills/<id>/`：完整可调用包。插件内 `/yulu:<id>`，默认对话模式。
- `/yulu:<id> translate|chat|strict`（或中文模式名）显式切换；`help` 展示 README；`off` 显式退出。
- 本流程被触发即退出角色，和普通 `help` 一样属于配置说明，不受角色语料格式约束。
- 独立个人 Skill 安装须再次确认路径，第一版正式支持插件内加载；生成文件在插件目录，升级前备份角色源文件。
