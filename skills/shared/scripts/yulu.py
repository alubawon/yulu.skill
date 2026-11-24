#!/usr/bin/env python3
"""Local persona, corpus and session tools. Runtime makes no model calls."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile

ID_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,62}")
SESSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
OUTPUT_MODES = {"translate", "chat", "strict"}
MODE_ALIASES = {"translate": "translate", "转译": "translate", "chat": "chat", "扮演": "chat", "对话": "chat", "strict": "strict", "强制": "strict"}
MODE_NAMES = {"translate": "转译", "chat": "扮演", "strict": "强制"}
MANIFEST_KEYS = {"schema_version", "id", "display_name", "modes", "default_mode", "entry", "corpus", "policy", "persona", "fallback_id", "source"}
PERSONA_SECTIONS = ("background", "personality_values", "goals_desires", "user_relationship", "likes", "dislikes_boundaries", "language_style")
EVIDENCE_TYPES = {"user_setting", "biography", "interview", "work_text", "inference"}
STATUSES = {"confirmed", "draft", "rejected"}


class YuluError(ValueError):
    pass


def read_json(path):
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise YuluError("无法读取 JSON：{}：{}".format(path, exc)) from exc


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent), delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(str(temporary), str(path))
    except OSError as exc:
        raise YuluError("无法写入 {}：{}".format(path, exc)) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def validate_id(value, label="角色 ID"):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise YuluError("{}必须以小写字母开头，仅含小写字母、数字和连字符".format(label))
    return value


def session_path(data_root, session_id):
    if not isinstance(session_id, str) or not SESSION_PATTERN.fullmatch(session_id):
        raise YuluError("会话 ID 格式无效")
    return data_root.resolve() / "sessions" / (session_id + ".json")


def resolve_child(root, relative, label):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise YuluError("{}路径无效".format(label))
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        raise YuluError("{}必须位于角色目录内".format(label))
    result = (root / Path(*path.parts)).resolve()
    if not result.is_relative_to(root.resolve()):
        raise YuluError("{}不能通过符号链接离开角色目录".format(label))
    return result


def read_parts(path):
    parts = read_json(path)
    validate_lines(parts)
    return parts


def validate_lines(lines):
    if not isinstance(lines, list) or any(not isinstance(x, str) or not x.strip() or x != x.strip() or "\r" in x or "\x00" in x for x in lines):
        raise YuluError("语料必须是非空、无首尾空白及特殊字符的字符串列表")
    if len(set(lines)) != len(lines):
        raise YuluError("语料不能包含重复片段")


def entry_id(text):
    return "line-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def default_persona():
    return {"schema_version": 1, "subject_kind": "unspecified", "sections": {key: [] for key in PERSONA_SECTIONS}, "interaction_state": {"confirmed_facts": [], "user_preferences": []}}


def validate_persona(persona):
    if not isinstance(persona, dict) or set(persona) != {"schema_version", "subject_kind", "sections", "interaction_state"} or persona["schema_version"] != 1:
        raise YuluError("persona.json 必须符合 schema v1")
    if persona["subject_kind"] not in {"real_person", "fictional", "work_narrator", "unspecified"}:
        raise YuluError("扮演对象类型无效")
    sections = persona["sections"]
    state = persona["interaction_state"]
    if not isinstance(state, dict) or set(state) != {"confirmed_facts", "user_preferences"} or any(not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value) for value in state.values()):
        raise YuluError("interaction_state 只能包含已确认互动事实和用户偏好")
    if not isinstance(sections, dict) or set(sections) != set(PERSONA_SECTIONS):
        raise YuluError("persona 必须包含完整的人格维度")
    for name, claims in sections.items():
        if not isinstance(claims, list):
            raise YuluError("人格维度必须是列表：" + name)
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {"text", "source_type", "source_ref", "confidence", "status"}:
                raise YuluError("人格条目必须包含 text/source_type/source_ref/confidence/status")
            if not isinstance(claim["text"], str) or not claim["text"].strip() or "\n" in claim["text"]:
                raise YuluError("人格条目必须是非空单行文本")
            if claim["source_type"] not in EVIDENCE_TYPES or claim["status"] not in STATUSES or claim["confidence"] not in {"high", "medium", "low"}:
                raise YuluError("人格来源、置信度或状态无效")
            if not isinstance(claim["source_ref"], str) or not claim["source_ref"].strip():
                raise YuluError("人格条目必须标注来源；用户设定使用 user://explicit")
            if claim["status"] == "confirmed" and claim["source_type"] == "inference":
                raise YuluError("推断不能直接确认为事实，须由用户重新标注来源")
    return persona


def load_persona(root):
    persona = read_json(root / "persona.json")
    return validate_persona(persona)


def persona_markdown(persona, display_name):
    lines = ["# 扮演对象：" + display_name, "对象类型：" + persona["subject_kind"]]
    labels = {"background": "身份背景", "personality_values": "性格与价值观", "goals_desires": "目标与欲望", "user_relationship": "与用户的关系", "likes": "喜好", "dislikes_boundaries": "禁忌与边界", "language_style": "语言风格"}
    for section, claims in persona["sections"].items():
        confirmed = [claim["text"] for claim in claims if claim["status"] == "confirmed"]
        if confirmed:
            lines.append(labels[section] + "：" + "；".join(confirmed))
    lines.append("未写入的人格信息视为未知，不得根据作品虚构真实人物传记。作品文本只描述作品叙述者或语言风格。")
    return "\n".join(lines)


def normalize_corpus(source):
    """Unique physical lines are atoms; repeated occurrences stay in the index."""
    atoms = {}
    document = None
    paragraph = 0
    for line_number, raw in enumerate(source.splitlines(), 1):
        text = raw.strip()
        if not text:
            paragraph += 1
            continue
        if re.fullmatch(r"《[^《》\n]+》", text):
            document = text[1:-1]
            paragraph = 0
            continue
        atom = atoms.setdefault(text, {"id": entry_id(text), "text": text, "occurrences": []})
        atom["occurrences"].append({"document": document, "paragraph": paragraph, "line": line_number})
    return list(atoms.values())


def validate_requested_parts(requested, source):
    lines = source.splitlines()
    for part in requested:
        if not any("\n".join(lines[index:index + len(part.splitlines())]) == part for index in range(len(lines))):
            raise YuluError("输入组合必须是同一段原文的连续行，不会保存为独立库存：" + part)


def corpus_texts(root):
    return [entry["text"] for entry in read_json(root / "corpus.json")]


def load_character(root):
    root = root.resolve()
    manifest = read_json(root / "character.json")
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS or manifest["schema_version"] != 3:
        raise YuluError("character.json 字段不符合 schema v3")
    validate_id(manifest["id"])
    if manifest["entry"] != manifest["id"] or manifest["modes"] != ["translate", "chat", "strict"] or manifest["default_mode"] not in OUTPUT_MODES:
        raise YuluError("角色入口或模式配置无效")
    if not isinstance(manifest["display_name"], str) or not manifest["display_name"].strip() or "\n" in manifest["display_name"]:
        raise YuluError("角色显示名无效")
    source = resolve_child(root, manifest["source"], "原文").read_text(encoding="utf-8")
    corpus_path = resolve_child(root, manifest["corpus"], "语料")
    entries = read_json(corpus_path)
    if not isinstance(entries, list):
        raise YuluError("corpus.json 必须是规范语言单元列表")
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "text", "occurrences"} or entry["id"] != entry_id(entry["text"]):
            raise YuluError("语料单元或稳定 ID 无效")
        if entry["id"] in ids or not entry["text"].strip() or "\n" in entry["text"]:
            raise YuluError("语料必须唯一且为原子单行")
        ids.add(entry["id"])
        if not entry["occurrences"]:
            raise YuluError("语料缺少来源位置")
        for occurrence in entry["occurrences"]:
            if set(occurrence) != {"document", "paragraph", "line"} or not isinstance(occurrence["line"], int):
                raise YuluError("语料来源位置无效")
            lines = source.splitlines()
            if occurrence["line"] < 1 or occurrence["line"] > len(lines) or lines[occurrence["line"] - 1].strip() != entry["text"]:
                raise YuluError("语料来源行号与原文不一致：" + entry["text"])
    if entries and manifest["fallback_id"] not in ids:
        raise YuluError("fallback_id 必须指向规范语料单元")
    if not entries and manifest["fallback_id"] is not None:
        raise YuluError("空语料不能指定回退项")
    policy = resolve_child(root, manifest["policy"], "规则").read_text(encoding="utf-8")
    if manifest["persona"] != "persona.json":
        raise YuluError("persona 必须指向角色目录内 persona.json")
    load_persona(root)
    return manifest, [entry["text"] for entry in entries], policy


def fallback(manifest, lines):
    for line in lines:
        if entry_id(line) == manifest["fallback_id"]:
            return line
    return lines[0] if lines else ""


def default_policy():
    return """# 扮演与语料规则

