# -*- coding: utf-8 -*-
"""print_subagent_brief.py —— 输出子代理契约包全文到 stdout（P1-5）。

用法
----
    python scripts/print_subagent_brief.py

用途
----
主 agent 派发第3／4层细分子代理时，用本脚本取契约包全文，**逐字拼接**进派发提示词
（减少"读了再摘抄改写"的漂移）；子代理零额外规则文件读取，
可读取任务白名单明确指定的数据、图表和任务包，不自行遍历项目或答案。见
`references/workflow.md` 第 2 步 2.4b 的「子 agent 数浪契约」。

契约包由 `build_package.py` 拼装生成（固定头尾取 20 子代理契约头尾源，
第 2 块从 02 数浪 `SUBAGENT-BRIEF` 锚点区只复制不移动抽取）；本脚本只读取输出。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRIEF = os.path.join(os.path.dirname(HERE), "references", "subagent_brief.md")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not os.path.exists(BRIEF):
        raise SystemExit("[错误] 契约包不存在：%s（先跑 build_package.py --apply）" % BRIEF)
    with open(BRIEF, encoding="utf-8") as f:
        sys.stdout.write(f.read())


if __name__ == "__main__":
    main()
