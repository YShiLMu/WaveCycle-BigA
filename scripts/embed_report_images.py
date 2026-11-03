#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_report_images.py — 把浪型图 PNG 内嵌进分析报告 .md 与网页报告 .html。

用法:
    python embed_report_images.py <分析输出文件夹> [--md-keep-absolute]

流程:
    1. 定位 图表/ 下 PNG（命名权威 naming.IMAGE_KEYS）：
       - 日线全景为核心图：标准模式 2 张；单方案防御模式 1 张（仅主方案全景，
         替代方案 4 个图位标记"不适用"）；
       - 分钟分形层图（60m/30m/15m）成组可选：启用分钟分形层时标准模式 6 张、
         单方案防御模式 3 张（仅主方案）；未启用时对应图位标记"未启用分钟分形层"；
       - 分钟图组只允许 ∅ / 主方案 3 张 / 全部 6 张三种形态，缺张判错退出；
    2. 定位 分析报告_*.md 与 网页报告_*.html;
    3. md：把 ![说明](...主方案_全景.png) 等图片链接替换为 base64 data URI
       （--md-keep-absolute 时保留绝对路径并在文末注明回退原因）;
    4. html：把 {{主方案全景图路径}} 等 8 个占位符替换为 base64 data URI；
       缺图图位的 <img> 替换为对应降级说明（不适用 / 未启用分钟分形层）;
    5. 校验：html 内 data:image/png;base64, 数量 == <img class="pano-img"> 数量
       == 实际图片数；md 图片标记数量 == 实际图片数；html 必须保留模板
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
import hashlib
from html.parser import HTMLParser
from PIL import Image

from naming import HTML_TOKENS, IMAGE_KEYS, MINUTE_IMAGE_KEYS

MINUTE_KEYS = {key for key, _fn in MINUTE_IMAGE_KEYS}
MAIN_MINUTE_KEYS = {key for key in MINUTE_KEYS if key.startswith("主方案")}


def missing_note(key, images):
    """缺图图位的降级说明：单方案防御（替代全景缺失）时替代 4 图位标"不适用"，
    其余分钟图位标"未启用分钟分形层"。"""
    if key.startswith("替代方案") and "替代方案全景" not in images:
        return "（单方案防御模式：替代方案未出图，不适用）"
    return "（未启用分钟分形层：本图位由分钟分形层分析出图后注入）"

IMG_PATTERN = re.compile(r'''<img\b(?:[^>"']|"[^"]*"|'[^']*')*>''', re.IGNORECASE)
MD_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
SRC_PATTERN = re.compile(r'''(?<![\w:-])src\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''', re.IGNORECASE)


class ImageAttributes(HTMLParser):
    def __init__(self, tag):
        super().__init__()
        self.attributes = {}
        self.feed(tag)

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            keys = [key for key, _value in attrs]
            if len(keys) != len(set(keys)):
                raise SystemExit("[校验失败] 图片标签含重复属性")
            self.attributes = dict(attrs)


def image_key(label="", source="", scheme=""):
    """按稳定方案标识或旧版 alt/文件名定位，冲突与无标识不猜测。"""
    candidates = set()
    for key, filename in IMAGE_KEYS:
        if scheme in (key, key.replace("全景", "")) or label in (key, key + "图"):
            candidates.add(key)
        if source == HTML_TOKENS[key] or source.replace("\\", "/").split("/")[-1] == filename:
            candidates.add(key)
    if len(candidates) > 1:
        raise SystemExit("[校验失败] 图片方案标识相互冲突")
    return next(iter(candidates), None)


def pano_images(text):
    """取得所有全景图的标签、方案与来源，属性顺序不影响识别。"""
    result = []
    for match in IMG_PATTERN.finditer(text):
        attributes = ImageAttributes(match.group()).attributes
        if "pano-img" not in (attributes.get("class") or "").split():
            continue
        key = image_key(attributes.get("alt") or "", attributes.get("src") or "",
                        attributes.get("data-scheme") or "")
        if key is None:
            raise SystemExit("[校验失败] 全景图缺少明确方案标识，无法安全重嵌")
        result.append((match, key, attributes))
    return result


