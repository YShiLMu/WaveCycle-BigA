#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_report_images.py — 把浪型图 PNG 内嵌进分析报告 .md 与网页报告 .html。

用法:
    python embed_report_images.py <分析输出文件夹> [--md-keep-absolute]

流程:
    1. 定位 图表/ 下 4 张 PNG（主方案/替代方案 × 全景/放大）;
    2. 定位 分析报告_*.md 与 网页报告_*.html;
    3. md：把 ![说明](...主方案_全景.png) 等图片链接替换为 base64 data URI
       （--md-keep-absolute 时保留绝对路径、保留 图表/ 目录并在文末注明回退原因）;
    4. html：把 {{主方案全景图路径}} 等 4 个占位符替换为 base64 data URI;
    5. 校验：html 内 data:image/png;base64, 数量 == <img> 数量；md 图片标记数量 == 4；
       任一不通过则以退出码 1 结束，禁止交付缺图文件。
"""

import argparse
import base64
import pathlib
import re
import sys

IMAGE_KEYS = [
    ("主方案全景", "主方案_全景.png"),
    ("主方案放大", "主方案_放大.png"),
    ("替代方案全景", "替代方案_全景.png"),
    ("替代方案放大", "替代方案_放大.png"),
]

HTML_TOKENS = {
    "主方案全景": "{{主方案全景图路径}}",
    "主方案放大": "{{主方案放大图路径}}",
    "替代方案全景": "{{替代方案全景图路径}}",
    "替代方案放大": "{{替代方案放大图路径}}",
}


def data_uri(png_path: pathlib.Path) -> str:
    return "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode("ascii")


def locate_assets(folder: pathlib.Path):
    chart = folder / "图表"
    images = {}
    for key, filename in IMAGE_KEYS:
        p = chart / filename
        if not p.is_file():
            raise SystemExit(f"[错误] 缺少图表文件：{p}")
        images[key] = p
    mds = sorted(folder.glob("分析报告_*.md"))
    htmls = sorted(folder.glob("网页报告_*.html"))
    if len(mds) != 1:
        raise SystemExit(f"[错误] 需恰好 1 份分析报告 .md，实际 {len(mds)} 份：{folder}")
    if len(htmls) != 1:
        raise SystemExit(f"[错误] 需恰好 1 份网页报告 .html，实际 {len(htmls)} 份：{folder}")
    return images, mds[0], htmls[0]


def embed_md(md_path: pathlib.Path, images, keep_absolute: bool):
    text = md_path.read_text(encoding="utf-8")
    for key, filename in IMAGE_KEYS:
        pat = re.compile(r"(!\[[^\]]*\]\()([^)]*" + re.escape(filename) + r")(\))")
        if keep_absolute:
            # 校验原引用为绝对路径；保留原样
            for m in pat.finditer(text):
                p = m.group(2)
                if not (p.startswith("/") or re.match(r"^[A-Za-z]:[/\\]", p)):
                    raise SystemExit(f"[错误] 回退模式下图片引用必须是绝对路径：{p}")
        else:
            uri = data_uri(images[key])
            text = pat.sub(lambda m, u=uri: m.group(1) + u + m.group(3), text)
    if keep_absolute:
        note = "\n\n> 注：本报告图片使用绝对路径引用（当前查看器不支持 data URI 图片时的回退模式）；图片目录保留在 `图表/`。\n"
        if "回退模式" not in text:
            text += note
    md_path.write_text(text, encoding="utf-8", newline="")


def embed_html(html_path: pathlib.Path, images):
    text = html_path.read_text(encoding="utf-8")
    for key, token in HTML_TOKENS.items():
        uri = data_uri(images[key])
        # 1) src="{{token}}" 注入 data URI
        text = re.sub(r'src="' + re.escape(token) + r'"', 'src="' + uri + '"', text)
        # 2) 其余出现处（如图片缺失提示）替换为相对文件名，避免大段 base64 文本
        text = text.replace(token, images[key].name)
    html_path.write_text(text, encoding="utf-8", newline="")


def validate(md_text: str, html_text: str, images, keep_absolute: bool):
    expected = len(images)  # 标准模板为 4
    html_imgs = len(re.findall(r'<img class="pano-img"', html_text))
    html_uris = html_text.count("data:image/png;base64,")
    if html_uris != html_imgs:
        raise SystemExit(
            f"[校验失败] html 内嵌图 {html_uris} 张 ≠ <img> 数量 {html_imgs} 张"
        )
    if html_imgs != expected:
        print(f"[警告] 模板 <img> 数量 {html_imgs} 与标准 4 张不一致（单方案防御模式？），按实际数量校验。")
    for token in HTML_TOKENS.values():
        if token in html_text:
            raise SystemExit(f"[校验失败] html 仍含未替换占位符：{token}")

    md_links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_text)
    md_png = [m for m in md_links if m.startswith("data:image/png;base64,") or m.endswith(".png")]
    if len(md_png) != expected:
        raise SystemExit(f"[校验失败] md 图片标记 {len(md_png)} 个 ≠ 预期 {expected} 个")
    if keep_absolute:
        for m in md_png:
            if not (m.startswith("/") or re.match(r"^[A-Za-z]:[/\\]", m)):
                raise SystemExit(f"[校验失败] 回退模式下 md 图片引用非绝对路径：{m}")
    else:
        if any(not m.startswith("data:image/png;base64,") for m in md_png):
            raise SystemExit("[校验失败] md 中仍有未内嵌的 PNG 引用")


def main():
    ap = argparse.ArgumentParser(description="把浪型图 PNG 内嵌为 base64，输出自包含的 md/html 交付文档")
    ap.add_argument("folder", help="分析输出文件夹（含 图表/、分析报告_*.md、网页报告_*.html）")
    ap.add_argument("--md-keep-absolute", action="store_true",
                    help="md 回退为绝对路径引用（查看器不支持 data URI 时使用），html 仍强制内嵌 base64")
    args = ap.parse_args()

    folder = pathlib.Path(args.folder)
    if not folder.is_dir():
        raise SystemExit(f"[错误] 文件夹不存在：{folder}")
    images, md_path, html_path = locate_assets(folder)

    embed_md(md_path, images, args.md_keep_absolute)
    embed_html(html_path, images)

    md_text = md_path.read_text(encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8")
    validate(md_text, html_text, images, args.md_keep_absolute)

    mode = "md=绝对路径回退 / html=base64" if args.md_keep_absolute else "md+html 均 base64"
    print(f"[完成] 已内嵌 {len(images)} 张图（{mode}）：")
    print(f"  md  : {md_path}")
    print(f"  html: {html_path}")


if __name__ == "__main__":
    main()
