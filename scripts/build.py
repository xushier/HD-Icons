#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HD-Icons 一键构建脚本（本地 / GitHub Actions 通用）

流程：
  1. 校验 inbox 新文件命名
  2. TinyPNG 无损压缩 inbox 中的 PNG（SVG 不压缩）
  3. 分发入库：inbox 文件移入对应目录，重名按"同前缀最大序号+1"自动改名
  4. 全量重建 icons.json（输出格式与历史版本完全一致）
  5. 更新 README.md 中的数量标记 <!--ICONS:xxx-->
  6. 重新生成三张合并预览图（_icons-radius.jpg / _icons-circle.jpg / _icons-svg.jpg）

用法：
  python scripts/build.py --repo .

环境变量：
  TINYPNG_KEY    TinyPNG API 密钥（inbox 有 PNG 时必需；GitHub 上配置为 Secret）
  HDICONS_FONT   预览图标签字体路径（可选，默认自动查找）
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

FOLDERS = ["border-radius", "circle", "svg"]
RAW_BASE = "https://raw.githubusercontent.com/xushier/HD-Icons/main"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".gif"}

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NUM_SUFFIX_RE = re.compile(r"-\d+$")
README_MARKER_RE = re.compile(r"(<!--ICONS:(\w+)-->)(.*?)(<!--/ICONS:\2-->)")

# 预览图排版参数
PREVIEW = {
    "icon": 128,        # 单个图标缩略尺寸
    "cols": 15,         # 每行图标数
    "gap_x": 30,        # 水平间距
    "gap_y": 62,        # 垂直间距（含文件名文字区域）
    "pad": 20,          # 四周留白
    "text_size": 17,    # 文件名字号
    "bg": (244, 246, 249),
    "fg": (62, 66, 72),
}


def log(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"[警告] {msg}", file=sys.stderr, flush=True)


