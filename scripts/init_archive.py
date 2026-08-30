# -*- coding: utf-8 -*-
"""分析输出归档初始化——归档文件夹命名与交付文档命名的唯一权威。

把归档规范（SKILL.md「输出归档」）编码成工具：一次命令创建
  <root>/<标的名称>_<代码>_<YYYYMMDD>_<HHMM>/
  └── 图表/
并打印两个交付文档的标准文件名，禁止再手工命名。

用法：
  python init_archive.py --name 饮料制造 --code 881133
  python init_archive.py --name 饮料制造 --code 881133 --root "C:/x/分析输出" --time 20260830_0924
  python init_archive.py --name 饮料制造 --code 881133 --print-dir
  # --print-dir：只打印归档文件夹绝对路径（单行，便于 shell $(...) 捕获后拼接重定向目标）；
  #   省略时输出多行人读说明（含图表目录、标准文件名与后续命令提示）

说明：
  - 默认 root = 当前工作目录下 ./分析输出（项目根目录运行即落在项目归档区）；
  - --time 省略时取当前本地时间；Windows 文件夹名禁止 \\ / : * ? " < > |，
    时间一律 4 位（0924），脚本对名称/代码做非法字符校验；
  - 幂等：文件夹已存在时报错退出（避免误写进旧文件夹；更新数浪应写回原文件夹，
    由模型显式指定 --root 指向既有目录并用 --force 才允许复用）。
"""
import argparse
import datetime
import os
import re
import sys

BAD_CHARS = r'\\/:*?"<>|'
DOCS = ("分析报告_%s_%s_%s.md", "网页报告_%s_%s_%s.html")


def validate_component(value, label):
    if not value:
        raise SystemExit("[错误] %s 不能为空" % label)
    bad = [ch for ch in value if ch in BAD_CHARS]
    if bad:
        raise SystemExit("[错误] %s 含 Windows 非法字符: %r" % (label, "".join(set(bad))))
    if re.search(r"\s", value):
        raise SystemExit("[错误] %s 不应含空格: %r" % (label, value))
    return value


def main():
    p = argparse.ArgumentParser(
        description="创建分析输出归档文件夹（命名规范唯一权威）")
    p.add_argument("--name", required=True, help="标的名称（如 饮料制造）")
    p.add_argument("--code", required=True, help="标的代码（如 881133）")
    p.add_argument("--root", default="分析输出", help="归档根目录（默认 ./分析输出）")
    p.add_argument("--time", default=None,
                   help="时间戳 YYYYMMDD_HHMM（默认当前本地时间；更新写回场景配合 --force 使用）")
    p.add_argument("--force", action="store_true",
                   help="目标文件夹已存在时不报错（更新数浪写回原文件夹场景）")
    p.add_argument("--print-dir", action="store_true",
                   help="只打印归档文件夹绝对路径（单行，便于 shell $(...) 捕获）；仍执行创建")
    args = p.parse_args()

    name = validate_component(args.name, "标的名称")
    code = validate_component(args.code, "标的代码")
    stamp = args.time or datetime.datetime.now().strftime("%Y%m%d_%H%M")
    if not re.fullmatch(r"\d{8}_\d{4}", stamp):
        raise SystemExit("[错误] --time 格式应为 YYYYMMDD_HHMM，收到: %s" % stamp)

    folder = os.path.join(args.root, "%s_%s_%s" % (name, code, stamp))
    if os.path.exists(folder) and not args.force:
        raise SystemExit("[错误] 归档文件夹已存在（更新写回请加 --force 并确认是同一标的）: %s" % folder)
    os.makedirs(os.path.join(folder, "图表"), exist_ok=True)

    if args.print_dir:
        print(os.path.abspath(folder))
        return 0

    print("[OK] 归档文件夹: %s" % os.path.abspath(folder))
    print("     图表目录: %s" % os.path.abspath(os.path.join(folder, "图表")))
    print("     交付文档（标准命名，禁止改动）：")
    for tpl in DOCS:
        print("       - " + os.path.join(folder, tpl % (name, code, stamp)))
    print("     浪型图命名（embed_report_images.py 权威）：")
    print("       主方案_全景.png / 主方案_放大.png / 替代方案_全景.png / 替代方案_放大.png")
    print("     生成交付文档后运行：")
    print("       python embed_report_images.py \"%s\"" % os.path.abspath(folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
