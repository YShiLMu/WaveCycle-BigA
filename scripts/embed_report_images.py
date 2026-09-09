#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_report_images.py — 把浪型图 PNG 内嵌进分析报告 .md 与网页报告 .html。

用法:
    python embed_report_images.py <分析输出文件夹> [--md-keep-absolute]

流程:
    1. 定位 图表/ 下 PNG：标准模式 2 张（主方案全景 + 替代方案全景，见 naming.IMAGE_KEYS/CHART_VIEWS 单一出处）；
       单方案防御模式 1 张（仅主方案全景，替代方案缺失时其图区标记"不适用"），
       只缺一张判错退出）;
    2. 定位 分析报告_*.md 与 网页报告_*.html;
    3. md：把 ![说明](...主方案_全景.png) 等图片链接替换为 base64 data URI
       （--md-keep-absolute 时保留绝对路径并在文末注明回退原因）;
    4. html：把 {{主方案全景图路径}} 等 2 个占位符替换为 base64 data URI；
       单方案防御模式时，替代方案图区 <img> 删除、提示改为"不适用";
    5. 校验：html 内 data:image/png;base64, 数量 == <img class="pano-img"> 数量
       == 实际图片数（2 或 1）；md 图片标记数量 == 实际图片数；html 必须保留模板
       头部特征注释（"波浪理论网页报告模板"）；任一不通过则以退出码 1 结束，
       禁止交付缺图文件。