def fail(msg):
    print(f"[错误] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# ---------------------------------------------------------------- 1. 校验 inbox

def validate_inbox(repo):
    """检查 inbox 内新文件的类型与命名，返回 (errors, warnings, files)。"""
    errors, warnings, files = [], [], {}
    for folder in FOLDERS:
        inbox_dir = repo / "inbox" / folder
        items = []
        if not inbox_dir.is_dir():
            files[folder] = items
            continue
        expected = ".svg" if folder == "svg" else ".png"
        for f in sorted(inbox_dir.iterdir()):
            if f.name == ".gitkeep" or not f.is_file():
                continue
            if f.suffix.lower() != expected:
                errors.append(f"inbox/{folder}/ 只接受 {expected} 文件，发现：{f.name}")
                continue
            if not NAME_RE.match(f.stem):
                errors.append(f"命名不合法（仅允许小写字母/数字/连字符）：{f.name}")
                continue
            if not NUM_SUFFIX_RE.search(f.stem):
                warnings.append(f"{f.name} 未以数字结尾，建议形如 name-1 的命名")
            items.append(f)
        files[folder] = items
    return errors, warnings, files


# ---------------------------------------------------------------- 2. TinyPNG 压缩

def tinify(path, key):
    """调用 TinyPNG API 压缩单个 PNG，返回 (压缩前字节数, 压缩后字节数, 已用额度)。"""
    data = path.read_bytes()
    req = urllib.request.Request("https://api.tinify.com/shrink", data=data)
    req.add_header("Authorization",
                   "Basic " + base64.b64encode(f"api:{key}".encode()).decode())
    with urllib.request.urlopen(req, timeout=180) as resp:
        info = json.loads(resp.read().decode())
        quota = (resp.headers.get("Compression-Count")
                 or resp.headers.get("X-Compression-Count"))
    with urllib.request.urlopen(info["output"]["url"], timeout=180) as r:
        out = r.read()
    if len(out) < len(data):
        path.write_bytes(out)
    return len(data), path.stat().st_size, quota


def compress_inbox(files, key):
    saved = 0
    quota = None
    pngs = files["border-radius"] + files["circle"]
    for f in pngs:
        try:
            before, after, quota = tinify(f, key)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                fail("TinyPNG 本月免费额度已用完（500 张/月），本次未做任何改动")
            fail(f"压缩失败 {f.name}：HTTP {e.code} {e.reason}")
        except (urllib.error.URLError, OSError) as e:
            fail(f"压缩失败 {f.name}：网络错误 {e}")
        saved += before - after
        log(f"  {f.name}: {before // 1024}KB -> {after // 1024}KB")
    msg = f"共压缩 {len(pngs)} 张，节省 {saved // 1024}KB"
    if quota:
        msg += f"（本月已用 {quota}/500）"
    log(msg)


# ---------------------------------------------------------------- 3. 分发入库

def available_name(target_dir, name):
    """若目标已存在同名文件，按"同前缀最大序号+1"改名，否则保持原名。"""
    if not (target_dir / name).exists():
        return name
    stem, ext = Path(name).stem, Path(name).suffix
    prefix = NUM_SUFFIX_RE.sub("", stem)
    max_num = 0
    for f in target_dir.iterdir():
        m = re.fullmatch(re.escape(prefix) + r"-(\d+)", f.stem)
        if m and f.suffix.lower() == ext.lower():
            max_num = max(max_num, int(m.group(1)))
    n = max_num + 1
    while (target_dir / f"{prefix}-{n}{ext}").exists():
        n += 1
    return f"{prefix}-{n}{ext}"


def dispatch(repo, files):
    moved = []
    for folder, items in files.items():
        if not items:
            continue
        target = repo / folder
        for f in items:
            new_name = available_name(target, f.name)
            if new_name != f.name:
                log(f"  重名处理：{folder}/{f.name} -> {new_name}")
            shutil.move(str(f), str(target / new_name))
            moved.append(f"{folder}/{new_name}")
    return moved


# ---------------------------------------------------------------- 4. icons.json

def build_icons_json(repo):
    """全量重建 icons.json，逻辑与历史脚本一致（含跨目录重名加后缀的去重行为）。"""
    icons, used = [], set()
    counts = {"radius": 0, "circle": 0, "svg": 0}
    for folder in FOLDERS:
        d = repo / folder
        if not d.is_dir():
            warn(f"文件夹不存在，跳过：{folder}")
            continue
        for file in sorted(d.iterdir()):
            if not (file.is_file() and file.suffix.lower() in IMAGE_EXTS):
                continue
            name = file.stem
            original = name
            url = f"{RAW_BASE}/{folder}/{file.name}"
            counter = 1
            while name in used:
                name = f"{original}-{counter}"
                counter += 1
            used.add(name)
            icons.append({"name": name, "url": url})
            counts[{"border-radius": "radius", "circle": "circle", "svg": "svg"}[folder]] += 1

    update_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "name": "小迪的HD-Icons",
        "description": (f"当前数量：{len(icons)}，更新于：{update_at}。"
                        "不定期更新，有需求欢迎提交：github.com/xushier/HD-Icons"),
        "total_count": len(icons),
        "update_at": update_at,
        "icons": icons,
    }
    (repo / "icons.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    counts["total"] = len(icons)
    return counts


# ---------------------------------------------------------------- 5. README 标记

def update_readme(repo, counts):
    readme = repo / "README.md"
    if not readme.is_file():
        warn("README.md 不存在，跳过数量更新")
        return
    text = readme.read_text(encoding="utf-8")

    def repl(m):
        key = m.group(2)
        if key in counts:
            return m.group(1) + str(counts[key]) + m.group(4)
        warn(f"README 中存在未知标记 ICONS:{key}")
        return m.group(0)

    readme.write_text(README_MARKER_RE.sub(repl, text), encoding="utf-8")


# ---------------------------------------------------------------- 6. 预览图

def load_font(size):
    from PIL import ImageFont
    candidates = [
        os.environ.get("HDICONS_FONT"),
        str(Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                pass
    warn("未找到可用字体，预览图将使用默认位图字体")
    return ImageFont.load_default()


def rasterize_svg(svg_path, size, cache_dir):
    """把 SVG 光栅化为 PNG（依次尝试 rsvg-convert / resvg / cairosvg），失败返回 None。"""
    out = cache_dir / (svg_path.stem + ".png")
    if out.exists():
        return out
    cmds = []
    if shutil.which("rsvg-convert"):
        cmds.append(["rsvg-convert", "-w", str(size), "-h", str(size),
                     "-o", str(out), str(svg_path)])
    if shutil.which("resvg"):
        cmds.append(["resvg", "--width", str(size), "--height", str(size),
                     str(svg_path), str(out)])
    for cmd in cmds:
        try:
            if subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0 \
                    and out.exists():
                return out
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(out),
                         output_width=size, output_height=size)
        if out.exists():
            return out
    except Exception:
        pass
    return None


def merge_preview(repo, folder, out_name):
    """把目录内全部图标合并为一张带文件名标注的 JPEG 预览图。"""
    from PIL import Image, ImageDraw
    import textwrap

    src = repo / folder
    files = sorted(f for f in src.iterdir()
                   if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
    if not files:
        warn(f"{folder}/ 为空，跳过预览图 {out_name}")
        return

    font = load_font(PREVIEW["text_size"])
    cell_w = PREVIEW["icon"] + PREVIEW["gap_x"]
    cell_h = PREVIEW["icon"] + PREVIEW["gap_y"]
    rows = (len(files) + PREVIEW["cols"] - 1) // PREVIEW["cols"]
    width = PREVIEW["cols"] * cell_w - PREVIEW["gap_x"] + 2 * PREVIEW["pad"]
    height = rows * cell_h - PREVIEW["gap_y"] + 2 * PREVIEW["pad"]

    sheet = Image.new("RGB", (width, height), PREVIEW["bg"])
    draw = ImageDraw.Draw(sheet)

    cache_dir = Path(tempfile.mkdtemp(prefix="hdicons_"))
    skipped = 0
    try:
        for i, f in enumerate(files):
            row, col = divmod(i, PREVIEW["cols"])
            x = col * cell_w + PREVIEW["pad"]
            y = row * cell_h + PREVIEW["pad"]

            if f.suffix.lower() == ".svg":
                raster = rasterize_svg(f, 512, cache_dir)
                if raster is None:
                    skipped += 1
                    continue
                f = raster
            try:
                icon = Image.open(f).convert("RGBA")
            except OSError as e:
                warn(f"无法读取 {f.name}：{e}")
                skipped += 1
                continue
            icon = icon.resize((PREVIEW["icon"], PREVIEW["icon"]),
                               Image.Resampling.LANCZOS)
            sheet.paste(icon, (x, y), icon)

            wrapped = "\n".join(textwrap.wrap(f.stem, width=16))
            bbox = draw.textbbox((0, 0), wrapped, font=font)
            text_w = bbox[2] - bbox[0]
            draw.text((x + (PREVIEW["icon"] - text_w) // 2,
                       y + PREVIEW["icon"] + 4),
                      wrapped, font=font, fill=PREVIEW["fg"])
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)

    rendered = len(files) - skipped
    if rendered < len(files):
        # 预览图必须包含全部图标，有遗漏时不覆盖已有图片，避免生成残缺预览
        warn(f"{folder} 有 {skipped} 个文件未能渲染（SVG 光栅化不可用或文件损坏），"
             f"本次跳过写入 {out_name}，保留现有版本")
        return
    out_path = repo / out_name
    sheet.save(out_path, format="JPEG", quality=78, dpi=(128, 128))
    log(f"  {out_name}: {len(files)} 个图标，{sheet.width}x{sheet.height}")


# ---------------------------------------------------------------- 主流程

def main():
    parser = argparse.ArgumentParser(description="HD-Icons 一键构建")
    parser.add_argument("--repo", default=".", help="仓库根目录")
    parser.add_argument("--skip-compress", action="store_true",
                        help="跳过 TinyPNG 压缩（仅调试用）")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()

    log("== 1/6 校验 inbox ==")
    errors, warnings, inbox_files = validate_inbox(repo)
    for w in warnings:
        warn(w)
    if errors:
        for e in errors:
            warn(e)
        fail("inbox 存在问题，已中止（所有文件保持原样）")

    png_count = len(inbox_files["border-radius"]) + len(inbox_files["circle"])
    svg_count = len(inbox_files["svg"])
    total_inbox = png_count + svg_count
    log(f"inbox 共 {total_inbox} 个新文件（PNG {png_count}，SVG {svg_count}）")

    if png_count and not args.skip_compress:
        key = os.environ.get("TINYPNG_KEY", "").strip()
        if not key:
            fail("inbox 中有 PNG 但未设置 TINYPNG_KEY"
                 "（GitHub 上需在 Settings -> Secrets 中配置）")
        log("== 2/6 TinyPNG 无损压缩 ==")
        compress_inbox(inbox_files, key)
    else:
        log("== 2/6 跳过压缩（无 PNG 或指定 --skip-compress）==")

    log("== 3/6 分发入库 ==")
    moved = dispatch(repo, inbox_files)
    for m in moved:
        log(f"  + {m}")

    log("== 4/6 重建 icons.json ==")
    counts = build_icons_json(repo)
    log(f"总数 {counts['total']}（圆角矩形 {counts['radius']} / "
        f"圆形 {counts['circle']} / SVG {counts['svg']}）")

    log("== 5/6 更新 README 数量标记 ==")
    update_readme(repo, counts)

    log("== 6/6 生成预览图 ==")
    merge_preview(repo, "border-radius", "_icons-radius.jpg")
    merge_preview(repo, "circle", "_icons-circle.jpg")
    merge_preview(repo, "svg", "_icons-svg.jpg")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"added={len(moved)}\n")

    log(f"完成！本次新增 {len(moved)} 个图标。")


if __name__ == "__main__":
    main()
