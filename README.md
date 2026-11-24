# yulu.skill

可溯源人格、语言库存与显式角色扮演插件。只有用户显式唤起才进入角色；普通输入不切换模式，`off` 退出。

## 三种模式

| 操作 | 命令 | 行为 |
|---|---|---|
| 扮演（默认） | `/yulu:liu-bin chat` | 以角色第一人称回应，不解说语料，默认不加括号释义。 |
| 转译 | `/yulu:liu-bin translate` | 只使用合适的完整原文片段，不加其他台词。 |
| 强制风格 | `/yulu:liu-bin strict` | 每句包含完整原文片段，不是人格定义。 |
| 帮助 | `/yulu:liu-bin help` | 展示说明，不退出。 |
| 退出 | `/yulu:liu-bin off` | 恢复普通 agent。 |

扮演可用 `chat` 或“扮演”；`strict;对话` 同时指定风格和内容。人格行为优先于通用助手客套/解说反射，但不覆盖系统或开发者指令。

## 人格与语言库存

每个角色包含：

- `persona.json`：身份背景、性格价值观、目标欲望、用户关系、喜好、禁忌和语言风格。每项记录来源类型、位置、置信度和确认状态；`interaction_state` 仅保存经确认的互动事实与偏好。
- `persona.md`：仅由已确认条目渲染的紧凑运行时人格；未知不编造。
- `source.txt`：不可变语言原文。
- `corpus.json`：唯一原子行、稳定 ID 及歌曲/段落/行号 occurrence。重复副歌只存一次，组合不进入库存。
- `evidence/`：用户提供的传记、访谈、作品或明确设定，供 creator 使用，不进入运行包。

角色的专属人格、证据和语言原文均保存在 `characters/<角色 ID>/`，运行时仅使用发布后的 `skills/<角色 ID>/`；项目文档不定义具体角色人格。

`/yulu:create-character` 收集对象类型、传记/访谈/设定、语言原文、关系与边界，生成草案，用户确认后发布。事后补充人格使用 `evidence-add`、`persona-set`、`publish`，不必重导语料。

运行时注入 persona 和最多 6 条按当前输入检索的语言样例；无匹配则自然说话。不调用嵌入模型，不全量注入库存，不保存邻接排列。组合只作为输入视图，不能跨歌曲或段落。

## 校验与运行边界

运行时没有 Stop、规则复核或 LLM 复核，只有 Skill 与上下文软约束。离线 `check` 仅用于测试；生成器不提供 Stop 开关，不修改全局模型配置。

主 agent 默认扮演。专用 roleplay subagent 暂不作为默认能力：需先解决有状态会话续接、近期上下文、人格/检索预算、工具权限与错误回退，不能用每轮全新 subagent 代替持久人格。

## 验证

```bash
python3 -m unittest discover -s tests -v
claude plugin validate --strict .
python3 skills/shared/scripts/yulu.py validate characters/liu-bin --ready
```

个人安装将 `~/.claude/skills/yulu` 链接到本仓库。更新后重新加载插件或重启会话。架构见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，验证记录见 [docs/VERIFICATION.md](docs/VERIFICATION.md)。