本脚本不删除 图表/ 目录：PNG 原图与内嵌后的两个交付文档一同永久归档。
"""

import argparse
import base64
import pathlib
import re
import sys
import io
from PIL import Image

from naming import HTML_TOKENS, IMAGE_KEYS


def verify_png(payload):
    """同时验证 PNG 格式、校验块和像素解码，拒绝伪造前缀。"""
    try:
        with Image.open(io.BytesIO(payload)) as img:
            if img.format != "PNG":
                raise ValueError("图片不是 PNG")
            img.verify()
        with Image.open(io.BytesIO(payload)) as img:
            img.load()
    except Exception as exc:
        raise SystemExit("[校验失败] PNG 无法完整解码：%s" % exc)


def data_uri(png_path: pathlib.Path) -> str:
    payload = png_path.read_bytes()
    verify_png(payload)
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def locate_assets(folder: pathlib.Path):
    chart = folder / "图表"
    images = {}
    for key, filename in IMAGE_KEYS:
        p = chart / filename
        if p.is_file():
            images[key] = p
    # 主方案全景必备；替代方案全景可选（有 = 标准 2 张；无 = 单方案防御 1 张）
    for key, filename in IMAGE_KEYS:
        if key not in images and key == "主方案全景":
            raise SystemExit(f"[错误] 缺少主方案全景图：{chart / filename}")
    mds = sorted(folder.glob("分析报告_*.md"))
    htmls = sorted(folder.glob("网页报告_*.html"))
    if len(mds) != 1:
        raise SystemExit(f"[错误] 需恰好 1 份分析报告 .md，实际 {len(mds)} 份：{folder}")
    if len(htmls) != 1:
        raise SystemExit(f"[错误] 需恰好 1 份网页报告 .html，实际 {len(htmls)} 份：{folder}")
    return images, mds[0], htmls[0]


def embed_md(md_path: pathlib.Path, images, keep_absolute: bool, write=True):
    text = md_path.read_text(encoding="utf-8")
    for key, filename in IMAGE_KEYS:
        pat = re.compile(r"(!\[[^\]]*\]\()([^)]*" + re.escape(filename) + r")(\))")
        if key not in images:
            continue  # 单方案防御模式：替代方案图在 md 中无引用，跳过
        if keep_absolute:
            target = images[key].resolve().as_posix()
        else:
            target = data_uri(images[key])
        text = pat.sub(lambda m: m.group(1) + target + m.group(3), text)
        # 标准图名也可定位已经内嵌的引用，支持再次内嵌与绝对路径回退。
        named = re.compile(r"(!\[" + re.escape(key) + r"\]\()([^)]*)(\))")
        text = named.sub(lambda m: m.group(1) + target + m.group(3), text)
    if keep_absolute:
        note = "\n\n> 注：本报告图片使用绝对路径引用（当前查看器不支持 data URI 图片时的回退模式）；图片目录保留在 `图表/`。\n"
        if "回退模式" not in text:
            text += note
    if write:
        md_path.write_text(text, encoding="utf-8", newline="")
    return text


def embed_html(html_path: pathlib.Path, images, write=True):
    text = html_path.read_text(encoding="utf-8")
    for key, token in HTML_TOKENS.items():
        if key in images:
            uri = data_uri(images[key])
            # 1) src="{{token}}" 注入 data URI
            text = re.sub(r'src="' + re.escape(token) + r'"', 'src="' + uri + '"', text)
            # 2) 其余出现处（如图片缺失提示）替换为相对文件名，避免大段 base64 文本
            text = text.replace(token, images[key].name)
        else:
            # 单方案防御模式：删除缺失图的 <img> 标签（跨行，含 onerror），
            # 图片缺失提示改为"不适用"。[^<]* 保证不跨过其他 <img> 标签
            img_pat = re.compile(r'<img class="pano-img"[^<]*src="' + re.escape(token) + r'"[^<]*>',
                                 re.DOTALL)
            text = img_pat.sub("", text)
            miss_pat = re.compile(r'<div class="img-missing">[^<]*' + re.escape(token) + r'[^<]*</div>')
            text = miss_pat.sub(
                '<div class="img-missing">（单方案防御模式：替代方案未出图，不适用）</div>', text)
            text = text.replace(token, "（无图）")
    if write:
        html_path.write_text(text, encoding="utf-8", newline="")
    return text


def validate(md_text: str, html_text: str, images, keep_absolute: bool):
    import report_common as rc  # 锚点校验函数单一出处；局部导入避免与命名工具循环依赖
    rc.check_invalidation_anchor(md_text, "分析报告.md")
    rc.check_invalidation_anchor(html_text, "网页报告.html")
    has_state = "REPORT-STATE-" in md_text or "REPORT-STATE-" in html_text
    if has_state:
        try:
            md_state, html_state = rc.extract_state(md_text), rc.extract_state(html_text)
        except (ValueError, UnicodeError) as exc:
            raise SystemExit("[校验失败] 报告状态错误：%s" % exc)
        if md_state != html_state:
            raise SystemExit("[校验失败] 两份报告结构化状态不一致")
        rc.validate(md_state)
        expected_count = 1 if md_state["报告模式"] == "单方案防御" else 2
        if len(images) != expected_count:
            raise SystemExit("[校验失败] 实际图片数与声明的报告模式不一致")
    for label, text in (("md", md_text), ("html", html_text)):
        for encoded in re.findall(r"data:image/png;base64,([^\"')\s<>]*)", text):
            try:
                payload = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise SystemExit("[校验失败] %s 图片编码无效：%s" % (label, exc))
            verify_png(payload)
    if keep_absolute:
        for path in images.values():
            verify_png(path.read_bytes())
    expected = len(images)  # 标准模式 2 张；单方案防御模式 1 张（见 naming.IMAGE_KEYS）
    html_imgs = len(re.findall(r'<img class="pano-img"', html_text))
    html_uris = html_text.count("data:image/png;base64,")
    if "波浪理论网页报告模板" not in html_text:
        raise SystemExit("[校验失败] html 缺少模板头部特征注释（\"波浪理论网页报告模板\"），疑似非模板生成")
    if html_uris != html_imgs:
        raise SystemExit(
            f"[校验失败] html 内嵌图 {html_uris} 张 ≠ <img> 数量 {html_imgs} 张"
        )
    if html_imgs != expected:
        raise SystemExit(
            f"[校验失败] html <img> 数量 {html_imgs} ≠ 实际图表 {expected} 张"
            f"（标准模式 2 张；单方案防御模式 1 张且替代方案图区应标记不适用）")
    for token in HTML_TOKENS.values():
        if token in html_text:
            raise SystemExit(f"[校验失败] html 仍含未替换占位符：{token}")

    md_links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_text)
    md_png = [m for m in md_links if m.startswith("data:image/png;base64,") or m.endswith(".png")]
    if len(md_png) != expected:
        raise SystemExit(f"[校验失败] md 图片标记 {len(md_png)} 个 ≠ 实际图表 {expected} 张")
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

    md_text = embed_md(md_path, images, args.md_keep_absolute, write=False)
    html_text = embed_html(html_path, images, write=False)
    validate(md_text, html_text, images, args.md_keep_absolute)
    md_path.write_text(md_text, encoding="utf-8", newline="")
    html_path.write_text(html_text, encoding="utf-8", newline="")

    mode = "md=绝对路径回退 / html=base64" if args.md_keep_absolute else "md+html 均 base64"
    print(f"[完成] 已内嵌 {len(images)} 张图（{mode}）：")
    print(f"  md  : {md_path}")
    print(f"  html: {html_path}")
    print(f"[保留] 图表目录不删除，PNG 原图随归档永久保留：{folder / '图表'}")


if __name__ == "__main__":
    main()
