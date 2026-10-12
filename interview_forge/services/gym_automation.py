# -*- coding: utf-8 -*-
"""南大健身房自动预约执行器（工具箱·健身房预约工具的浏览器自动化核心）。

由 gym.py 调度器以子进程运行，也可手动执行：
  python -m interview_forge.services.gym_automation --venue 129 --date 2026-10-12
      --slots "17:00-18:00,16:00-17:00" --json-result data/logs/gym/result.json

输出约定：--json-result 指向的文件写入
  {"status": "succeeded|no_slot|failed|ambiguous", "detail": str, ...}
退出码：0 succeeded（含当日已有有效预约）/ 2 no_slot / 3 ambiguous / 1 failed。

技术栈：Playwright(Chromium) + ddddocr(点选验证码检测/双版分类) + PaddleOCR(可选行级识别)
        + DeepSeek(约束多选认字，凭据见 deepseek_key()) + numpy(Canny 缺口匹配)。
安全边界：金额非 0 停止；结果不明先查订单；日志不含密码/Cookie。
"""
import argparse
import base64
import json
import logging
import os
import re
import sys
import time
from datetime import date as date_cls, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")

PREFERRED_SLOTS = ["17:00-18:00", "16:00-17:00"]
BOOKING_RELEASE_HOUR = 8
BOOKING_RELEASE_MINUTE = 0
BOOKING_RELEASE_SECOND = 20
ORDERS_URL = "https://ggtypt.nju.edu.cn/venue/orders"
VENUE_URL_FMT = "https://ggtypt.nju.edu.cn/venue/venue-reservation/{venue}"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ---------------------------------------------------------------- paths / config

def credentials_file():
    """凭据查找顺序：环境变量 > data/gym-credentials.txt > 桌面体育馆项目(本机兼容)。
    仅手动执行（未传 --credentials-stdin）时使用。"""
    env = os.environ.get("GYM_CREDENTIALS_FILE", "").strip()
    if env:
        return Path(env)
    local = ROOT / "data" / "gym-credentials.txt"
    if local.exists():
        return local
    legacy = Path(r"C:\Users\20303\Desktop\研一1\体育场馆预约\账号密码.txt")
    if legacy.exists():
        return legacy
    return local  # 默认路径，read_credentials 时报错提示


def read_stdin_credentials() -> tuple[str, str]:
    """调度器经 stdin 传入的 JSON 凭据（不落命令行/日志）。"""
    raw = sys.stdin.read()
    payload = json.loads(raw or "{}")
    account = str(payload.get("account") or "").strip()
    password = str(payload.get("password") or "")
    if not account or not password:
        raise RuntimeError("stdin 凭据缺失 account/password")
    return account, password


def setup_logging():
    log_dir = ROOT / "data" / "logs" / "gym"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    fh = logging.FileHandler(log_dir / f"booking-{stamp}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    log.setLevel(logging.INFO)
    return log_dir


def read_credentials():
    path = credentials_file()
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"无法读取凭据文件 {path}：{exc}") from exc
    m_user = re.search(r"账号[：:]\s*(\S+)", txt)
    m_pass = re.search(r"密码[：:]\s*(\S+)", txt)
    if not m_user or not m_pass:
        raise RuntimeError(f"凭据文件 {path} 中未找到 账号：/密码： 字段")
    return m_user.group(1), m_pass.group(1)


log = logging.getLogger("gym.booking")

# ---------------------------------------------------------------- utilities

def base64_png(data_uri):
    return base64.b64decode(data_uri.split(",", 1)[1])


def safe_body_text(page, limit=400):
    """页面可能正在跳转，读取失败按空串处理。"""
    try:
        return page.evaluate(f"() => document.body.innerText.slice(0, {limit})")
    except Exception:  # noqa: BLE001
        return ""


def is_site_ready(page):
    """就绪=不在 CAS、不在 oauth 换票中、页面有内容且无“请登录后访问”。"""
    url = page.url
    if "authserver" in url or "oauth_token" in url:
        return False
    state = safe_body_text(page)
    if not state:
        return False
    return "请登录后访问" not in state and "统一身份认证登录" not in state


def wait_either(page, css_list, timeout_ms):
    """等待任一 CSS 选择器出现，返回第一个出现的选择器；超时返回 None。"""
    joined = ",".join(css_list)
    try:
        page.wait_for_selector(joined, timeout=timeout_ms, state="visible")
        for css in css_list:
            if page.query_selector(css) is not None:
                return css
        return None
    except Exception:  # noqa: BLE001
        return None


def robust_goto(page, url, attempts=4):
    """站点常有自动跳转在途，主动导航可能被打断：遇到就等一下重试。"""
    for _ in range(attempts):
        try:
            page.goto(url, wait_until="domcontentloaded")
            return
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "interrupted" in msg or "Execution context" in msg:
                time.sleep(2)
                continue
            raise
    raise RuntimeError(f"导航 {url} 连续 {attempts} 次被打断")


def date_label_cn(d: date_cls):
    return f"{d.month}月{d.day}日"


# ---------------------------------------------------------------- slider

JS_CANVAS_DUMP = """() => {
  const bg = document.querySelector('canvas:not(.block)');
  const block = document.querySelector('canvas.block');
  if (!bg || !block) return null;
  const rb = bg.getBoundingClientRect(), rs = block.getBoundingClientRect();
  return {
    bgData: bg.toDataURL('image/png'),
    blockData: block.toDataURL('image/png'),
    attr: [bg.width, bg.height, block.width, block.height],
    css: [rb.width, rb.height, rs.width, rs.height],
  };
}"""


