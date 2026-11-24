---
name: create-character
description: "显式创建或补充可溯源的人格扮演角色；触发时退出当前角色。"
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" off)
argument-hint: "[角色说明、角色 ID 或 persona]"
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" off`

# 人格与语言资料生产流程

这是普通配置流程，不是扮演。运行时脚本为 `${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py`，Python 3.9+。创建、维护、发布必须使用同一脚本和 schema，不得只写一份与运行无关的人设散文。

## 必须向用户收集的输入

1. **扮演对象**：显示名、ASCII ID；`real_person`、`fictional`、`work_narrator` 中的一种；与用户的关系。
2. **人格证据**：真实人物优先要求传记、访谈或用户明确设定，提供 UTF-8 文件路径及可得的作者、日期、引用区间。缺少证据时请用户直接填写身份背景、性格价值观、目标欲望、关系、喜好禁忌，不得根据歌词补写真人传记。
3. **语言资料**：用户有权使用的作品或发言原文路径。作品只支撑作品叙述者与语言风格，不自动支撑真人事实。
4. **风格与边界**：人称、称呼、口癖、节奏、情绪表达、用户互动方式及禁区。

信息不全就先问，保留 draft，不要编造后发布。

## 可重复执行的生产步骤

1. 新建角色骨架；如用户直接提供符合 schema 的 persona，可附 `--persona`：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" new <id> "<显示名>" \
     --plugin-root "${CLAUDE_PLUGIN_ROOT}"
   ```

2. 对每份人格证据调用 `evidence-add`，把原文复制到角色自包含的 `evidence/`：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" evidence-add \
     "${CLAUDE_PLUGIN_ROOT}/characters/<id>" "<访谈或传记路径>" --kind interview
   ```

   `kind` 支持 `biography`、`interview`、`work_text`、`user_setting`。

3. 阅读证据，起草完整 `persona.json`。七个人格维度均为列表，每项必须包含：

   ```json
   {"text":"具体规范","source_type":"interview","source_ref":"evidence/...#行号或区间","confidence":"high","status":"draft"}
   ```

   `source_type` 只能是 `user_setting`、`biography`、`interview`、`work_text`、`inference`。推断不能标为 confirmed；用户明确设定使用 `user://explicit`。向用户展示事实、推断和待确认项，请其逐项修订/确认。

4. 草案保存与确认发布分别执行；确认时不得含 draft/rejected：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" persona-set \
     "${CLAUDE_PLUGIN_ROOT}/characters/<id>" "<草案路径>"
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" persona-set \
     "${CLAUDE_PLUGIN_ROOT}/characters/<id>" "<确认稿路径>" --confirm
   ```

5. 语言库存不再保存所有邻接排列。提供原文和来源片段 JSON 后，脚本自动折叠重复行、记录准确 occurrence，并生成原子 `corpus.json`：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" import \
     "${CLAUDE_PLUGIN_ROOT}/characters/<id>" "<片段 JSON>" \
     --source "<原文路径>" --output "${CLAUDE_PLUGIN_ROOT}/skills/<id>" --replace
   ```

6. 校验并报告实际产物：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/<id>/scripts/yulu.py" validate \
     "${CLAUDE_PLUGIN_ROOT}/skills/<id>" --ready
   ```

   必须存在 `character.json`、`persona.json`、`persona.md`、`source.txt`、原子 `corpus.json`、`policy.md`、`SKILL.md` 和 `scripts/yulu.py`。让用户重新加载插件后显式唤起，不自动进入角色。

## 事后补充人格

用户提供新传记/访谈或设定后，重复 `evidence-add` → 草案确认 → `persona-set`；无需重导语料。再执行：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/shared/scripts/yulu.py" publish \
  "${CLAUDE_PLUGIN_ROOT}/characters/<id>" --output "${CLAUDE_PLUGIN_ROOT}/skills/<id>"
```

`persona-show` 可审计当前规范。未知维度保持空列表；不得把旧草稿自动当成确认人格。

## 运行时语义

- chat = 第一人称扮演，不解说语料，默认无括号释义。
- translate = 纯原文转译；strict = 每句引用原文的特殊风格。
- corpus 是语言库存，不是人格事实。运行时只注入 persona 和少量检索样例，不全量注入排列组合。
- 运行时无 Stop 和 LLM 复核；不提供生成开关。
