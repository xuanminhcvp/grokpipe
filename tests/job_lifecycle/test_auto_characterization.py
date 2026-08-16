import threading
import unittest
from pathlib import Path

from helpers import function_source, load_sfboard, make_handler, reset_legacy_state

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard/sfboard.py"


class _BlockingBoard:
    """Dừng vòng auto giữa lúc đã chụp state và trước lúc enqueue."""

    def __init__(self, data):
        self.path = __file__
        self.data = data
        self.da_vao = threading.Event()
        self.tiep_tuc = threading.Event()

    def read(self):
        return self.data

    def find_file(self, _asset_id):
        self.da_vao.set()
        if not self.tiep_tuc.wait(2):
            raise AssertionError("vòng auto không được nhả để hoàn tất test")
        return None

    def video_file(self, _shot_id):
        return None


class _ReadyVideoBoard:
    """Board trơ: shot đã có start frame, chưa có video.

    `co_anh=False` dùng cho nhánh ảnh — SF chưa có file nên auto coi là còn
    thiếu và sẽ xếp lô."""

    path = __file__

    def __init__(self, scene, co_anh=True):
        self.scene = scene
        self.co_anh = co_anh

    def read(self):
        return {"scenes": [self.scene]}

    def find_file(self, _asset_id):
        return "/fake/start-frame.png" if self.co_anh else None

    def video_file(self, _shot_id):
        return None


class _ObservedLock:
    """Lock thật có thêm tín hiệu khi thread stop bắt đầu chờ acquire."""

    def __init__(self):
        self._lock = threading.Lock()
        self.stop_dang_cho = threading.Event()

    def __enter__(self):
        if threading.current_thread().name == "stop-all-test":
            self.stop_dang_cho.set()
        self._lock.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self._lock.release()


class AutoCharacterizationTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.m.AUTO.clear()
        self.board_cu = self.m.BOARD
        self.accounts_cu = self.m.ACCOUNTS
        self.m.ACCOUNTS = []

    def tearDown(self):
        self.m.BOARD = self.board_cu
        self.m.ACCOUNTS = self.accounts_cu
        self.m.AUTO.clear()
        reset_legacy_state(self.m)

    def test_auto_video_blocks_both_running_and_queued(self):
        """Auto video phải bỏ qua CẢ `queued`, không riêng `running`.

        Chỉ chặn `running` thì shot đang nằm chờ được xếp thêm lượt nữa — và
        với video, lượt thừa là một lần trừ credit cho đúng shot sắp dựng xong.
        """
        shot = {"id": "V-S1-01", "sf": "SF-S1-01", "prompt": "máy lia"}
        scene = {"id": "S1", "sfs": [], "shots": [shot]}
        self.m.BOARD = _ReadyVideoBoard(scene)
        self.m._auto_vid_doc = lambda: True
        st = {"try": {}, "last": {}, "stat": {}}
        with self.m.AUTO_LOCK:
            self.m.AUTO[scene["id"]] = st

        for nhan in ("queued", "running"):
            with self.subTest(nhan=nhan):
                self.m._dat_job(shot["id"], {"state": nhan, "msg": "đang có việc"})

                self.m._auto_scene(scene, st, 1)

                self.assertEqual(self.m.VID_QUEUE.qsize(), 0)
                self.assertNotIn(shot["id"], st["try"])

    def test_auto_image_checks_running_and_queued(self):
        source = function_source(BOARD, "_auto_scene")
        self.assertIn('not in ("running", "queued")', source)

    def test_auto_producer_observes_same_stop_barrier_as_retry_timer(self):
        """Snapshot auto cũ không được enqueue sau khi `/api/dung-het` trả về.

        Board giả chỉ chặn I/O đọc asset; phần quyết định task, ghi `JOBS` và
        `_xep` đều là production thật. Đây là đúng khe race: `_auto_runner` đã
        lấy được `st`, user dừng tất cả, rồi snapshot cũ mới chạy tiếp.
        """
        scene = {
            "id": "REF",
            "sfs": [{"id": "REF_LORETTA_PORTRAIT", "refs": {}}],
            "shots": [],
        }
        board = _BlockingBoard({"scenes": [scene]})
        self.m.BOARD = board
        st = {"try": {}, "last": {}, "stat": {}}
        with self.m.AUTO_LOCK:
            self.m.AUTO[scene["id"]] = st

        loi = []

        def chay_snapshot_cu():
            try:
                self.m._auto_scene(scene, st, 1)
            except BaseException as exc:  # chuyển lỗi trong thread về thread test
                loi.append(exc)

        th = threading.Thread(target=chay_snapshot_cu, daemon=True)
        th.start()
        try:
            self.assertTrue(board.da_vao.wait(2), "vòng auto không tới điểm chặn")
            handler = make_handler(self.m, "/api/dung-het?dong_chrome=0")
            handler.do_POST()
            self.assertEqual(handler.captured[0], 200)
        finally:
            board.tiep_tuc.set()
            th.join(2)

        self.assertFalse(th.is_alive(), "vòng auto không kết thúc")
        if loi:
            raise loi[0]
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0,
                         "snapshot auto cũ đã xếp việc mới sau Dừng tất cả")
        self.assertNotIn(
            (self.m.JOBS.get("REF_LORETTA_PORTRAIT") or {}).get("state"),
            ("queued", "running"),
        )

    def test_dung_het_doi_auto_commit_xong_roi_vet_task_vua_commit(self):
        """Stop và auto commit phải dùng chung lock, không được lách qua nhau.

        Nếu auto đã thắng barrier và đang ở giữa critical section, stop phải
        đợi nó enqueue xong rồi mới vét. Không dùng chung lock thì stop vét hàng
        rỗng và trả 200 trước; auto sau đó mới enqueue — chính là job chạy tiếp.
        """
        scene = {
            "id": "REF",
            "sfs": [{"id": "REF_LORETTA_PORTRAIT", "refs": {}}],
            "shots": [],
        }
        board = _BlockingBoard({"scenes": [scene]})
        board.tiep_tuc.set()
        self.m.BOARD = board
        st = {"try": {}, "last": {}, "stat": {}}
        with self.m.AUTO_LOCK:
            self.m.AUTO[scene["id"]] = st

        lock_cu = self.m.AUTO_LOCK
        allow_cu = self.m._auto_allow
        lock = _ObservedLock()
        vao_commit = threading.Event()
        nha_commit = threading.Event()
        stop_bat_dau = threading.Event()
        stop_xong = threading.Event()
        loi = []

        def allow_chan(st_arg, ident, cyc, ghi=True):
            if ghi and threading.current_thread().name == "auto-commit-test":
                vao_commit.set()
                if not nha_commit.wait(2):
                    raise AssertionError("không được nhả auto commit")
            return allow_cu(st_arg, ident, cyc, ghi)

        self.m.AUTO_LOCK = lock
        self.m._auto_allow = allow_chan

        def chay_auto():
            try:
                self.m._auto_scene(scene, st, 1)
            except BaseException as exc:
                loi.append(exc)

        def chay_stop():
            try:
                stop_bat_dau.set()
                handler = make_handler(self.m, "/api/dung-het?dong_chrome=0")
                handler.do_POST()
                if handler.captured is None or handler.captured[0] != 200:
                    raise AssertionError(f"stop trả kết quả lạ: {handler.captured!r}")
            except BaseException as exc:
                loi.append(exc)
            finally:
                stop_xong.set()

        auto = threading.Thread(target=chay_auto, name="auto-commit-test", daemon=True)
        stop = threading.Thread(target=chay_stop, name="stop-all-test", daemon=True)
        auto.start()
        try:
            self.assertTrue(vao_commit.wait(2), "auto không vào critical section commit")
            stop.start()
            self.assertTrue(stop_bat_dau.wait(2), "thread stop không bắt đầu")
            self.assertTrue(lock.stop_dang_cho.wait(2),
                            "Dừng tất cả không acquire cùng AUTO_LOCK với auto commit")
            self.assertFalse(stop_xong.is_set(),
                             "Dừng tất cả trả về khi auto vẫn đang commit")
        finally:
            nha_commit.set()
            auto.join(2)
            if stop.ident is not None:
                stop.join(2)
            self.m._auto_allow = allow_cu
            self.m.AUTO_LOCK = lock_cu

        self.assertFalse(auto.is_alive())
        self.assertFalse(stop.is_alive())
        if loi:
            raise loi[0]
        self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)
        self.assertEqual(self.m.JOBS["REF_LORETTA_PORTRAIT"]["msg"], "đã dừng")

    def test_multi_copy_enqueue_uses_distinct_job_identity_per_copy(self):
        """Ba bản song song là BA job khác nhau, không phải một ident xếp ba lần.

        Cùng một ident cho ba bản thì kết quả bản này ghi đè trạng thái bản kia,
        và mọi cú vét hàng chỉ nhìn thấy một việc.
        """
        from helpers import FakeBoard

        self.m.BOARD = FakeBoard()
        self.m._init_job_shadow("shadow")
        try:
            h = make_handler(self.m, "/api/generate?sf=SF-S1-01&n=3")
            h.headers["Idempotency-Key"] = "multi-copy"
            h.do_POST()
            code, body = h.captured

            self.assertEqual(code, 200)
            self.assertEqual(len(set(body["job_ids"])), 3)
            self.assertIsNotNone(body["batch_id"])
            self.assertEqual(self.m.IMG_QUEUE.qsize(), 3)

            h2 = make_handler(self.m, "/api/generate?sf=SF-S1-01&n=3")
            h2.headers["Idempotency-Key"] = "multi-copy"
            h2.do_POST()

            self.assertEqual(h2.captured[1]["job_ids"], body["job_ids"])
            self.assertEqual(self.m.IMG_QUEUE.qsize(), 3)
        finally:
            self.m._init_job_shadow("legacy")

    def test_auto_video_failed_intent_is_not_revived_by_next_scan(self):
        """Auto là NGƯỜI TẠO, không phải người thử lại.

        Shot đã hỏng mà vòng quét sau lại xếp tiếp thì auto tự cầm quyền retry —
        đúng thứ Phase 9 mới được giao cho RetryPolicy. Job cũ phải giữ nguyên
        định danh, không có job mới nào mọc ra.
        """
        shot = {"id": "V-S1-01", "sf": "SF-S1-01", "prompt": "máy lia"}
        scene = {"id": "S1", "sfs": [], "shots": [shot]}
        st = {"try": {}, "last": {}, "stat": {}}
        self.m.BOARD = _ReadyVideoBoard(scene)
        self.m._auto_vid_doc = lambda: True
        self.m._init_job_shadow("shadow")
        try:
            with self.m.AUTO_LOCK:
                self.m.AUTO[scene["id"]] = st
            self.m._auto_scene(scene, st, 1)
            job_dau = self.m._JOB_SHADOW.job_for(shot["id"])

            self.m._dat_job(shot["id"], {"state": "error", "msg": "provider hỏng"})
            while not self.m.VID_QUEUE.empty():
                self.m.VID_QUEUE.get_nowait()
                self.m.VID_QUEUE.task_done()

            self.m._auto_scene(scene, st, 20)

            self.assertEqual(self.m.VID_QUEUE.qsize(), 0)
            self.assertEqual(
                self.m._JOB_SHADOW.job_for(shot["id"]).job_id, job_dau.job_id
            )
        finally:
            self.m._init_job_shadow("legacy")

    def test_auto_image_failed_intent_is_not_revived_by_next_scan(self):
        scene = {"id": "S1", "sfs": [{"id": "SF-S1-01", "refs": {}}], "shots": []}
        st = {"try": {}, "last": {}, "stat": {}}
        self.m.BOARD = _ReadyVideoBoard(scene, co_anh=False)
        self.m._init_job_shadow("shadow")
        try:
            with self.m.AUTO_LOCK:
                self.m.AUTO[scene["id"]] = st
            self.m._auto_scene(scene, st, 1)
            job_dau = self.m._JOB_SHADOW.job_for("SF-S1-01")

            self.m._dat_job("SF-S1-01", {"state": "error", "msg": "lô hỏng"})
            while not self.m.IMG_QUEUE.empty():
                self.m.IMG_QUEUE.get_nowait()
                self.m.IMG_QUEUE.task_done()

            self.m._auto_scene(scene, st, 20)

            self.assertEqual(self.m.IMG_QUEUE.qsize(), 0)
            self.assertEqual(
                self.m._JOB_SHADOW.job_for("SF-S1-01").job_id, job_dau.job_id
            )
        finally:
            self.m._init_job_shadow("legacy")
