#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_icon.py —— 把 `assets/logo.svg` 光栅化成多尺寸 `assets/ace.ico`。

为什么自己写光栅化而不用现成库：**本项目的构建依赖刻意为零**，而 svg->png 那套
（cairosvg / svglib+reportlab / Pillow+额外插件 / ImageMagick / Inkscape / 无头浏览器）
每一条都要联网装或要外部二进制。`logo.svg` 恰好是**纯几何图形**——一个圆角矩形底板、
一条描边路径（盾）、一条折线（提示符）、一个小圆角矩形（光标），没有文字、没有复杂曲线、
没有 filter——所以一个够用的小光栅化器是可行的，而且**结果可以当场检查**（渲染成 PNG
读回来看），不需要相信"它应该对"。

支持范围就是这份 SVG 用到的子集，多一样都不做：
  * `<rect>`（含 rx 圆角）、`<path>`（M/L/C，绝对与相对）
  * `fill` 纯色 / `stroke` 纯色或 linearGradient（userSpaceOnUse）
  * `stroke-width` / `stroke-linecap: round` / `stroke-linejoin: round`
抗锯齿用 3x3 超采样（每像素 9 个采样点），纯 `math` + `re` + `struct` + `zlib`。

ICO 编码：从 Vista 起 ICO 允许直接内嵌 PNG，所以每个尺寸存一张 PNG——
这也是最省事且被所有现代 Windows 接受的做法。

用法：
    python packaging/make_icon.py                    # 写 assets/ace.ico
    python packaging/make_icon.py --preview 512      # 另存一张大图便于肉眼核对
退出码 0 = 生成成功；1 = 失败（并说明原因）。
"""

from __future__ import annotations

import argparse
import math
import re
import struct
import sys
import zlib
from pathlib import Path

# Windows 控制台兼容：emoji / 非本机代码页字符不该让脚本崩（与仓库其他入口同一道防线）
for _s in (sys.stdout, sys.stderr):
    try:
        if _s.encoding and _s.encoding.lower() not in ("utf-8", "utf8"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SS = 3          # 超采样倍数：每像素 SS*SS 个采样点
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


# ---------------------------------------------------------------- 颜色与渐变
def parse_color(text: str):
    """#rgb / #rrggbb / none -> (r, g, b, a) 或 None。"""
    if not text:
        return None
    t = text.strip().lower()
    if t in ("none", "transparent"):
        return None
    m = re.fullmatch(r"#([0-9a-f]{3})", t)
    if m:
        h = m.group(1)
        return tuple(int(c * 2, 16) for c in h) + (255,)
    m = re.fullmatch(r"#([0-9a-f]{6})", t)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    raise ValueError(f"不支持的颜色写法: {text!r}")


class LinearGradient:
    """线性渐变，够用即可（这份 SVG 只有一处渐变）。

    这里有个容易踩的坑：`gradientUnits` **默认是 objectBoundingBox**，不是 userSpaceOnUse。
    也就是说 `x1="0" y1="0" x2="1" y2="1"` 指的是**图形包围盒的比例**（0 到 1），而不是
    绝对坐标 0 到 1。本仓库的 logo 正是省略了 gradientUnits 的写法——第一版实现把它当绝对
    坐标，于是所有采样点的 t 都被钳到 0，整条盾牌描边渲染成纯青色（第一个 stop）。
    浏览器渲染出来是有渐变的，所以那是解析错误，不是 SVG 的问题。

    于是这里保留原始坐标与 units，等图形解析完、拿到包围盒之后再换算成绝对坐标
    （见 `_resolve_gradients`）。
    """

    def __init__(self, stops, x1, y1, x2, y2, user_space: bool):
        self.stops = stops                      # [(offset, (r,g,b,a)), ...]
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.user_space = user_space
        self._len2 = 0.0
        self._dx = self._dy = 0.0

    def bind(self, bbox):
        """把（可能是比例的）坐标换算成该图形包围盒下的绝对坐标。

        objectBoundingBox 下，x 按 bbox 宽度、y 按 bbox 高度缩放——长宽不等时渐变会随之
        拉伸，这正是 SVG 规定（也是浏览器行为）。y2 缺省为 1，与 x2 同样处理。
        """
        if not self.user_space:
            bx, by, bw, bh = bbox
            self.x1, self.x2 = bx + self.x1 * bw, bx + self.x2 * bw
            self.y1, self.y2 = by + self.y1 * bh, by + self.y2 * bh
        self._dx, self._dy = self.x2 - self.x1, self.y2 - self.y1
        self._len2 = self._dx * self._dx + self._dy * self._dy

    def at(self, x: float, y: float):
        if self._len2 <= 0:
            t = 0.0
        else:
            t = ((x - self.x1) * self._dx + (y - self.y1) * self._dy) / self._len2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        stops = self.stops
        if t <= stops[0][0]:
            return stops[0][1]
        if t >= stops[-1][0]:
            return stops[-1][1]
        for i in range(len(stops) - 1):
            o0, c0 = stops[i]
            o1, c1 = stops[i + 1]
            if o0 <= t <= o1:
                k = 0.0 if o1 == o0 else (t - o0) / (o1 - o0)
                return tuple(round(c0[j] + (c1[j] - c0[j]) * k) for j in range(4))
        return stops[-1][1]