- chat 是扮演：以角色第一人称回应，不解释、不点评语料，不添加括号释义。
- translate 只输出合适的连续原文，不添加其他台词。
- strict 是特殊风格：每句包含完整原文片段，不添加括号释义。
- corpus 是语言库存，提供措辞、节奏与联想；扮演时不要求引用，不得强行堆砌。
- 只有显式角色命令切换模式或退出；help 是说明，create-character 进入配置流程并退出角色。"""


def skill_template():
    return """---
name: {id}
description: "显式扮演{display_name}，可切换转译、扮演、强制模式。需要 Claude Code >= 2.1.304。"
user-invocable: true
disable-model-invocation: true
allowed-tools:
  - Bash(${{CLAUDE_SKILL_DIR}}/scripts/yulu.py invoke *)
argument-hint: "[chat|translate|strict|help|off];[给角色的话]"
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: "${{CLAUDE_SKILL_DIR}}/scripts/yulu.py prompt"
---

!`${{CLAUDE_SKILL_DIR}}/scripts/yulu.py invoke "${{CLAUDE_SESSION_ID}}" "$ARGUMENTS"`

# 角色：{display_name}

只有用户显式调用才进入角色；`off` 退出。`persona` 是事后补充人格的配置入口，不进入扮演。

{policy}

