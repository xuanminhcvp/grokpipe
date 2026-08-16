# -*- coding: utf-8 -*-
"""Chạy hàng loạt ảnh SF qua board — dùng khi cần render cả một phim.

    python3 sfboard/chay-anh.py <PROJECT> [--port 8779] [--bo S4,S6,S7,S8]

LUẬT: một SF con chỉ được xếp hàng khi ẢNH NEO CỦA CHÍNH NÓ đã có file — chặn theo
đúng thứ nó phụ thuộc, KHÔNG chặn cả tầng, để 4 tài khoản không ngồi không chờ một
ảnh neo chẳng liên quan. Lỗi thì thử lại tới khi xong.

KHÔNG đụng tới video: script này chỉ gọi /api/generate cho ảnh.
"""
import json, time, os, sys, argparse, urllib.request, uuid

API = 'http://localhost:8779'
TREO = 600
PROJ = ''
BO: set = set()


def doi_so(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--port', type=int, default=8779)
    ap.add_argument('--bo', default='S4,S6,S7,S8', help='scene bỏ qua, cách nhau bằng dấu phẩy')
    ap.add_argument('--song-song', type=int, default=4, help='số job chạy cùng lúc = số Chrome')
    ap.add_argument('--toi-da-thu', type=int, default=25)
    ap.add_argument('--treo', type=int, default=600, help='giây: job running lâu hơn mức này coi như chết')
    ap.add_argument('--nghi-sau-loi', type=int, default=90, help='giây nghỉ trước khi thử lại một SF')
    return ap.parse_args(argv)


def get(p):
    with urllib.request.urlopen(API + p, timeout=20) as r:
        return json.load(r)


def post(p, idempotency_key):
    """POST kèm KHOÁ Ý ĐỊNH.

    Không có khoá thì mỗi lần script gửi lại (mạng chớp, board bận) là một ý
    định mới với server — nó xếp thêm một lượt render cho đúng SF đang chờ.
    Cùng khoá thì server trả về job cũ và không xếp thêm."""
    request = urllib.request.Request(
        API + p, method='POST', headers={'Idempotency-Key': idempotency_key})
    with urllib.request.urlopen(request, timeout=20) as r:
        return json.load(r)


class RequestKeys:
    """Khoá theo asset, GIỮ NGUYÊN cho tới khi chủ động xoay.

    Giữ nguyên: gửi lại vì lỗi mạng không tạo job thứ hai.
    Xoay: chỉ khi lượt cũ đã kết thúc bằng lỗi và ta CỐ Ý chạy lại — lúc đó
    phải là ý định mới, nếu không server sẽ replay job hỏng cũ."""

    def __init__(self, factory=lambda: uuid.uuid4().hex):
        self._factory = factory
        self._keys = {}

    def for_asset(self, asset_id):
        # KHÔNG dùng `setdefault(id, self._factory())`: Python tính tham số mặc
        # định ở MỌI lần gọi, nên mỗi lần đọc lại sinh thêm một khoá rồi vứt đi.
        if asset_id not in self._keys:
            self._keys[asset_id] = self._factory()
        return self._keys[asset_id]

    def rotate(self, asset_id):
        self._keys[asset_id] = self._factory()
        return self._keys[asset_id]


def co_anh(sf):
    return any(os.path.exists(os.path.join(PROJ, 'assets', sf + e))
               for e in ('.png', '.jpg', '.jpeg', '.webp'))


def log(*x):
    print(time.strftime('%H:%M:%S'), *x, flush=True)


def main(argv=None):
    global API, TREO, PROJ, BO
    a = doi_so(argv)
    API = f'http://localhost:{a.port}'
    TREO = a.treo
    PROJ = os.path.abspath(a.project)
    BO = {x.strip() for x in a.bo.split(',') if x.strip()} | {'REF'}
    IDEMPOTENCY = RequestKeys()
    d = json.load(open(os.path.join(PROJ, 'sf-board.json'), encoding='utf-8'))
    BG = {f['id']: (f['refs'].get('bg') or '')
          for sc in d['scenes'] if sc['id'] not in BO
          for f in sc.get('sfs', []) if not f['id'].startswith('SF-M-')}
    # ảnh neo trước, SF con sau — chỉ là thứ tự ưu tiên, không phải rào chắn
    uu_tien = ([i for i, b in BG.items() if b.startswith('SF-M-')] +
               [i for i, b in BG.items() if not b.startswith('SF-M-')])
    con = [i for i in uu_tien if not co_anh(i)]
    thu = {i: 0 for i in con}
    lan_loi, da_dem, bat_dau = {}, set(), {}
    log(f'══ BẮT ĐẦU: {len(con)}/{len(BG)} SF cần chạy')

    while con:
        try:
            jobs = get('/api/jobs')['jobs']
        except Exception as e:
            log(f'   ! board không trả lời: {e}'); time.sleep(15); continue
        # Chrome tự đóng giữa chừng thì job nằm mãi ở 'running' và ăn hết suất chạy —
        # quá TREO giây thì coi như chết, trả suất lại cho SF khác.
        now = time.time()
        dang = []
        for k, v in jobs.items():
            if v.get('state') != 'running':
                bat_dau.pop(k, None); continue
            t0 = bat_dau.setdefault(k, now)
            if now - t0 < TREO:
                dang.append(k)
            elif k in con:
                log(f'   ⏱ {k} treo >{TREO // 60}phút — bỏ đếm, xếp lại')
                bat_dau[k] = now

        for i in [x for x in con if co_anh(x)]:
            con.remove(i); log(f'   ✓ {i}   (còn {len(con)})')

        for i in list(con):
            st = jobs.get(i, {})
            # chỉ đếm MỘT lần cho mỗi lượt chạy — không đếm lại ở mỗi vòng poll
            if st.get('state') == 'error' and i not in dang and i not in da_dem:
                da_dem.add(i); thu[i] += 1
                if thu[i] > a.toi_da_thu:
                    log(f'   ✗ {i} bỏ sau {a.toi_da_thu} lần: {st.get("msg","")[:70]}'); con.remove(i)
                else:
                    lan_loi[i] = time.time()
                    # Lượt cũ đã kết thúc bằng lỗi: lần xếp sau là Ý ĐỊNH MỚI nên
                    # phải có khoá mới — giữ khoá cũ thì server replay job hỏng.
                    IDEMPOTENCY.rotate(i)
                    log(f'   ↻ {i} lỗi lần {thu[i]}: {st.get("msg","")[:65]}')
        if not con:
            break

        rong = a.song_song - len(dang)
        for i in con:
            if rong <= 0:
                break
            if i in dang or jobs.get(i, {}).get('state') == 'queued':
                continue
            if time.time() - lan_loi.get(i, 0) < a.nghi_sau_loi:
                continue
            bg = BG[i]
            if bg and not bg.startswith('SF-M-') and not co_anh(bg):
                continue                       # ảnh neo của chính nó chưa có → chờ
            try:
                ket_qua = post(f'/api/generate?sf={i}&n=1', IDEMPOTENCY.for_asset(i))
                da_dem.discard(i); rong -= 1
                job_id = (ket_qua or {}).get('job_id')
                log(f'   → xếp hàng {i}' + (f' · job {str(job_id)[:8]}' if job_id else ''))
            except Exception as e:
                log(f'   ! không xếp được {i}: {e}')
        time.sleep(15)

    log(f'══ XONG. Thiếu: {[i for i in BG if not co_anh(i)] or "không"}')


if __name__ == '__main__':
    main()
