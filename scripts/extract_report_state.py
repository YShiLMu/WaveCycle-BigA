#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""恢复内嵌报告状态，或提取不含图片数据的正文供语义复核。"""
import argparse
import json
from pathlib import Path
import re
import sys
import report_common as rc


def plain_text(text):
    text = re.sub(rc.STATE_PATTERN, "", text)
    return re.sub(r"data:image/[^;,\s]+;base64,[A-Za-z0-9+/=\r\n]+", "[图片数据已省略]", text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="分析报告或网页报告路径")
    parser.add_argument("--text", action="store_true", help="输出去掉图片与状态编码的正文")
    parser.add_argument("--validate-current", action="store_true", help="按当前正式报告规范严格校验；旧状态默认仅检查编码、JSON 与容器类型")
    args = parser.parse_args()
    if args.text and args.validate_current:
        parser.error("--text 与 --validate-current 不能同时使用")
    text = Path(args.report).read_text(encoding="utf-8-sig")
    if args.text:
        print(plain_text(text))
    else:
        try:
            state = rc.extract_state(text)
            if args.validate_current:
                rc.validate(state)
        except (ValueError, UnicodeError) as exc:
            parser.error(str(exc))
        print(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