# ---------------------------------------------------------------- SVG 解析
_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"([MmLlHhVvCcSsZz])")


def _nums(text: str):
    return [float(x) for x in _NUM.findall(text or "")]


def _attrs(tag_text: str) -> dict:
    return {k: v for k, v in re.findall(r'([a-zA-Z:_-]+)\s*=\s*"([^"]*)"', tag_text)}


def parse_svg(svg_text: str):
    """返回 (width, height, [shape...])；shape 是 dict。

    只认这份 logo 用到的标签/属性；遇到不认识的东西**直接抛错**，不静默忽略——
    静默忽略的后果是"图标少了一块而没人知道"。
    """
    root = _attrs(re.search(r"<svg\b([^>]*)>", svg_text, re.S).group(1))
    width = float(root.get("width") or 0) or 128.0
    height = float(root.get("height") or 0) or 128.0

    defs = re.search(r"<defs\b.*?</defs>", svg_text, re.S)
    gradients = {}
    if defs:
        for g in re.finditer(r"<linearGradient\b([^>]*)>(.*?)</linearGradient>", defs.group(0), re.S):
            ga = _attrs(g.group(1))
            stops = []
            for sm in re.finditer(r"<stop\b([^>]*)/?>", g.group(2)):
                sa = _attrs(sm.group(1))
                stops.append((float(sa.get("offset") or 0), parse_color(sa.get("stop-color"))))
            stops.sort(key=lambda s: s[0])
            if len(stops) < 2:
                raise ValueError(f"渐变 {ga.get('id')!r} 的 stop 少于 2 个")
            # gradientUnits 缺省 = objectBoundingBox（见 LinearGradient 的说明）
            units = (ga.get("gradientUnits") or "objectBoundingBox").strip()
            gradients[ga.get("id")] = LinearGradient(
                stops,
                float(ga.get("x1") or 0), float(ga.get("y1") or 0),
                float(ga.get("x2") if ga.get("x2") is not None else 1),
                float(ga.get("y2") if ga.get("y2") is not None else 1),
                user_space=(units == "userSpaceOnUse"))

    body = svg_text[svg_text.index(">", svg_text.index("<svg")) + 1:]
    body = re.sub(r"<defs\b.*?</defs>", "", body, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)

    shapes = []
    for m in re.finditer(r"<(rect|path)\b([^>]*?)/?>", body, re.S):
        kind, raw = m.group(1), m.group(2)
        a = _attrs(raw)

        def paint(key):
            """把 fill/stroke 的值解析成 颜色元组 或 渐变对象 或 None。"""
            v = a.get(key)
            gm = re.fullmatch(r"url\(#([^)]+)\)", (v or "").strip())
            if gm:
                if gm.group(1) not in gradients:
                    raise ValueError(f"{key} 引用了不存在的渐变: {gm.group(1)}")
                return gradients[gm.group(1)]
            return parse_color(v)

        fill = paint("fill")
        stroke = paint("stroke")
        sw = float(a.get("stroke-width") or 0)
        if fill is None and (stroke is None or sw <= 0):
            continue        # 既无填充也无描边 -> 不画（SVG 默认 fill 是黑，但这里显式写了 none）

        if kind == "rect":
            x, y = float(a.get("x") or 0), float(a.get("y") or 0)
            w, h = float(a.get("width") or 0), float(a.get("height") or 0)
            shapes.append({"kind": "rect", "x": x, "y": y, "w": w, "h": h,
                           "rx": float(a.get("rx") or 0),
                           "fill": fill, "stroke": stroke, "sw": sw})
        else:
            pts = _flatten_path(a.get("d") or "")
            if len(pts) < 2:
                raise ValueError(f"path 折点太少: {a.get('d')!r}")
            shapes.append({"kind": "path", "pts": pts, "closed": a.get("d", "").strip().rstrip().upper().endswith("Z"),
                           "fill": fill, "stroke": stroke, "sw": sw,
                           "cap_round": (a.get("stroke-linecap") == "round"),
                           "join_round": (a.get("stroke-linejoin") == "round")})
    if not shapes:
        raise ValueError("SVG 里没解析出任何图形")
    _resolve_gradients(shapes)
    return width, height, shapes