def solve_slider(page, max_attempts=5):
    """SliderCaptcha 拼图滑块：Canny 边缘图上按拼图块轮廓做模板匹配找缺口。

    服务端同时校验位置(容差5px)与拖动轨迹，因此拖动必须拟人：
    总时长 0.7~1.2s、加速-巡航-减速带噪声、轻微过冲回正。
    """
    import cv2
    for attempt in range(1, max_attempts + 1):
        try:
            if page.query_selector(".sliderContainer") is None:
                return True
            dump = page.evaluate(JS_CANVAS_DUMP)
            if not dump:
                log.warning("滑块：未找到 canvas，第 %d 次", attempt)
                time.sleep(1)
                continue
            bg = np.asarray(Image.open(BytesIO(base64_png(dump["bgData"]))).convert("RGB"), dtype=np.float32)
            piece = np.asarray(Image.open(BytesIO(base64_png(dump["blockData"]))).convert("RGBA"), dtype=np.uint8)
            bh, bw = bg.shape[:2]
            mask = piece[:, :, 3] > 128
            ys, xs = np.nonzero(mask)
            if len(xs) == 0:
                log.warning("滑块：拼图块掩码为空，第 %d 次", attempt)
                time.sleep(1)
                continue
            x0, x1 = int(xs.min()), int(xs.max())
            y0, y1 = int(ys.min()), int(ys.max())
            lum = 0.299 * bg[:, :, 0] + 0.587 * bg[:, :, 1] + 0.114 * bg[:, :, 2]
            edges = cv2.dilate(cv2.Canny(lum.astype(np.uint8), 60, 160), np.ones((3, 3), np.uint8))
            eroded = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8))
            contour = mask & (eroded == 0)
            cys, cxs = np.nonzero(contour)
            if len(cxs) == 0:
                cys, cxs = ys, xs
            best = None
            for dy in range(-4, 5):
                if y0 + dy < 0 or y1 + dy >= bh:
                    continue
                for dx in range(5, bw - (x1 - x0) - 5):
                    score = float(edges[cys + dy, cxs + dx].sum()) / len(cxs)
                    if best is None or score > best[0]:
                        best = (score, dx, dy)
            if best is None:
                raise RuntimeError("滑块：边缘匹配无候选")
            _, tx, _ = best
            scale = dump["css"][0] / dump["attr"][0]
            base_delta = round(tx * scale)
            delta = base_delta + [0, 1, -1, 2, -2][(attempt - 1) % 5]
            log.info("滑块：缺口x=%d 基准delta=%d 本轮拖动=%d", tx, base_delta, delta)
            drag_slider(page, delta)
            for _ in range(24):
                time.sleep(0.3)
                if page.url.startswith("https://ggtypt"):
                    log.info("滑块：第 %d 次通过并已跳转", attempt)
                    return True
                hidden = page.evaluate(
                    "() => { const el = document.querySelector('#captcha-id, .sliderContainer');"
                    " if (!el) return true; return getComputedStyle(el).display === 'none'; }")
                if hidden:
                    log.info("滑块：第 %d 次通过，弹窗已隐藏", attempt)
                    return True
            try:
                state = page.evaluate(
                    "() => { const s = document.querySelector('.slider');"
                    " return { sliderLeft: s ? s.style.left : null }; }")
            except Exception:  # noqa: BLE001
                state = None
            if state is None or page.url.startswith("https://ggtypt"):
                for _ in range(20):
                    time.sleep(0.5)
                    if page.url.startswith("https://ggtypt"):
                        log.info("滑块：第 %d 次通过并已跳转", attempt)
                        return True
            log.warning("滑块：第 %d 次未通过（%s）", attempt, json.dumps(state, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            if "Execution context was destroyed" in str(exc) or "navigation" in str(exc):
                for _ in range(20):
                    time.sleep(0.5)
                    if page.url.startswith("https://ggtypt"):
                        log.info("滑块：第 %d 次通过并已跳转", attempt)
                        return True
            log.warning("滑块：第 %d 次异常 %s", attempt, exc)
            time.sleep(1)
    return False


def drag_slider(page, delta):
    """拟人轨迹拖动（加速-巡航-减速+噪声+过冲回正），详见 solve_slider 说明。"""
    import random as _rnd
    box = page.locator(".slider").first.bounding_box()
    if not box:
        raise RuntimeError("找不到滑块手柄")
    sx, sy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(sx, sy)
    page.mouse.down()
    time.sleep(_rnd.uniform(0.06, 0.13))

    n = _rnd.randint(42, 55)
    acc, dec = max(3, int(n * 0.22)), max(3, int(n * 0.28))
    xs, x, v = [], 0.0, 0.0
    for i in range(n):
        if i < acc:
            f = 0.25 + 0.75 * (i / acc)
        elif i < n - dec:
            f = 1.0
        else:
            f = max(0.08, 1.0 - 0.9 * ((i - (n - dec)) / dec))
        v = max(0.9, v + f * _rnd.uniform(2.6, 4.4))
        x += v
        xs.append(x)
    xs = [val * (delta / xs[-1]) for val in xs]

    y = 0.0
    for px in xs:
        y = max(-4.0, min(4.0, y + _rnd.uniform(-0.8, 0.8)))
        page.mouse.move(sx + px, sy + y)
        time.sleep(_rnd.uniform(0.009, 0.024))

    page.mouse.move(sx + delta + _rnd.uniform(1.5, 3.5), sy + y * 0.5)
    time.sleep(_rnd.uniform(0.03, 0.06))
    for k in range(3):
        page.mouse.move(sx + delta + (2.5 * (1 - (k + 1) / 3)), sy + y * 0.3)
        time.sleep(_rnd.uniform(0.03, 0.06))
    page.mouse.move(sx + delta, sy)
    time.sleep(_rnd.uniform(0.05, 0.12))
    page.mouse.up()


# ---------------------------------------------------------------- login

def click_first_visible(page, text, timeout_ms=2500, exact=True):
    """在所有匹配文本的元素里点击第一个可见的。

    这类 Vue 页面常有多份隐藏的弹窗模板（相同文案），get_by_text(...).first
    会按 DOM 顺序绑到隐藏元素上，is_visible() 永远为 False 导致永远点不到；
    必须遍历全部匹配。"""
    locator = page.get_by_text(text, exact=exact)
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            count = locator.count()
        except Exception:  # noqa: BLE001
            count = 0
        for i in range(count):
            node = locator.nth(i)
            try:
                if node.is_visible():
                    node.click()
                    return True
            except Exception:  # noqa: BLE001
                continue
        time.sleep(0.25)
    return False


def settle_after_login(page, target_url, max_wait=45):
    """CAS 回跳后站点要自动走 /venue/login?oauth_token=... 换自身会话，
    期间连续多次自动跳转——任何主动 goto/reload 都会打断它。
    只观察；弹“请登录后访问”点确定；落到登录中转页点“统一登录”。"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if is_site_ready(page):
            return
        state = safe_body_text(page)
        try:
            if "请登录后访问" in state:
                if click_first_visible(page, "确定", timeout_ms=600):
                    log.info("点击“请登录后访问”确定，等待站点自行跳转")
                    time.sleep(1.2)
                    continue
            for txt in ("统一登录", "统一身份认证登录"):
                if click_first_visible(page, txt, timeout_ms=400):
                    log.info("点击“%s”，等待 CAS 与 oauth 自动换票", txt)
                    time.sleep(1.5)
                    break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.2)
    raise RuntimeError("登录后站点始终未就绪")


def login(page, user, pwd, target_url):
    robust_goto(page, target_url)
    if "authserver" not in page.url:
        log.info("已有登录态，直接进入场馆页")
        return
    log.info("跳转到统一身份认证，开始登录")
    page.fill("#username", user)
    page.fill("#password", pwd)
    page.locator("#login_submit:visible").click()
    if wait_either(page, [".sliderContainer"], 6000) == ".sliderContainer":
        log.info("出现滑块验证，自动拖动")
        if not solve_slider(page):
            raise RuntimeError("滑块验证未通过")
    page.wait_for_url("https://ggtypt.nju.edu.cn/**", timeout=15000)
    settle_after_login(page, target_url)
    log.info("登录完成")


def check_login(page, user, pwd, target_url):
    """只验证凭据能否登录（含滑块），不进入预约流程。返回 {status, detail}。

    status: ok / bad_credentials / captcha_failed / error"""
    robust_goto(page, target_url)
    if "authserver" not in page.url:
        return {"status": "ok", "detail": "已有登录态"}
    log.info("登录验证：填写凭据并提交")
    page.fill("#username", user)
    page.fill("#password", pwd)
    page.locator("#login_submit:visible").click()
    if wait_either(page, [".sliderContainer"], 8000) == ".sliderContainer":
        log.info("出现滑块验证，自动拖动")
        if not solve_slider(page):
            return {"status": "captcha_failed", "detail": "滑块验证未通过（可重试）"}
    try:
        page.wait_for_url("https://ggtypt.nju.edu.cn/**", timeout=20000)
    except Exception:  # noqa: BLE001
        body = safe_body_text(page, 300)
        if re.search(r"有误|不正确|不存在|锁定", body):
            return {"status": "bad_credentials", "detail": "账号或密码不正确"}
        return {"status": "error", "detail": f"登录后未跳转：{body[:120]}"}
    settle_after_login(page, target_url)
    return {"status": "ok", "detail": "登录验证通过"}


# ---------------------------------------------------------------- orders

def _summarize_order_rows(rows, target_date):
    """按目标日期汇总有效预约与未支付订单，保留原始行以便解释结果。"""
    today_marks = [target_date.isoformat(), date_label_cn(target_date),
                   f"{target_date.month:02d}-{target_date.day:02d}"]
    summary = {"booked": [], "pending": [], "relevant": []}
    for raw_row in rows:
        row = re.sub(r"\s+", " ", str(raw_row)).strip()
        if "健身房" not in row or not any(mark in row for mark in today_marks):
            continue
        summary["relevant"].append(row)
        if "已支付" in row and "正常" in row:
            summary["booked"].append(row)
        elif ("未支付" in row or "待支付" in row or "待付款" in row) and "已取消" not in row:
            summary["pending"].append(row)
    return summary


def _normalize_order_text(value):
    return re.sub(r"\s+", "", str(value)).replace("—", "-").replace("–", "-")


def _row_matches_slot(row, slot):
    return _normalize_order_text(slot) in _normalize_order_text(row)


def _format_existing_bookings(rows):
    labels = []
    for row in rows:
        match = re.search(
            r"((?:[01]\d|2[0-3]):[0-5]\d)\s*[-—–]\s*((?:[01]\d|2[0-3]):[0-5]\d)",
            str(row),
        )
        label = f"{match.group(1)}-{match.group(2)}" if match else "时段未识别"
        if label not in labels:
            labels.append(label)
    return "、".join(labels)


def _existing_booking_failure(rows):
    """目标日已有任一有效预约时立即停止，避免继续轮询或尝试其他时段。"""
    labels = _format_existing_bookings(rows).split("、")
    return {
        "status": "failed",
        "existing_bookings": labels,
        "detail": (f"当天已存在有效预约（{'、'.join(labels)}），"
                   "本次任务已停止，未尝试其他时段。"),
    }


def _booking_release_delay_seconds(now=None):
    """返回距离今天 08:00:20 的等待秒数；放号后为 0。"""
    now = now or datetime.now(SHANGHAI)
    release = now.replace(hour=BOOKING_RELEASE_HOUR,
                          minute=BOOKING_RELEASE_MINUTE,
                          second=BOOKING_RELEASE_SECOND,
                          microsecond=0)
    return max(0.0, (release - now).total_seconds())


def _daily_limit_message(text):
    markers = ("一天只能", "当天只能预约", "当日只能预约", "每天只能", "每日只能",
               "已预约过", "已有预约", "已存在预约", "不能重复预约", "预约次数已达",
               "每人限约一次", "每人每天限", "每人每日限", "单日仅限",
               "预约次数达到上限")
    compact = re.sub(r"\s+", "", text or "")
    return next((marker for marker in markers if marker in compact), None)


def check_existing_orders(page, target_date):
    """返回目标日期订单汇总；有效预约保留时段信息，不再笼统阻断当天其它时段。"""
    robust_goto(page, ORDERS_URL)
    time.sleep(1.5)
    if not is_site_ready(page):
        settle_after_login(page, VENUE_URL_FMT.format(venue="129"))
        robust_goto(page, ORDERS_URL)
        time.sleep(1.5)
    rows = page.evaluate("""() => {
      const trs = [...document.querySelectorAll('table tbody tr, .order-list li, .order-item')];
      return trs.map(tr => tr.innerText.replace(/\\s+/g, ' ').trim()).filter(t => t.length > 0);
    }""")
    log.info("订单页读取到 %d 条记录", len(rows))
    summary = _summarize_order_rows(rows, target_date)
    for row in summary["relevant"]:
        log.info("当天健身房订单记录：%s", row[:120])
    return summary


def _result_without_confirmation(page, target_date, slot, known_bookings=None):
    """未到确认页时复核站点提示与订单，避免把日限额误报成验证码失败。"""
    try:
        body = safe_body_text(page, 1200)
    except Exception:  # noqa: BLE001
        body = ""
    rejection = _daily_limit_message(body)
    orders_checked = True
    try:
        snapshot = check_existing_orders(page, target_date)
    except Exception as exc:  # noqa: BLE001
        log.warning("未确认订单复核失败：%s", exc)
        orders_checked = False
        snapshot = {"booked": [], "pending": [], "relevant": []}
    booked = snapshot.get("booked") or list(known_bookings or [])
    pending = snapshot.get("pending") or []

    matching = [row for row in snapshot.get("booked", []) if _row_matches_slot(row, slot)]
    if matching:
        return {
            "status": "succeeded",
            "detail": f"预约成功：订单页已核验所选时段为有效预约：{_format_existing_bookings(matching)}",
        }
    if rejection:
        detail = f"预约未成功：站点提示“{rejection}”。"
        if booked:
            detail += f"当天已有有效预约：{_format_existing_bookings(booked)}"
        return {"status": "failed", "detail": detail, "retryable": False}
    if pending:
        return {
            "status": "ambiguous",
            "detail": f"未能确认本次预约；订单页发现待支付订单：{_format_existing_bookings(pending)}，请先人工核实。",
            "retryable": False,
        }
    if booked:
        return {
            "status": "failed",
            "detail": f"站点未确认本次预约；当天已有其它有效预约：{_format_existing_bookings(booked)}。",
            "retryable": False,
        }
    if not orders_checked:
        return {
            "status": "ambiguous",
            "detail": "预约结果未确认，且订单页暂时无法核验；为避免重复下单，暂停自动重试，请稍后检查订单。",
            "retryable": False,
        }
    return {
        "status": "failed",
        "detail": "订单确认页未打开，订单页也未发现本次预约；可在稍后自动重试。",
        "retryable": True,
    }


# ---------------------------------------------------------------- venue page

def ensure_target_date(page, target_date):
    label = date_label_cn(target_date)
    # 场次表格与日期条均为 Vue 异步渲染；超时先重载一次再放弃（网络/首屏抖动兜底）
    for attempt in range(2):
        try:
            page.wait_for_selector(".reserveBlock", timeout=15000)
            page.wait_for_selector(".select_date_box .date_box .active", timeout=10000)
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 1:
                try:
                    body = page.evaluate("() => document.body.innerText.slice(0, 300)")
                    log.warning("场次页仍未渲染，页面文本片段：%s", body.replace("\n", " | "))
                    shot_dir = ROOT / "data" / "logs" / "gym" / "captures"
                    shot_dir.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(shot_dir / "venue-page-stuck.png"))
                except Exception:  # noqa: BLE001
                    pass
                raise RuntimeError("场次页未渲染出时段表格/日期条（已重载重试一次）") from exc
            log.warning("场次页首屏未就绪（%s），重载页面重试", exc)
            robust_goto(page, page.url)
            time.sleep(1)
    active = page.evaluate("""() => {
      const act = document.querySelector('.select_date_box .date_box .active');
      return act ? act.innerText.replace(/\\s+/g, '') : '';
    }""")
    if label not in active:
        raise RuntimeError(f"页面选中日期 {active or '未知'} 与目标 {label} 不符（站点只支持约当天）")


def confirm_if_popped(page, texts=("确定",), timeout_ms=2500):
    """点击后可能弹二次确认框，也可能不弹：短超时等待，出现才点。
    用 click_first_visible 遍历全部匹配（页面有隐藏弹窗模板，.first 会绑到隐藏元素）。"""
    for t in texts:
        if click_first_visible(page, t, timeout_ms=timeout_ms):
            log.info("出现二次确认弹窗（%s），已点击", t)
            return True
    return False


def pick_slot(page, slots):
    """按表头定位目标列，兼容 iview 固定列的拆分表（/129 表头与容量块分属不同
    <table>，必须全文档找表头行、按时段块所在列号对齐）。返回 (时段, 容量) 或 None。"""
    dump = page.evaluate("""() => {
      const timeRe = /^\d{2}:\d{2}-\d{2}:\d{2}$/;
      let headers = null;
      for (const row of document.querySelectorAll('tr')) {
        const cells = [...(row.cells || [])].map(c => (c.innerText || '').trim());
        if (cells.some(h => timeRe.test(h))) { headers = cells; break; }
      }
      const blocks = [...document.querySelectorAll('.reserveBlock')].map((b, i) => {
        const td = b.closest('td');
        return { i, header: td && headers ? (headers[td.cellIndex] || '') : '',
                 cls: b.className, text: (b.innerText || '').trim() };
      });
      return { headers, blocks };
    }""")
    headers = (dump or {}).get("headers")
    blocks = (dump or {}).get("blocks") or []
    log.info("表格解析：时间表头%s，时段块 %d 个", "已找到" if headers else "未找到", len(blocks))
    for slot in slots:
        for b in blocks:
            if b["header"] != slot:
                continue
            log.info("时段 %s 状态 class=%s 容量=%s", slot, b["cls"], b["text"])
            cls = b["cls"]
            if "selected" in cls:
                return slot, b["text"]
            if "disabled" in cls or "reserved" in cls:
                break  # 该时段不可选，试下一个备选
            if "free" in cls:
                page.locator(".reserveBlock").nth(b["i"]).click()
                confirm_if_popped(page)
                time.sleep(0.8)
                sel = page.evaluate("""() => {
                  const b = document.querySelector('.reserveBlock.selected');
                  return b ? b.innerText.trim() : null;
                }""")
                if not sel:
                    raise RuntimeError(f"点击 {slot} 后未进入选中状态")
                log.info("已选中时段 %s（%s）", slot, sel)
                return slot, sel
    return None


_ORDER_AMOUNT_RE = re.compile(
    r"(?:订单\s*金额|应付\s*金额|实付\s*金额|支付\s*金额|请您支付(?:金额)?|请支付(?:金额)?|金额|需支付|待支付)"
    r"\s*[：:]?\s*(?:人民币\s*)?[¥￥]?\s*"
    r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:元|人民币)?"
)


def parse_order_amount(text):
    """只从明确的金额标签读取金额；多个标签给出冲突值时拒绝猜测。"""
    values = _order_amount_values(text)
    if not values or any(value != values[0] for value in values[1:]):
        return None
    return values[0]


def _order_amount_values(text):
    return [float(match.replace(",", "")) for match in _ORDER_AMOUNT_RE.findall(text or "")]


def read_amount(page):
    return parse_order_amount(page.evaluate("() => document.body.innerText"))


# ---------------------------------------------------------------- click captcha

JS_CAPTCHA_DUMP = """() => {
  const modalText = document.body.innerText;
  const m = modalText.match(/请依次点击【(.+?)】/);
  const imgs = [...document.querySelectorAll('img[src^="data:image"]')]
    .map(img => ({ img, r: img.getBoundingClientRect() }))
    .filter(o => o.r.width > 100 && o.r.height > 50);
  const img = document.querySelector('.verifybox img') || (imgs[0] && imgs[0].img);
  if (!img) return null;
  const r = img.getBoundingClientRect();
  return {
    prompt: m ? m[1] : null,
    src: img.src,
    rect: [r.x, r.y, r.width, r.height],
    natural: [img.naturalWidth, img.naturalHeight],
  };
}"""


def deepseek_key():
    """验证码识字用的 DeepSeek key 查找顺序：
    1. 环境变量 DEEPSEEK_API_KEY（显式覆盖）；
    2. 站点 AI 配置库（管理后台「AI 配置」里配置的 DeepSeek 供应商，密钥加密存
       ai_config.db，主密钥 INTERVIEW_FORGE_AI_CONFIG_KEY）——部署机首选，
       前端即可换 key；
    3. data/gym-deepseek-key.txt（本工具独立 key 文件）；
    4. 本机开发机遗留路径。
    """
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    try:
        from interview_forge.ai.config_store import AIConfigStore

        store = AIConfigStore()
        for rec in store.list_providers():
            if not rec.enabled or not rec.key_configured:
                continue
            managed_deepseek = (
                rec.capability_profile == "deepseek_official"
                or "deepseek" in (rec.base_url or "").lower()
                or "deepseek" in (rec.name or "").lower()
            )
            if not managed_deepseek:
                continue
            secret = (store.provider_secret(rec.id) or "").strip()
            if secret:
                return secret
    except Exception:  # noqa: BLE001  AI 配置库未配置主密钥/不可用时静默跳过
        pass
    for p in (ROOT / "data" / "gym-deepseek-key.txt",
              Path("E:/interview-forge/.maintenance/deepseek-api-key.txt")):
        try:
            if p.exists():
                t = p.read_text(encoding="utf-8").strip()
                if t.startswith("sk-"):
                    return t
        except Exception:  # noqa: BLE001
            pass
    return None


def deepseek_choice(png_bytes, candidates, key):
    """约束式认字：让模型在候选字（含“都不是”）里选，只回答字母。"""
    import requests
    b64 = base64.b64encode(png_bytes).decode()
    opts = " ".join(f"{chr(65 + i)}.{c}" for i, c in enumerate(candidates))
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text":
                    f"图中是一个彩色、可能旋转、变形的艺术字汉字，背景杂乱。"
                    f"它最可能是下列哪个字：{opts}。若都不是或无法判断，回答 Z。只回答一个字母。"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}],
            "max_tokens": 1500,
            "temperature": 0,
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    m = re.search(r"[A-Za-z]", text)
    if m:
        idx = ord(m.group(0).upper()) - 65
        if 0 <= idx < len(candidates):
            return candidates[idx]
    return ""


_PADDLE_OCR = None


def _get_paddle():
    global _PADDLE_OCR
    if _PADDLE_OCR is None:
        try:
            from paddleocr import PaddleOCR
            _PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("PaddleOCR 初始化失败，跳过该路识别：%s", exc)
            _PADDLE_OCR = False
    return _PADDLE_OCR or None


def _paddle_read(pil_img):
    """PaddleOCR 行级识别（可选路）：返回 [(text, 行框bbox)]。"""
    ocr = _get_paddle()
    if not ocr:
        return []
    try:
        res = ocr.ocr(np.asarray(pil_img), cls=True)
        out = []
        for line in (res[0] or []):
            poly, (text, _score) = line[0], line[1]
            xs = [pt[0] for pt in poly]
            ys = [pt[1] for pt in poly]
            out.append((text, (min(xs), min(ys), max(xs), max(ys))))
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("PaddleOCR 识别异常：%s", exc)
        return []


def assign_targets(entries, targets):
    """四路投票（std/beta 各 2 分精确、1 分包含；ds 2 分；paddle 2 分），
    按得分降序贪心做目标字→框的一对一分配；未得分目标不分配。"""
    def votes_of(t, e):
        v = 0
        for k in ("std", "beta"):
            r = e.get(k) or ""
            if r == t:
                v += 2
            elif t in r:
                v += 1
        if e.get("ds") == t:
            v += 2
        if t in (e.get("paddle_chars") or ""):
            v += 2
        return v

    used = set()
    assignment = {}
    scored = []
    for t in targets:
        best_e, best_v = None, 0
        for e in entries:
            if id(e) in used:
                continue
            v = votes_of(t, e)
            if v > best_v:
                best_e, best_v = e, v
        scored.append((best_v, t, best_e))
    scored.sort(reverse=True, key=lambda x: x[0])
    for v, t, e in scored:
        if e is not None and v > 0:
            assignment[t] = e
            used.add(id(e))
    return assignment


def _confirmation_page(context, page):
    """Return the order-confirmation tab if it has opened in this context."""
    if "tradeNo" in page.url:
        return page
    for candidate in context.pages:
        if candidate is not page and "tradeNo" in candidate.url:
            try:
                candidate.bring_to_front()
            except Exception:  # noqa: BLE001
                pass
            return candidate
    return None


def _wait_for_manual_captcha(page, wait_s=180):
    """Wait for a human-solved challenge and detect confirmation tabs, including popups."""
    log.warning("等待人工完成验证码（%d 秒）", wait_s)
    deadline = time.time() + wait_s
    closed_since = None
    while time.time() < deadline:
        time.sleep(1)
        confirmed = _confirmation_page(page.context, page)
        if confirmed is not None:
            log.info("验证码完成，订单确认页已打开")
            return confirmed
        try:
            challenge_open = page.evaluate(JS_CAPTCHA_DUMP) is not None
        except Exception:  # noqa: BLE001
            challenge_open = False
        if challenge_open:
            closed_since = None
            continue
        # 验证弹窗关闭后站点可能延迟跳确认页；短暂宽限后仍无 tradeNo，
        # 就把它交给订单页复核，不能继续重试验证码/重复提交。
        if closed_since is None:
            closed_since = time.monotonic()
        elif time.monotonic() - closed_since >= 4:
            return _confirmation_page(page.context, page)
    return None


def solve_click_captcha(page, capture_dir, max_attempts=3, manual_only=False):
    """点选验证码：det 出框 + 四路认字投票，贪心分配；缺字刷新换题；失败转人工等待。

    返回承载订单确认页的 page（站点用新标签页打开确认页，必须监控整个
    context），失败返回 None。"""
    if manual_only:
        return _wait_for_manual_captcha(page)

    import ddddocr
    det = ddddocr.DdddOcr(det=True, show_ad=False)
    ocr_std = ddddocr.DdddOcr(show_ad=False)
    ocr_beta = ddddocr.DdddOcr(show_ad=False, beta=True)
    api_key = deepseek_key()
    log.info("验证码识别：ddddocr双版%s，DeepSeek约束多选%s",
             "+PaddleOCR" if _get_paddle() else "（PaddleOCR不可用）",
             "已启用" if api_key else "未配置key")

    for attempt in range(1, max_attempts + 1):
        dump = page.evaluate(JS_CAPTCHA_DUMP)
        if not dump:
            log.info("未检测到点选验证码弹窗，可能已直接通过")
            return page
        if not dump["prompt"]:
            log.warning("未解析到提示文字，转人工")
            break
        targets = [c for c in re.split(r"[,，、\s]+", dump["prompt"]) if c]
        log.info("点选验证码第 %d 次：依次点击 %s", attempt, targets)
        img_bytes = base64_png(dump["src"])
        try:
            (capture_dir / f"captcha-attempt{attempt}.png").write_bytes(img_bytes)
        except OSError:  # noqa: BLE001
            pass
        pil = Image.open(BytesIO(img_bytes)).convert("RGB")
        boxes = [b for b in det.detection(img_bytes)
                 if b[2] - b[0] >= 10 and b[3] - b[1] >= 10]
        log.info("检测到 %d 个字框", len(boxes))

        paddle_lines = _paddle_read(pil)
        entries = []
        for bx in boxes:
            x1, y1, x2, y2 = bx
            crop = pil.crop((x1, y1, x2, y2))
            buf = BytesIO()
            crop.save(buf, format="PNG")
            r_std = ocr_std.classification(buf.getvalue())
            r_beta = ocr_beta.classification(buf.getvalue())
            r_ds = ""
            if api_key:
                up = crop.resize(((x2 - x1) * 4, (y2 - y1) * 4), Image.LANCZOS)
                buf2 = BytesIO()
                up.save(buf2, format="PNG")
                try:
                    r_ds = deepseek_choice(buf2.getvalue(), targets + ["都不是"], api_key)
                except Exception as exc:  # noqa: BLE001
                    log.warning("DeepSeek 多选识别失败 box=%s：%s", list(bx), exc)
            e = {"box": list(bx), "std": r_std, "beta": r_beta, "ds": r_ds,
                 "paddle_chars": "", "center": ((x1 + x2) / 2, (y1 + y2) / 2)}
            cx, cy = e["center"]
            for text, (px1, py1, px2, py2) in paddle_lines:
                han = [c for c in text if "\u4e00" <= c <= "\u9fff"]
                if not han:
                    continue
                for k, ch in enumerate(han):
                    ccx = px1 + (px2 - px1) * (k + 0.5) / len(han)
                    ccy = (py1 + py2) / 2
                    if abs(ccx - cx) <= (px2 - px1) / len(han) and abs(ccy - cy) <= (py2 - py1):
                        e["paddle_chars"] += ch
            entries.append(e)
        log.info("逐框识别：%s", json.dumps(
            [{"box": e["box"], "std": e["std"], "beta": e["beta"],
              "ds": e["ds"], "paddle": e["paddle_chars"]} for e in entries], ensure_ascii=False))

        assignment = assign_targets(entries, targets)
        log.info("目标分配：%s", json.dumps(
            {t: (a["box"] if a else None) for t, a in assignment.items()}, ensure_ascii=False))
        if len(assignment) < len(targets):
            log.warning("第 %d 次有目标字未定位（%s），刷新换题",
                        attempt, [t for t in targets if t not in assignment])
            try:
                refresh = page.locator(
                    ".verify-refresh:visible, .refresh:visible, [class*='refresh']:visible"
                ).first
                if refresh.count() and refresh.is_enabled():
                    refresh.click(timeout=1500)
                    time.sleep(1.5)
                else:
                    raise RuntimeError("验证码刷新控件不可见")
            except Exception as exc:  # noqa: BLE001
                log.warning("无法刷新验证码，转人工处理：%s", exc)
                break
            continue

        rx, ry, rw, rh = dump["rect"]
        nw, nh = dump["natural"]
        for t in targets:
            e = assignment[t]
            cx, cy = e["center"]
            px = rx + cx / nw * rw
            py = ry + cy / nh * rh
            page.mouse.click(px, py)
            log.info("已点击「%s」 @ (%.0f, %.0f)", t, px, py)
            time.sleep(0.55)
        time.sleep(1.0)
        for txt in ("确认", "确定", "验证"):
            if click_first_visible(page, txt, timeout_ms=300):
                log.info("点击验证码弹窗「%s」", txt)
                break
        for _ in range(30):
            time.sleep(0.6)
            if "tradeNo" in page.url:
                log.info("点选验证码通过，已进入订单确认页")
                return page
            # 站点可能用新标签页打开订单确认页
            for pg in page.context.pages:
                if pg is not page and "tradeNo" in pg.url:
                    log.info("点选验证码通过，订单确认页在新标签页")
                    try:
                        pg.bring_to_front()
                    except Exception:  # noqa: BLE001
                        pass
                    return pg
            if page.evaluate(JS_CAPTCHA_DUMP) is None:
                log.info("验证码弹窗已关闭，短暂等待确认页后交由订单状态复核")
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    time.sleep(0.4)
                    confirmed = _confirmation_page(page.context, page)
                    if confirmed is not None:
                        return confirmed
                return None
        log.warning("点选验证码第 %d 次未通过", attempt)
        try:
            refresh = page.locator(".verify-refresh, .refresh, [class*='refresh']:visible").first
            refresh.click(timeout=3000)
            log.info("已点击刷新换一题")
            time.sleep(1.5)
        except Exception:  # noqa: BLE001
            page.keyboard.press("Escape")
            time.sleep(1)
            try:
                click_first_visible(page, "提交", timeout_ms=800)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.5)

    return _wait_for_manual_captcha(page)


# ---------------------------------------------------------------- payment

def pay_and_verify(page, target_date, slot, capture_dir=None):
    """确认页金额非 0 时停止；金额未知时仅在找到明确支付控件后点击并核验订单。
    返回 (status, detail)：succeeded / ambiguous / failed。

    支付按钮从未见过真实 DOM，因此按可靠性分层定位：先按钮类元素+精确文本，
    再放宽；全程截图留证；失败时把页面文本写入日志供远程诊断。
    """
    body = page.evaluate("() => document.body.innerText")
    amount_values = _order_amount_values(body)
    amount = parse_order_amount(body)
    log.info("确认页金额：%s 元", amount)
    if len(set(amount_values)) > 1:
        return "failed", "确认页金额标签数值冲突，按安全规则停止"
    if amount is not None and amount != 0:
        return "failed", f"订单金额为 {amount} 元（非 0），按安全规则停止"
    if amount is None:
        log.warning("确认页金额未识别；仅在找到可见且可用的明确支付控件时继续")
    if capture_dir:
        try:
            page.screenshot(path=str(capture_dir / "confirm-page.png"))
        except Exception:  # noqa: BLE001
            pass

    def click_pay_candidate(node, label):
        node.click()
        log.info("已点击支付控件（%s）", label)
        return True

    clicked = False
    # 1) 按钮类元素 + 精确文本（最可靠）
    pay_texts = ["立即支付", "去支付", "支 付", "支付"]
    for sel in ("button", "[role=button]", "a", ".btn",
                "input[type=submit]", "input[type=button]"):
        for txt in pay_texts:
            nodes = page.locator(sel).filter(has_text=txt)
            for i in range(min(nodes.count(), 5)):
                node = nodes.nth(i)
                try:
                    if not node.is_visible() or not node.is_enabled():
                        continue
                    label = (node.inner_text() or node.get_attribute("value") or "").strip()
                    # 排除倒计时/状态类文字节点
                    if re.search(r"倒计时|状态|须知|未支付", label):
                        continue
                    if not re.fullmatch(
                        r"(立即)?(去)?支\s*付(订单)?(?:\s*[（(]\s*\d+\s*(?:s|秒)?\s*[）)])?",
                        label,
                    ):
                        continue
                    clicked = click_pay_candidate(node, f"{sel}:{label}")
                    break
                except Exception:  # noqa: BLE001
                    continue
            if clicked:
                break
        if clicked:
            break
    # 2) 兜底：任意可见元素文本恰好是支付字样
    if not clicked and amount == 0:
        for txt in pay_texts:
            if click_first_visible(page, txt, timeout_ms=400):
                clicked = True
                log.info("已点击支付控件（text兜底:%s）", txt)
                break
    if not clicked:
        snippet = safe_body_text(page, 600)
        log.warning("确认页未找到支付按钮，页面文本片段：%s", snippet.replace("\n", " | "))
        inspection = inspect_payment(page, capture_dir)
        if amount is None:
            return "ambiguous", (
                "确认页金额无法识别且未找到支付按钮，未点击支付；"
                f"{inspection}，请人工核对（订单可能 5 分钟后自动取消）"
            )
        return "ambiguous", f"确认页未找到支付按钮，订单未支付；{inspection}（5 分钟后将自动取消）"

    time.sleep(2.5)
    # 支付后可能弹提示框（成功提示/二次确认）
    for _ in range(3):
        confirm_if_popped(page, ("确定", "知道了", "好的", "我知道了"), timeout_ms=1500)
        if "/venue/orders" in page.url:
            break
        time.sleep(1)
    if "/venue/orders" not in page.url:
        robust_goto(page, ORDERS_URL)
    time.sleep(2)
    rows = page.evaluate("""() => {
      const trs = [...document.querySelectorAll('table tbody tr, .order-list li, .order-item')];
      return trs.map(tr => tr.innerText.replace(/\\s+/g, ' ').trim()).filter(t => t.length > 0);
    }""")
    today_marks = [target_date.isoformat(), date_label_cn(target_date)]
    for row in rows:
        if "健身房" not in row or not any(mk in row for mk in today_marks):
            continue
        if slot and slot not in row:
            continue
        log.info("核验订单行：%s", row[:140])
        if "已支付" in row and "正常" in row:
            return "succeeded", f"订单核验通过：{row[:80]}"
        if "未支付" in row or "待支付" in row:
            return "ambiguous", "订单已生成但未支付成功（5 分钟后将自动取消）"
    return "ambiguous", "订单页未找到匹配的已支付记录，请人工核对"


# ---------------------------------------------------------------- main

def force_select_slot(page, slot):
    """测试用：强选一个前端已禁用的时段（去掉 disabled 类后点击）。
    服务端对刚结束的时段可能仍然受理（实测 22:01 可进入支付页）。"""
    idx = page.evaluate("""(slot) => {
      const tables = [...document.querySelectorAll('table')];
      for (const tb of tables) {
        const headerRow = tb.querySelector('thead tr') || tb.rows[0];
        if (!headerRow) continue;
        const headers = [...headerRow.cells].map(c => c.innerText.trim());
        if (!headers.some(h => /^\\d{2}:\\d{2}-\\d{2}:\\d{2}$/.test(h))) continue;
        const blocks = [...tb.querySelectorAll('.reserveBlock')];
        for (const block of blocks) {
          const td = block.closest('td');
          if (!td) continue;
          if (headers[td.cellIndex] !== slot) continue;
          block.classList.remove('disabled');
          block.classList.add('free');
          return blocks.indexOf(block);
        }
      }
      return -1;
    }""", slot)
    if idx < 0:
        raise RuntimeError(f"强选失败：表格中找不到时段 {slot}")
    block = page.locator(".reserveBlock").nth(idx)
    block.click()
    confirm_if_popped(page)
    time.sleep(0.8)
    sel = page.evaluate("""() => {
      const b = document.querySelector('.reserveBlock.selected');
      return b ? b.innerText.trim() : null;
    }""")
    if not sel:
        # 诊断留证：可能确认弹窗文案不同（如负剩余分钟），或服务端拒绝
        body = safe_body_text(page, 500)
        log.warning("强选后无选中态，页面文本片段：%s", body.replace("\n", " | "))
        try:
            page.screenshot(path=str(ROOT / "data/logs/gym/captures/force-select-fail.png"))
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"强选 {slot} 后未进入选中状态")
    log.info("已强选时段 %s（%s）", slot, sel)
    return slot, sel


def inspect_payment(page, capture_dir):
    """不支付，只采集支付页证据：截图 + 全部按钮类元素的文本/类名/位置。
    返回人类可读的候选描述，用于校准 pay_and_verify 的定位逻辑。"""
    if capture_dir:
        try:
            capture_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(capture_dir / "confirm-page.png"))
        except Exception:  # noqa: BLE001
            pass
    controls = page.evaluate("""() => {
      const out = [];
      for (const el of document.querySelectorAll('button, [role=button], a, .btn, input[type=submit], input[type=button]')) {
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        const text = (el.innerText || el.value || '').replace(/\\s+/g, ' ').trim();
        out.push({ tag: el.tagName, cls: String(el.className).slice(0, 60),
                   text: text.slice(0, 40),
                   rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
                   disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true' });
      }
      return out;
    }""")
    lines = [f"{c['tag']} cls={c['cls']!r} text={c['text']!r} rect={c['rect']} disabled={c['disabled']}"
             for c in controls]
    body = page.evaluate("() => document.body.innerText")
    money_lines = [ln.strip() for ln in body.splitlines() if ("金额" in ln or "支付" in ln or "倒计时" in ln)]
    payload = {"controls": controls, "money_lines": money_lines}
    if capture_dir:
        try:
            capture_dir.mkdir(parents=True, exist_ok=True)
            (capture_dir / "pay-inspect.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:  # noqa: BLE001
            pass
    log.info("支付页金额/支付相关文本：%s", json.dumps(money_lines, ensure_ascii=False))
    log.info("支付页可见控件：\n%s", "\n".join(lines))
    return f"支付页检查完成：{len(controls)} 个可见控件，已截图与 pay-inspect.json"


def run(args) -> dict:
    """执行一次完整预约流程，返回结果 dict（同时写入 --json-result）。"""
    target_url = VENUE_URL_FMT.format(venue=args.venue)
    target_date = date_cls.fromisoformat(args.date) if args.date else datetime.now(SHANGHAI).date()
    slots = [s.strip() for s in args.slots.split(",")] if args.slots else list(PREFERRED_SLOTS)
    capture_dir = ROOT / "data" / "logs" / "gym" / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    result = {"status": "failed", "detail": "", "date": target_date.isoformat(),
              "slots": slots, "venue": args.venue, "actual_slot": None}

    log.info("目标：%s 日期：%s 时段：%s", target_url, target_date, slots)
    release_delay = _booking_release_delay_seconds()
    if release_delay:
        log.info("放号前不启动预约流程，等待至 08:00:20（%.0f 秒）", release_delay)
        time.sleep(release_delay)
    if getattr(args, "credentials_stdin", False):
        user, pwd = read_stdin_credentials()
        log.info("凭据来源：调度器 stdin")
    else:
        user, pwd = read_credentials()
        log.info("凭据来源：%s", credentials_file())

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        ctx = browser.new_context(user_agent=USER_AGENT,
                                  viewport={"width": 1280, "height": 800},
                                  locale="zh-CN", timezone_id="Asia/Shanghai")
        page = ctx.new_page()
        page.set_default_timeout(8000)

        login(page, user, pwd, target_url)

        existing_bookings = []
        if not args.skip_order_check:
            order_snapshot = check_existing_orders(page, target_date)
            existing_bookings = order_snapshot["booked"]
            if order_snapshot["pending"]:
                result.update(
                    status="ambiguous",
                    detail=("当天存在未支付订单，避免重复下单，请人工确认："
                            f"{_format_existing_bookings(order_snapshot['pending'])}"),
                )
                log.warning(result["detail"])
                return result

            if existing_bookings:
                result.update(_existing_booking_failure(existing_bookings))
                log.warning(result["detail"])
                return result

        robust_goto(page, target_url)
        settle_after_login(page, target_url)
        ensure_target_date(page, target_date)

        if getattr(args, "force_slot", None):
            slot, capacity = force_select_slot(page, args.force_slot)
        else:
            # 不按时钟放弃：无空位时每 2 分钟重查一次，最多 15 次（约 30 分钟）
            picked = None
            for attempt in range(1, 16):
                picked = pick_slot(page, slots)
                if picked:
                    break
                if attempt == 15:
                    break
                log.info("第 %d 次查询无空位，120 秒后重查（最多 15 次）", attempt)
                time.sleep(120)
                robust_goto(page, target_url)
                settle_after_login(page, target_url)
                ensure_target_date(page, target_date)
            if not picked:
                result.update(status="no_slot",
                              detail="多次查询均无空位（15 次，约 30 分钟）")
                log.info(result["detail"])
                return result
            slot, capacity = picked
        result["actual_slot"] = slot

        amount = read_amount(page)
        log.info("订单金额：%s 元", amount)
        if amount != 0:
            result["detail"] = f"金额为 {amount} 元（非 0），按安全规则停止"
            log.error(result["detail"])
            return result

        agree = page.locator("input[type=checkbox]").first
        try:
            if not agree.is_checked():
                agree.check()
        except Exception:  # noqa: BLE001
            page.get_by_text("已阅读并同意", exact=False).first.click()
        time.sleep(0.5)
        if not agree.is_checked():
            raise RuntimeError("预约须知未能勾选")

        page.get_by_text("提交", exact=True).first.click()
        log.info("已点击提交，等待验证码")

        if wait_either(page, [".verifybox img", "img[src^='data:image']"], 5000):
            order_page = solve_click_captcha(
                page,
                capture_dir,
                manual_only=getattr(args, "manual_captcha", False),
            )
            if order_page is None:
                result.update(_result_without_confirmation(
                    page, target_date, slot, known_bookings=existing_bookings))
                log.error("%s", result["detail"])
                return result
            page = order_page  # 确认页可能在新标签页，后续支付/核验切换过去
        elif "tradeNo" not in page.url:
            result.update(_result_without_confirmation(
                page, target_date, slot, known_bookings=existing_bookings))
            log.warning("%s", result["detail"])
            return result

        page.wait_for_load_state("domcontentloaded")
        log.info("订单确认页：%s", page.url)
        if "tradeNo" not in page.url:
            result["detail"] = "验证码通过但未到达订单确认页"
            log.warning(result["detail"])
            return result

        if getattr(args, "no_pay", False):
            info = inspect_payment(page, capture_dir)
            result.update(status="inspected", detail=info)
            return result

        status, detail = pay_and_verify(page, target_date, slot, capture_dir)
        result.update(status=status, detail=detail)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="南大健身房自动预约执行器")
    parser.add_argument("--venue", default="129", help="场馆 id：129一层 / 162负一层(测试)")
    parser.add_argument("--date", default=None, help="目标日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--slots", default=None, help="逗号分隔的时段优先级")
    parser.add_argument("--json-result", default=None, help="结果 JSON 写入路径")
    parser.add_argument("--headless", action="store_true", help="无头模式（服务器部署用）")
    parser.add_argument("--credentials-stdin", action="store_true",
                        help="从 stdin 读 JSON 凭据（调度器调用方式，优先于凭据文件）")
    parser.add_argument("--skip-order-check", action="store_true", help="跳过当天已有订单预检（测试用）")
    parser.add_argument("--force-slot", default=None, help="强选指定时段（含前端已禁用的，测试用）")
    parser.add_argument("--no-pay", action="store_true", help="到达支付页只检查不支付（测试用）")
    parser.add_argument("--manual-captcha", action="store_true",
                        help="验证码弹出后等待人工点击，不尝试自动识别")
    parser.add_argument("--check-login", action="store_true",
                        help="凭据验证模式：只跑登录（含滑块），成功即退出")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    log_dir = setup_logging()
    result = {"status": "failed", "detail": "", "actual_slot": None}
    try:
        if args.check_login:
            if args.credentials_stdin:
                user, pwd = read_stdin_credentials()
            else:
                user, pwd = read_credentials()
            target_url = VENUE_URL_FMT.format(venue=args.venue)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=args.headless)
                ctx = browser.new_context(user_agent=USER_AGENT,
                                          viewport={"width": 1280, "height": 800},
                                          locale="zh-CN", timezone_id="Asia/Shanghai")
                page = ctx.new_page()
                page.set_default_timeout(8000)
                result = check_login(page, user, pwd, target_url)
        else:
            result = run(args)
    except Exception as exc:  # noqa: BLE001
        detail = f"异常：{exc}"
        retryable = "场次页未渲染出时段表格/日期条" in detail
        result = {"status": "failed", "detail": detail,
                  "actual_slot": None, "retryable": retryable}
        log.exception("流程失败")
    if not args.json_result:
        args.json_result = str(log_dir / "last-result.json")
    try:
        Path(args.json_result).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:  # noqa: BLE001
        log.exception("结果写入失败")
    log.info("最终结果：%s", json.dumps(result, ensure_ascii=False))
    code = {"succeeded": 0, "no_slot": 2, "ambiguous": 3, "inspected": 4}.get(result["status"], 1)
    sys.exit(code)


if __name__ == "__main__":
    main()
