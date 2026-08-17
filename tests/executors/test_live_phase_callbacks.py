"""Guard ranh giới credit/phase mà không cần mở Chrome thật."""

import ast
import inspect
from pathlib import Path
import unittest

from grokpipe.executors.image_chatgpt import ChatGPTSession
from grokpipe.executors.video_grok import GrokSession


ROOT = Path(__file__).resolve().parents[2]


def _method(path, class_name, method_name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name)
    return next(
        node for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name)


def _call_lines(method, name):
    lines = []
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else ""
        )
        if called == name:
            lines.append(node.lineno)
    return sorted(lines)


class LivePhaseCallbackContractTest(unittest.TestCase):
    def test_chatgpt_callbacks_la_keyword_optional(self):
        signature = inspect.signature(ChatGPTSession.generate_lo)

        for name in ("on_submitted", "on_waiting_provider"):
            parameter = signature.parameters[name]
            self.assertIsNone(parameter.default)
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_chatgpt_chi_bao_submitted_sau_gui_thanh_cong(self):
        method = _method(
            ROOT / "grokpipe/grokpipe/executors/image_chatgpt.py",
            "ChatGPTSession", "generate_lo")
        gui = _call_lines(method, "_gui")
        submitted = _call_lines(method, "on_submitted")
        waiting = _call_lines(method, "on_waiting_provider")

        self.assertEqual(len(gui), 1)
        self.assertEqual(len(submitted), 1)
        self.assertEqual(len(waiting), 1)
        self.assertLess(gui[0], submitted[0])
        self.assertLess(submitted[0], waiting[0])
        guard = next(
            node for node in method.body
            if isinstance(node, ast.If) and node.lineno == gui[0])
        self.assertTrue(any(isinstance(node, ast.Return) for node in guard.body))
        self.assertLess(max(node.end_lineno for node in guard.body), submitted[0])

    def test_grok_callbacks_la_keyword_optional(self):
        signature = inspect.signature(GrokSession.generate)

        for name in (
            "before_submit", "on_submitted", "on_waiting_provider",
            "on_downloading", "on_saving",
        ):
            parameter = signature.parameters[name]
            self.assertIsNone(parameter.default)
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_grok_reserve_va_phase_bao_quanh_dung_submit_download_save(self):
        method = _method(
            ROOT / "grokpipe/grokpipe/executors/video_grok.py",
            "GrokSession", "generate")
        before = _call_lines(method, "before_submit")
        submit = _call_lines(method, "_bam_submit")
        submitted = _call_lines(method, "on_submitted")
        waiting = _call_lines(method, "on_waiting_provider")
        downloading = _call_lines(method, "on_downloading")
        download = _call_lines(method, "_tai_ve")
        saving = _call_lines(method, "on_saving")
        makedirs = _call_lines(method, "makedirs")

        self.assertEqual(len(before), 1)
        self.assertEqual(len(submit), 1)
        self.assertEqual(len(submitted), 1)
        self.assertEqual(len(waiting), 1)
        self.assertEqual(len(downloading), 1)
        self.assertEqual(len(saving), 1)
        self.assertLess(before[0], submit[0])
        self.assertLess(submit[0], submitted[0])
        self.assertLess(submitted[0], waiting[0])
        self.assertLess(waiting[0], downloading[0])
        self.assertLess(downloading[0], download[0])
        self.assertLess(download[0], saving[0])
        self.assertLess(saving[0], makedirs[0])


if __name__ == "__main__":
    unittest.main()
