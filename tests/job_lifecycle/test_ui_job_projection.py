"""Projection hàng đợi trên trình duyệt phải tôn trọng thao tác Clear."""

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class UiJobProjectionTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("máy này không có node")

    def test_clear_an_job_terminal_nhung_khong_an_job_dang_chay(self):
        program = r"""
const { jobsTuLifecycle } = require('./sfboard/ui/job-projection.js');
const lifecycle = {
  source: 'runtime',
  hidden_terminal_job_ids: ['job-done'],
  jobs: [
    { job_id: 'job-done', asset_id: 'REF_DONE', state: 'completed' },
    { job_id: 'job-live', asset_id: 'REF_LIVE', state: 'running' },
  ],
};
const projected = jobsTuLifecycle(lifecycle, {});
if (Object.hasOwn(projected, 'REF_DONE')) process.exit(10);
if (projected.REF_LIVE?.state !== 'running') process.exit(11);

const beforeClear = jobsTuLifecycle({ ...lifecycle, hidden_terminal_job_ids: [] }, {});
if (beforeClear.REF_DONE?.state !== 'done') process.exit(12);

const afterRerun = jobsTuLifecycle({
  source: 'runtime',
  hidden_terminal_job_ids: ['job-new'],
  jobs: [
    { job_id: 'job-old', asset_id: 'REF_RERUN', state: 'needs_attention' },
    { job_id: 'job-new', asset_id: 'REF_RERUN', state: 'completed' },
  ],
}, {});
if (Object.hasOwn(afterRerun, 'REF_RERUN')) process.exit(13);
"""
        result = subprocess.run(
            ["node", "-e", program], cwd=ROOT,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
