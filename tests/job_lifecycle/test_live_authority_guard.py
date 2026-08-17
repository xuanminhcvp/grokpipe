"""Live worker chỉ phát fact/file; không được hồi sinh authority legacy."""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LiveAuthorityGuardTest(unittest.TestCase):
    def test_live_paths_khong_retry_enqueue_rotate_hay_ghi_jobs(self):
        forbidden_calls = {
            "_enqueue", "_xep", "_xep_lai_sau", "_xoay_chrome",
            "_dat_nhan_lo", "_generate_lo", "_generate_lo_ruot",
            "_gen_video", "put", "put_nowait",
        }
        violations = []
        for path in (
            ROOT / "sfboard/sfboard.py",
            ROOT / "sfboard/live_executor.py",
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            functions = [
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and (node.name.startswith("_live_")
                     or node.name.startswith("run_image_attempt")
                     or node.name.startswith("run_video_attempt"))
            ]
            for function in functions:
                for node in ast.walk(function):
                    if isinstance(node, ast.Call):
                        name = (
                            node.func.id if isinstance(node.func, ast.Name)
                            else node.func.attr
                            if isinstance(node.func, ast.Attribute) else ""
                        )
                        if name in forbidden_calls:
                            violations.append(
                                f"{path.name}:{node.lineno}:call {name}")
                    targets = (
                        node.targets if isinstance(node, ast.Assign)
                        else [node.target]
                        if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else []
                    )
                    if any(
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "JOBS"
                        for target in targets
                    ):
                        violations.append(
                            f"{path.name}:{node.lineno}:write JOBS")

        self.assertEqual(violations, [], violations)


if __name__ == "__main__":
    unittest.main()