def _flatten_path(d: str, curve_steps: int = 24):
    """把 M/L/H/V/C/Z 折成折线。只支持这份 logo 用到的命令。"""
    toks = [t for t in _CMD.split(d) if t.strip()]
    pts = []
    cx = cy = 0.0
    start = (0.0, 0.0)
    i = 0
    cmd = None
    while i < len(toks):
        tok = toks[i]
        if _CMD.fullmatch(tok):
            cmd = tok
            i += 1
        if cmd is None:
            raise ValueError(f"path 4 以非命令开头: {tok!r}")
        rel = cmd.islower()
        up = cmd.upper()

        def take(n):
            nonlocal i
            vals = _nums(toks[i]) if i < len(toks) and not _CMD.fullmatch(toks[i]) else []
            if len(vals) < n:
                raise ValueError(f"命令 {cmd} 参数不足: {toks[i] if i < len(toks) else 'EOF'}")
            i += 1
            return vals[:n]

        if up == "M":
            x, y = take(2)
            cx, cy = (cx + x, cy + y) if rel else (x, y)
            pts.append((cx, cy))
            start = (cx, cy)
            cmd = "l" if rel else "L"        # 后续隐式 lineto
        elif up == "L":
            x, y = take(2)
            cx, cy = (cx + x, cy + y) if rel else (x, y)
            pts.append((cx, cy))
        elif up == "H":
            (x,) = take(1)
            cx = cx + x if rel else x
            pts.append((cx, cy))
        elif up == "V":
            (y,) = take(1)
            cy = cy + y if rel else y
            pts.append((cx, cy))
        elif up == "C":
            v = take(6)
            p1 = (cx + v[0], cy + v[1]) if rel else (v[0], v[1])
            p2 = (cx + v[2], cy + v[3]) if rel else (v[2], v[3])
            p3 = (cx + v[4], cy + v[5]) if rel else (v[4], v[5])
            for s in range(1, curve_steps + 1):
                t = s / curve_steps
                mt = 1 - t
                bx = (mt ** 3) * cx + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
                by = (mt ** 3) * cy + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
                pts.append((bx, by))
            cx, cy = p3
        elif up == "Z":
            if pts and pts[-1] != start:
                pts.append(start)
            cx, cy = start
        else:
            raise ValueError(f"暂不支持的 path 命令: {cmd}")
    return pts


# ---------------------------------------------------------------- 光栅化
def _seg_dist2(px, py, ax, ay, bx, by):
    """点到线段的距离平方。"""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / l2
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    qx, qy = ax + t * dx, ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


def _rounded_rect_inside(x, y, rx0, ry0, w, h, r):
    """点是否在圆角矩形内（含边缘）。"""
    if x < rx0 or y < ry0 or x > rx0 + w or y > ry0 + h:
        return False
    if r <= 0:
        return True
    # 四个角用圆心距离判断；其余区域落在矩形内即算内
    cx = min(max(x, rx0 + r), rx0 + w - r)
    cy = min(max(y, ry0 + r), ry0 + h - r)
    if (x, y) == (cx, cy):
        return True
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r + 1e-9


def _point_in_poly(px, py, pts):
    """奇偶规则（这份 logo 的折线不需要非零规则）。"""
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            xin = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < xin:
                inside = not inside
    return inside


def _stroke_dist(x, y, pts, closed):
    best = float("inf")
    n = len(pts)
    last = n if closed else n - 1
    for i in range(last):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        d2 = _seg_dist2(x, y, ax, ay, bx, by)
        if d2 < best:
            best = d2
    return math.sqrt(best)


