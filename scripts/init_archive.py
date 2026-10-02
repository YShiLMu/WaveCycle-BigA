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
    由模型显式指定 --existing-dir 指向既有目录并用 --force 才允许复用）。
"""
import argparse
import datetime
import os
import re
import sys

from naming import IMAGE_FILENAMES, doc_names, validate_component


def main(argv=None):
    p = argparse.ArgumentParser(
        description="创建分析输出归档文件夹（命名规范唯一权威）")
    p.add_argument("--name", required=True, help="标的名称（如 饮料制造）")
    p.add_argument("--code", required=True, help="标的代码（如 881133）")
    target = p.add_mutually_exclusive_group()
    target.add_argument("--root", default=None, help="新建归档的父目录（默认 ./分析输出），不能传既有归档目录")
    target.add_argument("--existing-dir", help="复用既有归档绝对路径；须 --force，核对名称/代码/时间戳")
    p.add_argument("--time", default=None,
                   help="时间戳 YYYYMMDD_HHMM（默认当前本地时间；更新写回场景配合 --force 使用）")
    p.add_argument("--force", action="store_true",
                   help="目标文件夹已存在时不报错（更新数浪写回原文件夹场景）")
    p.add_argument("--print-dir", action="store_true",
                   help="只打印归档文件夹绝对路径（单行，便于 shell $(...) 捕获）；仍执行创建")
    p.add_argument("--print-stamp", action="store_true",
                   help="只打印时间戳 YYYYMMDD_HHMM（单一来源：供 data.json/文件名与文件夹名保持一致）")
    args = p.parse_args(argv)

    name = validate_component(args.name, "标的名称")
    code = validate_component(args.code, "标的代码")
    if args.existing_dir:
        if not args.force:
            p.error("--existing-dir 必须配合 --force 明确复用")
        if not os.path.isabs(args.existing_dir):
            p.error("--existing-dir 必须为绝对路径")
        folder = os.path.abspath(args.existing_dir)
        if not os.path.isdir(folder):
            p.error("--existing-dir 必须是已存在的归档目录")
        prefix = "%s_%s_" % (name, code)
        basename = os.path.basename(folder)
        if not basename.startswith(prefix):
            p.error("既有归档目录名称与 --name / --code 不一致")
        folder_stamp = basename[len(prefix):]
        if args.time and args.time != folder_stamp:
            p.error("--time 与既有归档目录时间戳不一致")
        stamp = folder_stamp
    else:
        stamp = args.time or datetime.datetime.now().strftime("%Y%m%d_%H%M")
    if not re.fullmatch(r"\d{8}_\d{4}", stamp):
        raise SystemExit("[错误] --time 格式应为 YYYYMMDD_HHMM，收到: %s" % stamp)
    try:
        datetime.datetime.strptime(stamp, "%Y%m%d_%H%M")
    except ValueError:
        p.error("归档时间戳不是有效本地日期时间")

    if not args.existing_dir:
        root = args.root or "分析输出"
        # 旧误用 --root 指向归档会造成再嵌套一层，显式阻断。
        if re.search(r"_\d{8}_\d{4}$", os.path.basename(os.path.normpath(root))):
            p.error("--root 应为归档父目录；复用已有归档请用 --existing-dir --force")
        folder = os.path.join(root, "%s_%s_%s" % (name, code, stamp))
    if os.path.exists(folder) and not args.force and not args.existing_dir:
        raise SystemExit("[错误] 归档文件夹已存在（更新写回请加 --force 并确认是同一标的）: %s" % folder)
    os.makedirs(os.path.join(folder, "图表"), exist_ok=True)

    if args.print_stamp:
        print(stamp)
        return 0
    if args.print_dir:
        print(os.path.abspath(folder))
        return 0

    print("[OK] 归档文件夹: %s" % os.path.abspath(folder))
    print("     图表目录: %s" % os.path.abspath(os.path.join(folder, "图表")))
    print("     交付文档（标准命名，禁止改动）：")
    for doc in doc_names(name, code, stamp):
        print("       - " + os.path.join(folder, doc))
    print("     浪型图命名（embed_report_images.py 权威）：")
    print("       " + " / ".join(IMAGE_FILENAMES))
    print("     生成交付文档后运行：")
    print("       python embed_report_images.py \"%s\"" % os.path.abspath(folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
