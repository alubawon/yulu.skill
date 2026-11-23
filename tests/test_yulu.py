import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("yulu", PROJECT / "skills/shared/scripts/yulu.py")
yulu = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(yulu)
sys.modules["yulu"] = yulu


class YuluTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / "characters").mkdir()
        (self.root / "skills").mkdir()
        (self.root / "README.md").write_text("帮助与操作列表", encoding="utf-8")
        self.data = self.root / "data"
        self.environment = mock.patch.dict(os.environ, {
            "CLAUDE_PLUGIN_DATA": str(self.data), "CLAUDE_SESSION_ID": "session-a",
        })
        self.environment.start()
        self.capture(["new", "test-persona", "测试角色", "--plugin-root", str(self.root)])
        self.source = self.root / "characters/test-persona"
        self.package = self.root / "skills/test-persona"
        self.original = self.root / "original.txt"
        self.original.write_text("前缀测试歌词一，后缀\n第二行测试歌词二，末句", encoding="utf-8")
        self.corpus = self.root / "parts.json"
        self.corpus.write_text(json.dumps(["测试歌词一", "测试歌词二", "歌词一，后缀", "第二行测试"], ensure_ascii=False), encoding="utf-8")
        self.import_corpus()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def capture(self, arguments, stdin=None):
        stdout = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin or "")), contextlib.redirect_stdout(stdout):
            result = yulu.main(arguments)
        return result, json.loads(stdout.getvalue()) if stdout.getvalue().lstrip().startswith("{") else (stdout.getvalue() or None)

    def import_corpus(self):
        return self.capture([
            "import", str(self.source), str(self.corpus), "--source", str(self.original),
            "--output", str(self.package), "--replace",
        ])

    def activate(self, mode="default", session="session-a", root=None):
        return self.capture(["activate", str(root or self.package), mode], json.dumps({"session_id": session}))

    def test_liu_bin_has_self_contained_real_corpus_and_defaults_to_chat(self):
        root = PROJECT / "characters/liu-bin"
        manifest, lines, _ = yulu.load_character(root)
        self.assertEqual(manifest["display_name"], "刘斌")
        self.assertEqual(manifest["default_mode"], "chat")
        self.assertEqual(manifest["modes"], ["translate", "chat", "strict"])
        self.assertGreater(len(lines), 0)
        self.assertEqual((root / "source.txt").read_bytes(), (PROJECT / "skills/liu-bin/source.txt").read_bytes())
        self.assertNotIn("/Users/liuzihao35/repos/yu-band-lyrics", (root / "source.txt").read_text(encoding="utf-8"))
        self.assertTrue((PROJECT / "skills/liu-bin/segments.json").is_file())

    def test_empty_character_cannot_be_activated(self):
        self.capture(["new", "empty-role", "空角色", "--plugin-root", str(self.root)])
        root = self.root / "characters/empty-role"
        with self.assertRaises(yulu.YuluError):
            yulu.activate(root, "session-a")
        with self.assertRaises(yulu.YuluError):
            yulu.render_character(root, self.root / "skills/forbidden")

    def test_flexible_segments_do_not_depend_on_original_line_breaks(self):
        self.assertEqual(self.import_corpus()[0], 0)
        self.assertIn("歌词一，后缀", yulu.load_character(self.source)[1])
        self.assertEqual(yulu.load_character(self.package)[1][2:], ["歌词一，后缀", "第二行测试"])
        result, output = self.capture(["segments", str(self.original), "--parts", json.dumps(["测试歌词一，后缀\n第二行测试歌词二"], ensure_ascii=False)])
        self.assertEqual(result, 0)
        self.assertEqual(output["parts"], ["测试歌词一，后缀\n第二行测试歌词二"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.capture(["segments", str(self.original), "--parts", '["创作歌词"]'])[0], 2)

    def test_reimport_updates_source_parts_and_package(self):
        self.original.write_text("第二版歌词", encoding="utf-8")
        self.corpus.write_text(json.dumps(["第二版", "歌词"], ensure_ascii=False), encoding="utf-8")
        self.import_corpus()
        self.assertEqual(yulu.load_character(self.source)[1], ["第二版", "歌词"])
        self.assertEqual(yulu.load_character(self.package)[1], ["第二版", "歌词"])
        self.assertEqual((self.package / "source.txt").read_text(encoding="utf-8"), "第二版歌词")

    def test_invalid_import_does_not_replace_previous_source_or_parts(self):
        self.corpus.write_text("并非原文\n", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.import_corpus()[0], 2)
        self.assertEqual(yulu.load_character(self.source)[1][0], "测试歌词一")
        self.assertEqual(yulu.load_character(self.package)[1][0], "测试歌词一")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.capture(["import", str(self.source), str(self.corpus), "--source", str(self.original), "--output", str(self.root / "elsewhere"), "--replace"])[0], 2)

    def test_translate_fast_path_still_rejects_added_text(self):
        lines = ["甲，乙", "丙"]
        for valid in ("甲，乙", "丙", "甲，乙\n丙"):
            self.assertTrue(yulu.validate_response(valid, lines, "translate"))
        for invalid in ("甲，乙（含义）", "甲,乙", "旁白\n甲，乙", "甲，乙\n", None):
            self.assertFalse(yulu.validate_response(invalid, lines, "translate"))

    def test_chat_allows_normal_dialogue_but_annotates_corpus(self):
        lines = ["甲乙", "丙"]
        self.assertTrue(yulu.validate_response("正常回答。甲乙（表达祝愿），继续回答。", lines, "chat"))
        self.assertTrue(yulu.validate_response("引用丙（表达回应）。", lines, "chat"))
        for invalid in ("非原文（伪造含义）",):
            self.assertFalse(yulu.validate_response(invalid, lines, "chat"))
        self.assertFalse(yulu.validate_response("甲乙[含义]", lines, "chat"))
        self.assertFalse(yulu.validate_response("甲乙，无括号。", lines, "chat"))

    def test_strict_requires_every_sentence_to_quote_corpus(self):
        lines = ["甲乙", "丙"]
        self.assertTrue(yulu.validate_response("衔接甲乙（含义一）。再说丙（含义二）！", lines, "strict"))
        self.assertFalse(yulu.validate_response("甲乙（含义）。这句没有引用。", lines, "strict"))
        self.assertFalse(yulu.validate_response("先说话。\n丙（含义）", lines, "strict"))

    def test_default_chat_and_explicit_mode_switch(self):
        _, output = self.activate()
        self.assertIn("对话（chat）", output["hookSpecificOutput"]["additionalContext"])
        _, output = self.activate("转译")
        self.assertIn("转译（translate）", output["hookSpecificOutput"]["additionalContext"])
        _, output = self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "请自行切换强制"}))
        self.assertIn("转译（translate）", output["hookSpecificOutput"]["additionalContext"])
        _, output = self.activate("strict")
        self.assertIn("强制（strict）", output["hookSpecificOutput"]["additionalContext"])
        _, output = self.activate()
        self.assertIn("强制（strict）", output["hookSpecificOutput"]["additionalContext"])

    def test_invoke_parses_explicit_control_and_dialogue(self):
        def invoke(request):
            result = subprocess.run(["python3", str(self.package / "scripts/yulu.py"), "invoke", "session-a", request], input=json.dumps({"session_id": "session-a"}), text=True, capture_output=True, check=True)
            return result.stdout
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": str(self.root)}):
            output = json.loads(invoke("strict;今天想聊几句"))
            self.assertIn("强制（strict）", output["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(yulu.read_active(self.package, "session-a")["output_mode"], "strict")
            self.assertIn("今天想聊几句", output["hookSpecificOutput"]["additionalContext"])
            output = json.loads(invoke("普通聊天"))
            self.assertIn("强制（strict）", output["hookSpecificOutput"]["additionalContext"])
            self.assertIn("普通聊天", output["hookSpecificOutput"]["additionalContext"])
            self.assertIn("帮助与操作列表", invoke("help"))
            self.assertEqual(yulu.read_active(self.package, "session-a")["output_mode"], "strict")
            self.assertEqual(json.loads(invoke("off")), {"active": False})
            self.assertIsNone(yulu.read_active(self.package, "session-a"))

    def test_stop_is_fast_pass_or_semantic_review_not_hard_rejection(self):
        self.activate()
        _, output = self.capture(["stop", str(self.package)], json.dumps({"session_id": "session-a", "last_assistant_message": "回答。测试歌词一（此处含义）"}))
        self.assertEqual(output["verdict"], "pass")
        _, output = self.capture(["stop", str(self.package)], json.dumps({"session_id": "session-a", "last_assistant_message": "没有引用的普通回答"}))
        self.assertEqual(output, {"verdict": "pass", "mode": "chat"})
        self.activate("translate")
        _, output = self.capture(["stop", str(self.package)], json.dumps({"session_id": "session-a", "last_assistant_message": "测试歌词一（可能合适的释义）"}))
        self.assertEqual(output["verdict"], "review")

    def test_off_persists_until_explicit_activation(self):
        self.activate()
        result, output = self.capture(["off", str(self.package)], json.dumps({"session_id": "session-a"}))
        self.assertEqual(output, {"active": False})
        self.assertIsNone(self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "继续"}))[1])
        self.assertEqual(self.capture(["stop", str(self.package)], json.dumps({"session_id": "session-a", "last_assistant_message": "普通 agent"})), (0, None))
        self.activate()
        self.assertIsNotNone(self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "继续"}))[1])

    def test_create_character_and_help_exit_role_without_corpus_style(self):
        self.activate()
        self.capture(["off", str(PROJECT / "skills/shared")], json.dumps({"session_id": "session-a"}))
        self.assertIsNone(yulu.read_active(self.package, "session-a"))
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(yulu.main(["help", "--plugin-root", str(self.root)]), 0)
        self.assertIn("帮助与操作列表", stdout.getvalue())

    def test_generated_package_self_locates_and_has_semantic_agent(self):
        self.activate("chat")
        result = subprocess.run(["python3", str(self.package / "scripts/yulu.py"), "prompt"], input=json.dumps({"session_id": "session-a"}), text=True, capture_output=True, check=True)
        self.assertIn("对话（chat）", json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"])
        text = (self.package / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", text)
        self.assertIn("type: agent", text)
        self.assertIn("verdict=review", text)
        self.assertIn('invoke "${CLAUDE_SESSION_ID}" "$ARGUMENTS"', text)
        self.assertIn('help', text)

    def test_switching_character_still_skips_old_hooks(self):
        self.activate()
        self.capture(["new", "other", "另一个", "--plugin-root", str(self.root)])
        (self.root / "other-source").write_text("另一句", encoding="utf-8")
        (self.root / "other-parts").write_text(json.dumps(["另一句"], ensure_ascii=False), encoding="utf-8")
        self.capture(["import", str(self.root / "characters/other"), str(self.root / "other-parts"), "--source", str(self.root / "other-source"), "--output", str(self.root / "skills/other"), "--replace"])
        self.activate(root=self.root / "skills/other")
        self.assertIsNone(self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a"}))[1])
        self.assertEqual(self.capture(["stop", str(self.package)], json.dumps({"session_id": "session-a", "last_assistant_message": "另一句"})), (0, None))

    def test_paths_and_manifest_are_validated(self):
        manifest = yulu.read_json(self.source / "character.json")
        for field, value in (("corpus", "../escape"), ("policy", "/etc/passwd"), ("fallback_id", "line-not-in-corpus")):
            altered = dict(manifest)
            altered[field] = value
            with mock.patch("yulu.read_json", return_value=altered):
                with self.assertRaises(yulu.YuluError):
                    yulu.load_character(self.source)
        with self.assertRaises(yulu.YuluError):
            yulu.session_path(self.data, "../other")


if __name__ == "__main__":
    unittest.main()