def _geom_bbox(sh):
    """几何包围盒（**不含**描边宽度）—— objectBoundingBox 用的是这个。

    SVG 规定 objectBoundingBox 取的是图形几何的包围盒；把 stroke-width 算进去会让
    渐变整体偏移。这里单独算，与渲染用的 `_shape_bbox`（含描边，用于裁剪遍历范围）分开。
    """
    if sh["kind"] == "rect":
        return sh["x"], sh["y"], sh["w"], sh["h"]
    xs = [p[0] for p in sh["pts"]]
    ys = [p[1] for p in sh["pts"]]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return x0, y0, max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)


def _resolve_gradients(shapes):
    """把每个图形身上的渐变按它自己的包围盒换算成绝对坐标。

    每个图形拿一份**独立副本**：同一 id 的渐变可能被多个图形引用，而 objectBoundingBox
    是相对各图形自己的包围盒，共用一个对象会让后面的图形覆盖前面的换算。
    """
    import copy
    for sh in shapes:
        for key in ("fill", "stroke"):
            g = sh.get(key)
            if isinstance(g, LinearGradient):
                g2 = copy.copy(g)
                g2.bind(_geom_bbox(sh))
                sh[key] = g2


def render(width, height, shapes, out_w, out_h):
    """渲染成 RGBA bytearray（行优先）。坐标按 width/height -> out_w/out_h 等比缩放。"""
    sx, sy = out_w / width, out_h / height
    buf = bytearray(out_w * out_h * 4)      # 全透明
    inv = 1.0 / (SS * SS)

    # 每个图形单独算覆盖率，再 source-over 合成到 buf
    for sh in shapes:
        (minx, miny, maxx, maxy) = _shape_bbox(sh, sx, sy)
        x0 = max(0, int(math.floor(minx)))
        y0 = max(0, int(math.floor(miny)))
        x1 = min(out_w - 1, int(math.ceil(maxx)))
        y1 = min(out_h - 1, int(math.ceil(maxy)))
        for py in range(y0, y1 + 1):
            for px in range(x0, x1 + 1):
                cov_fill = 0
                cov_str = 0
                acc = [0.0, 0.0, 0.0, 0.0]
                for sub in range(SS * SS):
                    ox = (sub % SS + 0.5) / SS
                    oy = (sub // SS + 0.5) / SS
                    # 目标像素内的采样点 -> 源坐标
                    gx = (px + ox) / sx
                    gy = (py + oy) / sy
                    if sh["fill"] is not None and _inside(sh, gx, gy):
                        cov_fill += 1
                        if isinstance(sh["fill"], LinearGradient):
                            c = sh["fill"].at(gx, gy)
                            for k in range(4):
                                acc[k] += c[k]
                    if sh["stroke"] is not None and sh["sw"] > 0:
                        if _stroke_covers(sh, gx, gy):
                            cov_str += 1
                            if isinstance(sh["stroke"], LinearGradient):
                                c = sh["stroke"].at(gx, gy)
                                for k in range(4):
                                    acc[k] += c[k]
                total = cov_fill + cov_str
                if total == 0:
                    continue
                if isinstance(sh["fill"], LinearGradient) or isinstance(sh["stroke"], LinearGradient):
                    r, g, b, a = (acc[k] / total for k in range(4))
                else:
                    col = sh["fill"] if cov_fill else sh["stroke"]
                    r, g, b, a = col
                alpha = total * inv * (a / 255.0)
                if alpha <= 0:
                    continue
                _blend(buf, px, py, out_w, r, g, b, alpha)
    return buf


def _shape_bbox(sh, sx, sy):
    pad = (sh["sw"] / 2.0 + 1) if sh["stroke"] is not None else 1
    if sh["kind"] == "rect":
        return ((sh["x"] - pad) * sx, (sh["y"] - pad) * sy,
                (sh["x"] + sh["w"] + pad) * sx, (sh["y"] + sh["h"] + pad) * sy)
    xs = [p[0] for p in sh["pts"]]
    ys = [p[1] for p in sh["pts"]]
    return ((min(xs) - pad) * sx, (min(ys) - pad) * sy,
            (max(xs) + pad) * sx, (max(ys) + pad) * sy)


def _inside(sh, gx, gy):
    if sh["kind"] == "rect":
        return _rounded_rect_inside(gx, gy, sh["x"], sh["y"], sh["w"], sh["h"], sh["rx"])
    return _point_in_poly(gx, gy, sh["pts"])


def _stroke_covers(sh, gx, gy):
    if sh["kind"] == "rect":
        half = sh["sw"] / 2.0
        outer = _rounded_rect_inside(gx, gy, sh["x"] - half, sh["y"] - half,
                                     sh["w"] + sh["sw"], sh["h"] + sh["sw"], sh["rx"] + half)
        inner = _rounded_rect_inside(gx, gy, sh["x"] + half, sh["y"] + half,
                                     sh["w"] - sh["sw"], sh["h"] - sh["sw"],
                                     max(0.0, sh["rx"] - half))
        return outer and not inner
    return _stroke_dist(gx, gy, sh["pts"], sh["closed"]) <= sh["sw"] / 2.0


def _blend(buf, px, py, w, r, g, b, alpha):
    i = (py * w + px) * 4
    dr, dg, db, da = buf[i], buf[i + 1], buf[i + 2], buf[i + 3]
    sa = alpha
    da_f = da / 255.0
    out_a = sa + da_f * (1 - sa)
    if out_a <= 0:
        return
    for k, sc in enumerate((r, g, b)):
        dc = (dr, dg, db)[k] / 255.0
        buf[i + k] = round(255 * (sc / 255.0 * sa + dc * da_f * (1 - sa)) / out_a)
    buf[i + 3] = round(255 * out_a)


# ---------------------------------------------------------------- PNG / ICO
def _png(rgba: bytearray, w: int, h: int) -> bytes:
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)                       # filter type 0
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def build_ico(images) -> bytes:
    """images: [(size, png_bytes), ...] -> ICO 字节。"""
    n = len(images)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    return header + entries + blobs