运行规则与少量相关语言样例由激活状态和每轮上下文提供。不得读取外部语料路径。

{fallback}
"""


def replace_directory(source, destination):
    if not destination.exists():
        os.replace(str(source), str(destination))
        return
    backup = destination.with_name(destination.name + ".previous")
    if backup.exists():
        raise YuluError("备份目录已存在，请先检查：" + str(backup))
    os.replace(str(destination), str(backup))
    try:
        os.replace(str(source), str(destination))
    except OSError:
        os.replace(str(backup), str(destination))
        raise
    shutil.rmtree(str(backup))


def render_character(root, destination):
    manifest, lines, policy = load_character(root)
    if not lines:
        raise YuluError("空语料角色保留为未就绪，不生成可调用的角色包")
    skill = skill_template().format(id=manifest["id"], display_name=manifest["display_name"], policy=policy.strip(), fallback="默认回退：" + fallback(manifest, lines))
    with tempfile.TemporaryDirectory(prefix=".yulu-render-", dir=str(destination.parent)) as temp:
        staging = Path(temp) / destination.name
        shutil.copytree(str(root), str(staging), ignore=shutil.ignore_patterns("scripts", ".runtime", "SKILL.md", "*.previous", "__pycache__", "evidence"))
        (staging / "SKILL.md").write_text(skill, encoding="utf-8")
        (staging / "persona.md").write_text(persona_markdown(load_persona(root), manifest["display_name"]) + "\n", encoding="utf-8")
        shutil.copytree(str(Path(__file__).resolve().parent), str(staging / "scripts"), ignore=shutil.ignore_patterns("__pycache__"))
        replace_directory(staging, destination)


def cmd_new(args):
    validate_id(args.id)
    if args.id in {"shared", "create-character"}:
        raise YuluError("该 ID 是插件保留名称")
    root = (args.plugin_root / "characters" / args.id).resolve()
    if root != args.plugin_root.resolve() / "characters" / args.id:
        raise YuluError("角色目录无效")
    if root.exists() and not args.replace:
        raise YuluError("角色已存在；重建须显式 --replace")
    manifest = {"schema_version": 3, "id": args.id, "display_name": args.display_name.strip(), "modes": ["translate", "chat", "strict"], "default_mode": "chat", "entry": args.id, "corpus": "corpus.json", "source": "source.txt", "policy": "policy.md", "persona": "persona.json", "fallback_id": None}
    persona = validate_persona(read_json(args.persona)) if args.persona else default_persona()
    destination = root.parent / (".yulu-new-" + args.id)
    if destination.exists():
        raise YuluError("暂存目录已存在：" + str(destination))
    try:
        destination.mkdir()
        atomic_write(destination / "character.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        atomic_write(destination / "policy.md", args.policy.read_text(encoding="utf-8") if args.policy else default_policy())
        atomic_write(destination / "persona.json", json.dumps(persona, ensure_ascii=False, indent=2) + "\n")
        atomic_write(destination / "persona.md", persona_markdown(persona, manifest["display_name"]) + "\n")
        atomic_write(destination / "corpus.json", "[]\n")
        atomic_write(destination / "source.txt", "")
        load_character(destination)
        replace_directory(destination, root)
    finally:
        if destination.exists():
            shutil.rmtree(str(destination))
    print(json.dumps({"id": args.id, "status": "draft", "next": "提供人格证据并 persona-set，再导入语言原文", "character_root": str(root)}, ensure_ascii=False))


def cmd_segments(args):
    text = args.file.read_text(encoding="utf-8")
    parts = json.loads(args.parts)
    validate_lines(parts)
    atoms = {entry["text"] for entry in normalize_corpus(text)}
    validate_requested_parts(parts, text)
    for part in parts:
        if any(line not in atoms for line in part.splitlines()):
            raise YuluError("片段中的行必须能在原文中独立定位：" + part)
    print(json.dumps({"parts": parts, "note": "运行时保存原子单元，不保存邻接排列"}, ensure_ascii=False))


def cmd_import(args):
    root = args.root.resolve()
    output = args.output.resolve()
    manifest, _, _ = load_character(root)
    if not args.replace:
        raise YuluError("更新语料必须显式 --replace")
    requested = read_parts(args.corpus.resolve())
    source = args.source.read_text(encoding="utf-8")
    validate_requested_parts(requested, source)
    entries = normalize_corpus(source)
    atoms = {entry["text"]: entry for entry in entries}
    missing = [line for part in requested for line in part.splitlines() if line not in atoms]
    if missing:
        raise YuluError("片段不能跨边界或脱离原文：" + missing[0])
    if not entries:
        raise YuluError("原始语料不能为空")
    manifest["fallback_id"] = args.fallback or entry_id(next(line for line in requested[0].splitlines() if line in atoms))
    if manifest["fallback_id"] not in {entry["id"] for entry in entries}:
        raise YuluError("回退 ID 不在规范语料中")
    if output != root.parent.parent / "skills" / manifest["id"]:
        raise YuluError("角色包必须发布到项目 skills/<角色 ID>/")
    published = output.parent / ("." + output.name + ".staged")
    if published.exists():
        raise YuluError("发布暂存目录已存在：" + str(published))
    try:
        with tempfile.TemporaryDirectory(prefix=".yulu-import-", dir=str(root.parent)) as temp:
            staging = Path(temp) / root.name
            shutil.copytree(str(root), str(staging))
            atomic_write(staging / "corpus.json", json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
            atomic_write(staging / "source.txt", source)
            atomic_write(staging / "character.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            load_character(staging)
            render_character(staging, published)
            replace_directory(staging, root)
        replace_directory(published, output)
    finally:
        if published.exists():
            shutil.rmtree(published)
    print(json.dumps({"atoms": len(entries), "input_parts": len(requested), "derived_combinations": sum("\n" in x for x in requested), "package": str(output)}, ensure_ascii=False))


def cmd_persona_set(args):
    root = args.root.resolve()
    manifest, _, _ = load_character(root)
    persona = validate_persona(read_json(args.file))
    if args.confirm:
        unconfirmed = [(section, claim["text"]) for section, claims in persona["sections"].items() for claim in claims if claim["status"] != "confirmed"]
        if unconfirmed:
            raise YuluError("仍有未确认或弃用条目；确认发布前请修订：" + str(unconfirmed))
    atomic_write(root / "persona.json", json.dumps(persona, ensure_ascii=False, indent=2) + "\n")
    atomic_write(root / "persona.md", persona_markdown(persona, manifest["display_name"]) + "\n")
    print(json.dumps({"sections": {key: len(value) for key, value in persona["sections"].items()}, "confirmed": args.confirm}, ensure_ascii=False))


def cmd_persona_show(args):
    print(json.dumps(load_persona(args.root.resolve()), ensure_ascii=False, indent=2))


def cmd_evidence_add(args):
    root = args.root.resolve()
    load_character(root)
    if args.kind not in {"biography", "interview", "work_text", "user_setting"}:
        raise YuluError("证据类型无效")
    target = root / "evidence" / (args.kind + "-" + hashlib.sha256(str(args.file.resolve()).encode()).hexdigest()[:8] + "-" + args.file.name)
    if target.exists():
        raise YuluError("证据已存在：" + str(target))
    target.parent.mkdir(exist_ok=True)
    shutil.copy2(str(args.file), str(target))
    print(json.dumps({"source_ref": str(target.relative_to(root)), "source_type": args.kind, "next": "creator 阅读后起草 persona-set；作品文本不得证明真人现实人格"}, ensure_ascii=False))


def cmd_publish(args):
    root = args.root.resolve()
    load_character(root)
    render_character(root, args.output.resolve())
    print(json.dumps({"package": str(args.output.resolve())}, ensure_ascii=False))


def cmd_validate(args):
    manifest, lines, _ = load_character(args.root)
    print(json.dumps({"id": manifest["id"], "status": "ready" if lines else "empty", "entries": len(lines), "persona": "persona.json"}, ensure_ascii=False))
    if args.ready and not lines:
        raise YuluError("角色语料为空，不可激活")


def cmd_check(args):
    _, lines, _ = load_character(args.root)
    valid = validate_response(sys.stdin.read(), lines, args.mode)
    print(json.dumps({"valid": valid, "mode": args.mode}, ensure_ascii=False))
    return 0 if valid else 1


def validate_response(text, lines, mode="translate"):
    if not isinstance(text, str) or not text or not lines:
        return False
    if mode == "translate":
        return all(line in set(lines) for line in text.split("\n"))
    if mode == "chat":
        return True
    if mode != "strict":
        return False
    sentences = list(re.finditer(r"[^。！？!?\n]+[。！？!?]?", text))
    return all(any(line in sentence.group() for line in lines) for sentence in sentences if sentence.group().strip())


def state_path(root, session_id):
    return session_path(Path(os.environ.get("CLAUDE_PLUGIN_DATA", str(root / ".runtime"))), session_id)


def read_active(root, session_id):
    path = state_path(root, session_id)
    if path.with_suffix(".off").is_file() or not path.is_file():
        return None
    try:
        state = read_json(path)
    except YuluError:
        # 状态损坏只停用角色，不允许拦截整个会话的输入。
        return None
    if not isinstance(state, dict) or set(state) != {"schema_version", "character_id", "character_root", "output_mode"}:
        return None
    if state["schema_version"] not in {2, 3}:
        return None
    if state["character_root"] != str(root.resolve()):
        return None
    manifest = load_character(root)[0]
    if state["character_id"] != manifest["id"] or state["output_mode"] not in OUTPUT_MODES:
        return None
    if state["schema_version"] == 2:
        state = {"schema_version": 3, "character_id": state["character_id"], "character_root": state["character_root"], "output_mode": state["output_mode"]}
        atomic_write(path, json.dumps(state, ensure_ascii=False) + "\n")
    return state


def activate(root, session_id, output_mode=None):
    manifest, lines, _ = load_character(root)
    if not lines:
        raise YuluError("角色语料为空，请先导入")
    path = state_path(root, session_id)
    previous = read_active(root, session_id) if output_mode is None and path.is_file() else None
    mode = output_mode or (previous["output_mode"] if previous else manifest["default_mode"])
    if mode not in OUTPUT_MODES:
        raise YuluError("角色不支持该输出模式")
    state = {"schema_version": 3, "character_id": manifest["id"], "character_root": str(root.resolve()), "output_mode": mode}
    atomic_write(path, json.dumps(state, ensure_ascii=False) + "\n")
    disabled = path.with_suffix(".off")
    if disabled.exists():
        disabled.unlink()
    return state


def deactivate(data_root, session_id):
    path = session_path(data_root, session_id)
    atomic_write(path.with_suffix(".off"), "off\n")
    print(json.dumps({"active": False}, ensure_ascii=False))


def cmd_off(args):
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    if not session_id:
        raise YuluError("关闭角色必须在 Claude Code 会话中显式执行")
    deactivate(Path(os.environ.get("CLAUDE_PLUGIN_DATA", str(args.root / ".runtime"))), session_id)


def cmd_invoke(args):
    os.environ["CLAUDE_SESSION_ID"] = args.session_id
    os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(args.root.parent.parent))
    os.environ.setdefault("CLAUDE_PLUGIN_DATA", str(args.root / ".runtime"))
    raw = (args.request or "").strip()
    control, separator, message = raw.partition(";")
    if not separator:
        control, message = raw, ""
    if control in {"off", "关闭"}:
        cmd_off(args)
        return
    if control in {"help", "帮助"}:
        print((Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "README.md").read_text(encoding="utf-8"))
        return
    args.mode = control if control in MODE_ALIASES else "default"
    args.dialogue = raw if not separator else message
    activate(args.root, args.session_id, MODE_ALIASES.get(args.mode))
    context = policy_context(args.root, args.session_id)
    if args.dialogue:
        context += "\n用户对话：" + args.dialogue
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}, ensure_ascii=False))


def read_event():
    try:
        event = json.load(sys.stdin)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise YuluError("钩子输入不是有效 JSON：{}".format(exc)) from exc
    if not isinstance(event, dict) or not isinstance(event.get("session_id"), str):
        raise YuluError("钩子输入缺少 session_id")
    return event


def retrieve(lines, query, limit=6):
    """Deterministic token scoring; no embeddings or model calls."""
    query = (query or "").strip()
    words = set(re.findall(r"[a-zA-Z0-9]+|[一-鿿]{2,}", query.lower()))
    grams = {query[i:i + 2] for i in range(len(query) - 1) if re.fullmatch(r"[一-鿿]{2}", query[i:i + 2])}
    scored = []
    for position, text in enumerate(lines):
        lowered = text.lower()
        score = (12 if query and query in lowered else 0) + sum(4 for word in words if word in lowered) + sum(1 for gram in grams if gram in lowered)
        if score:
            scored.append((-score, position, text))
    return [text for _, _, text in sorted(scored)[:limit]]


def policy_context(root, session_id):
    manifest, lines, policy = load_character(root)
    state = read_active(root, session_id)
    mode = state["output_mode"] if state else manifest["default_mode"]
    instructions = {
        "translate": "转译：只选择完整原文表达，不加释义或其他台词。",
        "chat": "扮演：以角色第一人称自然回应，不解说语料，不加括号释义，不自称通用助手。",
        "strict": "强制：每句含完整原文片段，不加括号释义；这是风格模式，不是人格定义。",
    }[mode]
    return """<yulu-active-character>
