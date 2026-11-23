# yulu.skill

纯 Claude Code 角色生成与调用插件。角色只能显式唤起，唤起后在当前会话持续生效；用户显式关闭后才恢复普通 agent。

## 刘斌：三种输出模式

`/yulu:liu-bin` 默认进入**对话模式**。在角色已激活时再次显式使用下列命令切换：

| 操作 | 命令 | 行为 |
|---|---|---|
| 对话（默认） | `/yulu:liu-bin chat` 或 `对话` | 正常回答；插入语料原文时，紧跟中文括号解释含义。 |
| 转译 | `/yulu:liu-bin translate` 或 `转译` | 用合适的语料片段表达用户输入；不添加括号释义或额外台词。 |
| 强制 | `/yulu:liu-bin strict` 或 `强制` | 每句话都包含语料片段，引用后紧跟中文括号释义；可自然衔接。 |
| 帮助 | `/yulu:liu-bin help` 或 `帮助` | 展示本 README 与操作列表，不退出角色。 |
| 退出 | `/yulu:liu-bin off` 或 `关闭` | 恢复普通 agent；之后只有显式唤起才重新进入。 |
| 吸收语料 | `/yulu:create-character` | 进入普通配置流程，**触发即退出当前角色**。 |

普通对话中的“切换模式”“退出角色”等文字不执行控制操作。只有角色命令的显式控制参数才生效。模式切换命令本身属于控制操作，不需要用歌词回答。

## 语料吸收

原文来自用户指定的本地文件。原文的换行不是切分边界：可以按意思在原行内部切分，也可以组合跨行片段；不擅自续写、翻译、修正或补写语料。

通过 `/yulu:create-character` 提供原文路径，agent 提议片段，再用脚本核验来源。完整原文和片段都保存在本项目，导入后运行**不再依赖外部原文目录**。

```text
characters/liu-bin/
├── source.txt       # 完整原文，保留歌曲分隔，不用于外部路径引用
├── corpus.json      # JSON 字符串数组；每项是可含换行的完整片段
├── policy.md        # 三模式与会话控制契约
└── character.json   # schema v2：默认 chat，片段 ID 与回退项

skills/liu-bin/      # 自包含角色包：相同资料、SKILL.md、校验脚本
```

默认第一条片段为回退项。没有原文或有效片段时保持 `empty`，不假装角色可用。`segments` 只做快速来源检查；`import --source` 将原文一起存入项目。已有语料的替换必须先由用户确认。

## 软校验

输出采用两层校验，而不是机械逐行拒绝：

1. Python 脚本快速检查原文片段、转译的额外文本、引用的括号释义和强制模式的逐句引用。
2. 单一 `agent` 类型 Stop 钩子先运行脚本。`pass` 直接放行；`review` 时读取项目内的原文、片段和当前模式，由 LLM 判断。原文换行不同或脚本未命中，**不等于违规**；语义符合当前模式应放行。只有明确违反当前模式才要求重答。

对话允许不含语料的正常回答；语义复核主要检查疑似引用及转译/强制的合规性。括号释义是否准确、片段是否贴切由模型判断，脚本只提供可重复的快速通道。

## 边界与运行要求

- Claude Code **2.1.304+**（Skill frontmatter 钩子）；Python 3.9+，仅标准库。
- `agent` Stop 钩子是实验性能力，需要在目标版本做端到端验证。当前环境为 2.1.186，不能据此声称完整角色钩子已验证。
- 纯插件不能在回复显示前拦截文本。软校验与事后重答不等于零越界输出，运行失败、重试上限、上下文压缩都可能削弱约束。
- 角色持续有效不等于全局生效；会话由 Skill 钩子和会话状态限定。`/clear`、`/resume` 后需重新显式唤起。
- 新角色生成在插件目录，升级前备份；独立安装到其他 Skill 目录须用户另行确认。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 skills/shared/scripts/yulu.py validate characters/liu-bin
claude plugin validate --strict .
claude --plugin-dir /path/to/yulu.skill
```

首批刘斌语料已导入：19 首完整原文、661 个去重片段，并保留 `segments.json` 来源索引。默认对话实测成功；不同 CLI 版本的动态 shell 权限/环境注入存在差异，测试时可对**单次会话**使用 `--permission-mode auto`，并按需显式提供 `CLAUDE_PLUGIN_ROOT`、`CLAUDE_PLUGIN_DATA`、`CLAUDE_SESSION_ID`。不要为规避权限而关闭所有安全检查；新版自动环境仍需验证。详见 [验证记录](docs/VERIFICATION.md)。

架构与状态机见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。
