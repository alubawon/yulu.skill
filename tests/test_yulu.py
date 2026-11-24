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
        (self.root / "README.md").write_text("帮助", encoding="utf-8")
        self.environment = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.root / "data"), "CLAUDE_SESSION_ID": "session-a"})
        self.environment.start()
        self.capture(["new", "test-persona", "测试角色", "--plugin-root", str(self.root)])
        self.source = self.root / "characters/test-persona"
        self.package = self.root / "skills/test-persona"
        self.original = self.root / "original.txt"
        self.original.write_text("《作品》\n甲乙\n丙\n\n甲乙\n丁", encoding="utf-8")
        self.corpus = self.root / "parts.json"
        self.corpus.write_text(json.dumps(["甲乙", "丙", "甲乙\n丙", "丁"], ensure_ascii=False), encoding="utf-8")
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
        return self.capture(["import", str(self.source), str(self.corpus), "--source", str(self.original), "--output", str(self.package), "--replace"])

    def activate(self, mode="default", session="session-a", root=None):
        request = mode if mode != "default" else ""
        result = subprocess.run([str((root or self.package) / "scripts/yulu.py"), "invoke", session, request], text=True, capture_output=True, check=True)
        return result.returncode, json.loads(result.stdout)

    def persona(self, status="confirmed"):
        data = yulu.default_persona()
        data["subject_kind"] = "fictional"
        data["sections"]["background"].append({"text": "一名旅行者", "source_type": "user_setting", "source_ref": "user://explicit", "confidence": "high", "status": status})
        data["sections"]["language_style"].append({"text": "短句，不解说", "source_type": "work_text", "source_ref": "source.txt:1-4", "confidence": "medium", "status": status})
        path = self.root / "persona.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_liu_bin_has_persona_and_normalized_corpus(self):
        root = PROJECT / "characters/liu-bin"
        manifest, lines, _ = yulu.load_character(root)
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(manifest["display_name"], "刘斌")
        self.assertTrue((root / "persona.json").is_file())
        self.assertLess(len(lines), 400)
        self.assertTrue(all("\n" not in line for line in lines))
        self.assertFalse(any("身躯在人群中穿梭 在不知不觉中冰冷的融化\n幻想为你挺身而出" in line for line in lines))

    def test_normalization_deduplicates_repeats_without_saving_combinations(self):
        entries = yulu.read_json(self.source / "corpus.json")
        self.assertEqual([entry["text"] for entry in entries], ["甲乙", "丙", "丁"])
        self.assertEqual(len(entries[0]["occurrences"]), 2)
        self.assertEqual(entries[0]["occurrences"][1]["line"], 5)
        self.assertEqual(len(yulu.corpus_texts(self.package)), 3)

    def test_invalid_source_location_and_cross_boundary_are_rejected(self):
        self.original.write_text("《甲》\n甲乙\n\n《乙》\n丙", encoding="utf-8")
        self.corpus.write_text(json.dumps(["甲乙\n丙"], ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.import_corpus()[0], 2)
        self.assertEqual(len(yulu.read_json(self.source / "corpus.json")), 3)

    def test_persona_requires_provenance_and_separates_draft(self):
        path = self.persona("draft")
        _, output = self.capture(["persona-set", str(self.source), str(path)])
        self.assertFalse(output["confirmed"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.capture(["persona-set", str(self.source), str(path), "--confirm"])[0], 2)
        self.capture(["persona-set", str(self.source), str(self.persona()), "--confirm"])
        self.capture(["publish", str(self.source), "--output", str(self.package)])
        self.assertIn("一名旅行者", (self.package / "persona.md").read_text())
        data = json.loads(self.persona().read_text())
        data["sections"]["background"][0]["source_type"] = "inference"
        path = self.root / "bad-persona.json"
        path.write_text(json.dumps(data, ensure_ascii=False))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.capture(["persona-set", str(self.source), str(path), "--confirm"])[0], 2)

    def test_evidence_input_is_copied_with_type(self):
        evidence = self.root / "interview.txt"
        evidence.write_text("访谈原文", encoding="utf-8")
        _, output = self.capture(["evidence-add", str(self.source), str(evidence), "--kind", "interview"])
        stored = self.source / output["source_ref"]
        self.assertEqual(stored.read_text(), "访谈原文")
        self.assertEqual(output["source_type"], "interview")

    def test_chat_is_roleplay_without_annotation_and_retrieves(self):
        self.capture(["persona-set", str(self.source), str(self.persona()), "--confirm"])
        self.capture(["publish", str(self.source), "--output", str(self.package)])
        _, output = self.activate("chat")
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("扮演：以角色第一人称", context)
        self.assertIn("一名旅行者", context)
        self.assertNotIn("紧跟中文括号", context)
        _, output = self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "说说甲乙"}))
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("甲乙", context)
        self.assertNotIn("丙", context)
        self.assertLess(len(context), 2000)

    def test_no_matching_context_does_not_dump_corpus(self):
        self.activate()
        _, output = self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "完全无关的输入"}))
        self.assertIn("本轮无匹配样例", output["hookSpecificOutput"]["additionalContext"])

    def test_no_stop_even_with_legacy_switch_and_off(self):
        with mock.patch.dict(os.environ, {"YULU_REVIEW": "1"}):
            self.import_corpus()
        text = (self.package / "SKILL.md").read_text()
        self.assertNotIn("Stop:", text)
        self.assertNotIn("cmd_stop", (self.package / "scripts/yulu.py").read_text())
        self.activate()
        result, output = self.capture(["off", str(PROJECT / "skills/shared")])
        self.assertEqual(output, {"active": False})
        self.assertIsNone(self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "继续"}))[1])

    def test_legacy_v2_state_migrates_instead_of_blocking_prompt(self):
        self.activate("strict")
        path = self.root / "data/sessions/session-a.json"
        path.write_text(json.dumps({"schema_version": 2, "character_id": "test-persona", "character_root": str(self.package.resolve()), "output_mode": "strict"}, ensure_ascii=False), encoding="utf-8")
        result, output = self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "继续"}))
        self.assertEqual(result, 0)
        self.assertIn("强制", output["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(yulu.read_json(path)["schema_version"], 3)

    def test_unreadable_or_unknown_state_deactivates_without_blocking(self):
        self.activate()
        path = self.root / "data/sessions/session-a.json"
        for content in ("不是 JSON", json.dumps({"schema_version": 99}), json.dumps({"schema_version": 3, "character_id": "test-persona", "character_root": str(self.package.resolve()), "output_mode": "未知模式"})):
            path.write_text(content, encoding="utf-8")
            result, output = self.capture(["prompt", str(self.package)], json.dumps({"session_id": "session-a", "prompt": "继续"}))
            self.assertEqual(result, 0)
            self.assertIsNone(output)
        self.assertIsNone(yulu.read_active(self.package, "session-a"))

    def test_generated_package_is_self_contained(self):
        self.assertEqual((self.package / "persona.json").read_bytes(), (self.source / "persona.json").read_bytes())
        self.assertTrue((self.package / "scripts/yulu.py").is_file())
        self.assertNotIn("evidence", [path.name for path in self.package.iterdir()])


if __name__ == "__main__":
    unittest.main()
