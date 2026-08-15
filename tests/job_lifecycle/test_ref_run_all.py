"""Hành vi xuyên suốt của nút “Chạy hết” RIÊNG trong scene REF.

Không gọi Chrome/provider. Chỉ thay tầng lưu file ảnh bằng bộ nhớ; endpoint,
AUTO, cách tìm phụ thuộc, chia lô, ghi JOBS và PriorityQueue đều là production.
"""

from helpers import load_sfboard, make_handler, reset_legacy_state


class _RefBoard:
    def __init__(self, scene):
        self.path = __file__
        self.data = {"scenes": [scene]}
        self.files = set()

    def read(self):
        return self.data

    def find_file(self, asset_id):
        return f"/{asset_id}.png" if asset_id in self.files else None

    def video_file(self, _shot_id):
        return None


class TestRefRunAll:
    def setup_method(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.m.AUTO.clear()
        self.board_cu = self.m.BOARD
        self.scene = {
            "id": "REF",
            "sfs": [
                {"id": "REF_AN_PORTRAIT", "prompt": "portrait An", "refs": {}},
                {"id": "REF_AN_HOME_FULL", "prompt": "An ở nhà",
                 "refs": {"chars": ["REF_AN_PORTRAIT"]}},
                {"id": "REF_BINH_PORTRAIT", "prompt": "portrait Bình", "refs": {}},
                {"id": "REF_BINH_WORK_FULL", "prompt": "Bình công sở",
                 "refs": {"chars": ["REF_BINH_PORTRAIT"]}},
                {"id": "REF_PROP_PHONE", "prompt": "điện thoại", "refs": {}},
            ],
            "shots": [],
        }
        self.board = _RefBoard(self.scene)
        self.m.BOARD = self.board

    def teardown_method(self):
        self.m.BOARD = self.board_cu
        self.m.AUTO.clear()
        reset_legacy_state(self.m)

    def _post(self, path):
        handler = make_handler(self.m, path)
        handler.do_POST()
        return handler.captured

    def _lay_het_hang_anh(self):
        items = []
        while self.m.IMG_QUEUE.qsize():
            item = self.m._lay(self.m.IMG_QUEUE, block=False)
            self.m.IMG_QUEUE.task_done()
            items.append(item)
        return items

    def test_portrait_doc_lap_duoc_gom_chung_mot_lo(self):
        self._post("/api/auto?op=toggle&scene=REF")

        self.m._auto_scene(self.scene, self.m.AUTO["REF"], 1)
        idents = [item[1] for item in self._lay_het_hang_anh()]

        assert "LO:REF_AN_PORTRAIT,REF_BINH_PORTRAIT" in idents
        assert "LO:REF_PROP_PHONE" in idents
        assert all("_FULL" not in ident for ident in idents)

    def test_full_bon_nhan_vat_chinh_tach_rieng_tu_nguoi_thu_nam_gom_chung(self):
        sfs = []
        for ten in ("A", "B", "C", "D", "E", "F"):
            portrait = f"REF_{ten}_PORTRAIT"
            sfs.extend([
                {"id": portrait, "prompt": f"portrait {ten}", "refs": {}},
                {"id": f"REF_{ten}_FULL", "prompt": f"full {ten}",
                 "refs": {"chars": [portrait]}},
            ])
        self.scene["sfs"] = sfs
        self.board.files.update(f"REF_{ten}_PORTRAIT" for ten in "ABCDEF")
        self._post("/api/auto?op=toggle&scene=REF")

        self.m._auto_scene(self.scene, self.m.AUTO["REF"], 1)
        idents = [item[1] for item in self._lay_het_hang_anh()]

        for ten in "ABCD":
            assert f"LO:REF_{ten}_FULL" in idents
        assert "LO:REF_E_FULL,REF_F_FULL" in idents

    def test_nut_chay_het_REF_tao_du_moi_REF_dung_thu_tu_phu_thuoc(self):
        code, body = self._post("/api/auto?op=toggle&scene=REF")

        assert code == 200
        assert body["on"] is True
        assert set(body["auto"]) == {"REF"}, "không được bật Chạy hết cho scene thường"

        da_tao = []
        vong_cua = {}
        for cyc in range(1, 5):
            miss_img, total_img, miss_vid, total_vid = self.m._auto_scene(
                self.scene, self.m.AUTO["REF"], cyc
            )
            assert (total_img, miss_vid, total_vid) == (5, 0, 0)

            items = self._lay_het_hang_anh()
            for item in items:
                ident = item[1]
                ids = ident[3:].split(",") if ident.startswith("LO:") else [ident]
                self.m._dat_job(ident, {"state": "done", "msg": "xong"})
                for asset_id in ids:
                    assert asset_id not in da_tao, f"REF bị enqueue trùng: {asset_id}"
                    da_tao.append(asset_id)
                    vong_cua[asset_id] = cyc
                    self.board.files.add(asset_id)

            if miss_img == 0:
                assert not items
                break

        assert set(da_tao) == {
            "REF_AN_PORTRAIT",
            "REF_AN_HOME_FULL",
            "REF_BINH_PORTRAIT",
            "REF_BINH_WORK_FULL",
            "REF_PROP_PHONE",
        }
        assert vong_cua["REF_AN_PORTRAIT"] < vong_cua["REF_AN_HOME_FULL"]
        assert vong_cua["REF_BINH_PORTRAIT"] < vong_cua["REF_BINH_WORK_FULL"]
        assert self.m.IMG_QUEUE.qsize() == 0