本会话由用户显式选择扮演 {display_name}，模式：{mode_name}。
{instruction}
在不违反更高优先级指令的前提下，以下人格和扮演行为优先于通用助手的客套、解说及说教反射；不要声称自己改变了底层模型或系统指令。
{persona}
{policy}
以下仅是按本轮输入检索的语言库存样例，不是人格事实，不要求引用：
{examples}
</yulu-active-character>""".format(display_name=manifest["display_name"], mode_name=MODE_NAMES[mode], instruction=instructions, persona=persona_markdown(load_persona(root), manifest["display_name"]), policy=policy.strip(), examples="（本轮无强制引用）")


def cmd_prompt(args):
    event = read_event()
    if not read_active(args.root.resolve(), event["session_id"]):
        return 0
    context = policy_context(args.root, event["session_id"])
    manifest, lines, _ = load_character(args.root)
    examples = retrieve(lines, event.get("prompt", ""))
    context = context.replace("（本轮无强制引用）", "\n".join(examples) if examples else "本轮无匹配样例，按人格自然回应，不强行引用。")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}, ensure_ascii=False))


def parser():
    commands = argparse.ArgumentParser(prog="yulu")
    subcommands = commands.add_subparsers(dest="command", required=True)
    for name in ("prompt", "off", "invoke"):
        command = subcommands.add_parser(name)
        if name == "invoke":
            command.add_argument("session_id")
            command.add_argument("request", nargs="?")
        else:
            command.add_argument("root", type=Path, nargs="?")
        command.set_defaults(function=globals()["cmd_" + name])
    command = subcommands.add_parser("new")
    command.add_argument("id")
    command.add_argument("display_name")
    command.add_argument("--plugin-root", type=Path, required=True)
    command.add_argument("--policy", type=Path)
    command.add_argument("--persona", type=Path)
    command.add_argument("--replace", action="store_true")
    command.set_defaults(function=cmd_new)
    for name in ("persona-set", "persona-show", "evidence-add", "publish", "validate"):
        command = subcommands.add_parser(name)
        command.add_argument("root", type=Path)
        if name == "persona-set":
            command.add_argument("file", type=Path)
            command.add_argument("--confirm", action="store_true")
        if name == "persona-show":
            command.set_defaults(function=cmd_persona_show)
        elif name == "evidence-add":
            command.add_argument("file", type=Path)
            command.add_argument("--kind", required=True)
        elif name == "publish":
            command.add_argument("--output", type=Path, required=True)
        elif name == "validate":
            command.add_argument("--ready", action="store_true")
        command.set_defaults(function=globals()["cmd_" + name.replace("-", "_")])
    command = subcommands.add_parser("import")
    command.add_argument("root", type=Path)
    command.add_argument("corpus", type=Path)
    command.add_argument("--source", type=Path, required=True)
    command.add_argument("--replace", action="store_true")
    command.add_argument("--fallback")
    command.add_argument("--output", type=Path, required=True)
    command.set_defaults(function=cmd_import)
    for name in ("segments", "check"):
        command = subcommands.add_parser(name)
        command.add_argument("root", type=Path)
        if name == "segments":
            command.add_argument("--parts", required=True)
        else:
            command.add_argument("--mode", choices=sorted(OUTPUT_MODES), default="chat")
        command.set_defaults(function=globals()["cmd_" + name])
    return commands


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command in {"prompt", "off", "invoke"} and getattr(args, "root", None) is None:
        args.root = Path(__file__).resolve().parent.parent
    try:
        return args.function(args) or 0
    except (YuluError, OSError, UnicodeError) as exc:
        if args.command == "prompt":
            print(json.dumps({"systemMessage": "Yulu 角色上下文未更新：{}".format(exc)}, ensure_ascii=False))
        else:
            print("Yulu 错误：{}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