def md_images(text):
    result = []
    for match in MD_IMAGE_PATTERN.finditer(text):
        label, source = match.groups()
        if not (source.startswith("data:image/png;base64,") or source.lower().endswith(".png")):
            continue
        key = image_key(label, source)
        if key is None:
            raise SystemExit("[校验失败] Markdown 图片缺少明确方案标识，无法安全重嵌")
        result.append((match, key, source))
    return result


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
    # 分钟分形层图成组规则：只允许 ∅ / 主方案 3 张（单方案防御）/ 全部 6 张
    minute_found = {key for key in images if key in MINUTE_KEYS}
    legal_groups = (set(), MAIN_MINUTE_KEYS, MINUTE_KEYS)
    if minute_found not in legal_groups:
        raise SystemExit("[错误] 分钟分形层图必须成组出图（主/替代各 60m+30m+15m），"
                         "当前不齐：%s" % sorted(minute_found))
    if "替代方案全景" in images and minute_found == MAIN_MINUTE_KEYS:
        raise SystemExit("[错误] 替代方案全景存在但缺替代方案分钟图——分钟图组应为全部 6 张")
    mds = sorted(folder.glob("分析报告_*.md"))
    htmls = sorted(folder.glob("网页报告_*.html"))
    if len(mds) != 1:
        raise SystemExit(f"[错误] 需恰好 1 份分析报告 .md，实际 {len(mds)} 份：{folder}")
    if len(htmls) != 1:
        raise SystemExit(f"[错误] 需恰好 1 份网页报告 .html，实际 {len(htmls)} 份：{folder}")
    return images, mds[0], htmls[0]


def embed_md(md_path: pathlib.Path, images, keep_absolute: bool, write=True):
    text = md_path.read_text(encoding="utf-8")
    found = md_images(text)
    for match, key, _source in reversed(found):
        if key not in images:
            replacement = missing_note(key, images)
        else:
            target = images[key].resolve().as_posix() if keep_absolute else data_uri(images[key])
            replacement = "![%s](%s)" % (key, target)
        text = text[:match.start()] + replacement + text[match.end():]
    note = "\n\n> 注：本报告图片使用绝对路径引用（当前查看器不支持 data URI 图片时的回退模式）；图片目录保留在 `图表/`。\n"
    if keep_absolute:
        if note not in text:
            text += note
    else:
        text = text.replace(note, "")
    if write:
        md_path.write_text(text, encoding="utf-8", newline="")
    return text