def _png_to_rgba(png: bytes):
    """仅供 --preview 自检用：把刚生成的 PNG 解回 RGBA，验证编码没写错。"""
    pos = 8
    w = h = 0
    idat = b""
    while pos < len(png):
        ln = struct.unpack(">I", png[pos:pos + 4])[0]
        tag = png[pos + 4:pos + 8]
        data = png[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h = struct.unpack(">II", data[:8])
        elif tag == b"IDAT":
            idat += data
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 4
    out = bytearray()
    for y in range(h):
        assert raw[y * (stride + 1)] == 0, "只支持 filter 0"
        out += raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)]
    return out, w, h


def main() -> int:
    ap = argparse.ArgumentParser(description="logo.svg -> 多尺寸 ace.ico（纯标准库）")
    ap.add_argument("--svg", default=str(REPO / "assets" / "logo.svg"))
    ap.add_argument("--out", default=str(REPO / "assets" / "ace.ico"))
    ap.add_argument("--preview", type=int, default=0,
                    help="另外渲染一张这么大的 PNG，便于肉眼核对（如 512）")
    args = ap.parse_args()

    svg_path = Path(args.svg)
    if not svg_path.is_file():
        print(f"FAIL: 找不到 {svg_path}")
        return 1
    try:
        w, h, shapes = parse_svg(svg_path.read_text(encoding="utf-8"))
    except Exception as e:                                     # noqa: BLE001
        print(f"FAIL: 解析 SVG 出错: {type(e).__name__}: {e}")
        return 1
    print(f"SVG {w:g}x{h:g}，解析出 {len(shapes)} 个图形")

    images = []
    for size in ICO_SIZES:
        rgba = render(w, h, shapes, size, size)
        # 自检：透明通道不全为零（否则等于画了个空的），且确实有内容
        opaque = sum(1 for i in range(3, len(rgba), 4) if rgba[i] > 0)
        if opaque == 0:
            print(f"FAIL: {size}px 渲染结果全透明 —— 光栅化没画上东西")
            return 1
        png = _png(rgba, size, size)
        back, bw, bh = _png_to_rgba(png)
        if (bw, bh) != (size, size) or len(back) != len(rgba):
            print(f"FAIL: {size}px PNG 自检失败（解回来尺寸/长度不对）")
            return 1
        images.append((size, png))
        print(f"  {size:>3}px  覆盖 {opaque * 100 // (size * size):>3}% 像素  png {len(png):>5} 字节")

    ico = build_ico(images)
    out = Path(args.out)
    out.write_bytes(ico)
    print(f"已写入 {out}（{len(ico)} 字节，{len(images)} 个尺寸）")

    if args.preview:
        rgba = render(w, h, shapes, args.preview, args.preview)
        p = out.with_name(f"_preview_{args.preview}.png")
        p.write_bytes(_png(rgba, args.preview, args.preview))
        print(f"预览图 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