def embed_html(html_path: pathlib.Path, images, write=True):
    text = html_path.read_text(encoding="utf-8")
    for match, key, attributes in reversed(pano_images(text)):
        if key not in images:
            replacement = ('<p class="img-note" data-scheme-unavailable="%s">%s</p>'
                           % (key, missing_note(key, images)))
        else:
            if "src" not in attributes:
                raise SystemExit("[校验失败] 全景图缺少 src 属性")
            replacement = SRC_PATTERN.sub(lambda _match: 'src="' + data_uri(images[key]) + '"', match.group(), count=1)
            if "data-scheme" not in attributes:
                replacement = re.sub(r"\s*/?>$", ' data-scheme="' + key.replace("全景", "") + '">', replacement)
        text = text[:match.start()] + replacement + text[match.end():]
    for key, token in HTML_TOKENS.items():
        if key in images:
            # 提示中的路径使用文件名，图片 src 已按稳定方案标识统一替换。
            text = text.replace(token, images[key].name)
        else:
            miss_pat = re.compile(r'<div class="img-missing">[^<]*' + re.escape(token) + r'[^<]*</div>')
            text = miss_pat.sub('<div class="img-missing">%s</div>' % missing_note(key, images), text)
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
        state_defense = md_state["报告模式"] == "单方案防御"
        if state_defense != ("替代方案全景" not in images):
            raise SystemExit("[校验失败] 实际图片数与声明的报告模式不一致")
        minute_expected = 0 if not (set(images) & MINUTE_KEYS) else (3 if state_defense else 6)
        expected_count = (1 if state_defense else 2) + minute_expected
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
    expected = len(images)  # 标准 2 / 防御 1（日线核心）+ 分钟组 0/3/6（见 naming.IMAGE_KEYS）
    html_records = pano_images(html_text)
    html_imgs = len(html_records)
    html_uris = html_text.count("data:image/png;base64,")
    if "波浪理论网页报告模板" not in html_text:
        raise SystemExit("[校验失败] html 缺少模板头部特征注释（\"波浪理论网页报告模板\"），疑似非模板生成")
    if html_uris != html_imgs:
        raise SystemExit(
            f"[校验失败] html 内嵌图 {html_uris} 张 ≠ <img> 数量 {html_imgs} 张"
        )
    if html_imgs != expected:
        raise SystemExit(
            f"[校验失败] html <img> 数量 {html_imgs} 张 ≠ 实际图表 {expected} 张"
            f"（日线核心：标准 2 / 单方案防御 1；分钟图组 0/3/6，缺图图位应有降级说明）")
    for token in HTML_TOKENS.values():
        if token in html_text:
            raise SystemExit(f"[校验失败] html 仍含未替换占位符：{token}")

    md_records = md_images(md_text)
    md_png = [source for _match, _key, source in md_records]
    if len(md_png) != expected:
        raise SystemExit(f"[校验失败] md 图片标记 {len(md_png)} 个 ≠ 实际图表 {expected} 张")
    if keep_absolute:
        for m in md_png:
            if not (m.startswith("/") or re.match(r"^[A-Za-z]:[/\\]", m)):
                raise SystemExit(f"[校验失败] 回退模式下 md 图片引用非绝对路径：{m}")
    else:
        if any(not m.startswith("data:image/png;base64,") for m in md_png):
            raise SystemExit("[校验失败] md 中仍有未内嵌的 PNG 引用")

    # 逐方案核对原图和两份文档，而不是只核对张数和 PNG 是否能解码。
    for key, path in images.items():
        md_sources = [source for _match, found_key, source in md_records if found_key == key]
        html_sources = [attrs.get("src", "") for _match, found_key, attrs in html_records if found_key == key]
        if len(md_sources) != 1 or len(html_sources) != 1:
            raise SystemExit("[校验失败] %s 在每份文档中须恰有一张图" % key)
        payload = path.read_bytes()
        verify_png(payload)
        original_hash = hashlib.sha256(payload).digest()
        for label, source in (("md", md_sources[0]), ("html", html_sources[0])):
            if label == "md" and keep_absolute:
                if pathlib.Path(source).resolve() != path.resolve():
                    raise SystemExit("[校验失败] %s 回退路径不是当前方案原图" % key)
                embedded_payload = pathlib.Path(source).read_bytes()
            else:
                if not source.startswith("data:image/png;base64,"):
                    raise SystemExit("[校验失败] %s 的 %s 图片未内嵌" % (label, key))
                try:
                    embedded_payload = base64.b64decode(source.split(",", 1)[1], validate=True)
                except ValueError as exc:
                    raise SystemExit("[校验失败] %s 图片编码无效：%s" % (label, exc))
            if hashlib.sha256(embedded_payload).digest() != original_hash:
                raise SystemExit("[校验失败] %s 的 %s 图片与当前 PNG 原图不一致" % (label, key))
    if "替代方案全景" not in images:
        notices = re.findall(r'''<(?:p\b[^>]*data-scheme-unavailable=["']替代方案[^"']*["'][^>]*|div class="img-missing")>([^<]*)</(?:p|div)>''', html_text)
        if not any("替代方案" in notice and "不适用" in notice for notice in notices):
            raise SystemExit("[校验失败] 单方案防御网页须在替代方案图区明确标记不适用")
    # 分钟图位降级说明逐位核对：缺图的分钟图位（非防御缺图）各应有一条说明
    # （按说明段落特征前缀计数，排除模板/CSS/JS 注释里的同名文字）
    missing_minute_notes = [key for key in MINUTE_KEYS if key not in images
                            and not (key.startswith("替代方案") and "替代方案全景" not in images)]
    note_count = len(re.findall(r'<p class="img-note"[^>]*>（未启用分钟分形层', html_text))
    if note_count != len(missing_minute_notes):
        raise SystemExit("[校验失败] 「未启用分钟分形层」说明 %d 条 ≠ 缺图分钟图位 %d 个"
                         % (note_count, len(missing_minute_notes)))


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
