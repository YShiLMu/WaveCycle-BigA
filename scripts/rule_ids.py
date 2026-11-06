# -*- coding: utf-8 -*-
"""规则编号统一解析 —— 2 代公理编号（R-IMP-07）的唯一正则出处。

新输出、文档、报告与脚本提示一律只使用 2 代编号（R-IMP/R-DIA/R-ZZ…）。
本模块保留 1 代数字编号（R5/R6/R7）的解析能力，唯一用途是读取已归档的 1 代历史报告，
供 `invalidation_check.py --from-report` 与 `extract_report_state.py` 恢复旧状态；
不得在新报告或任何面向用户的文案中输出旧编号。

可推导数值边界的规则（两侧含义一致）：
    R-IMP-07  第 2 浪不得越过第 1 浪起点（100% 回撤上限）
    R-IMP-08  第 3 浪必须突破第 1 浪终点
    R-IMP-09  第 3 浪不得是 1/3/5 中最短
    R-IMP-10  第 4 浪不得进入第 1 浪价格区域
失败浪（Truncation）不是 2 代硬公理，按"结构失效"登记，不得以规则失效冒充。
"""

import re

RULE_ID_PATTERN = re.compile(r"R-(?:[A-Z]{2,4})-\d{1,2}|\bR\d{1,2}\b")

# 能推出硬价位（比较符可复算）的规则编号：2 代编号 + 历史归档读取兼容写法。
DERIVABLE_RULES = frozenset({"R-IMP-07", "R-IMP-08", "R-IMP-09", "R-IMP-10",
                             "R5", "R6", "R7"})

# 「触及即失效」的规则：浪 4 与浪 1 重叠含等号边界（其余按越过判定，不含等号）。
TOUCH_COUNTS_RULES = frozenset({"R-IMP-10", "R7"})


def rule_ids(text):
    """抽取文本中出现的全部规则编号（2 代编号 + 历史归档兼容写法）。"""
    return set(RULE_ID_PATTERN.findall(str(text)))


def has_derivable_rule(text):
    """该依据是否引用了可推出数值边界的规则。"""
    return bool(rule_ids(text) & DERIVABLE_RULES)


def touch_counts(text):
    """该依据是否属于「触及即失效」的规则（含等号边界）。"""
    return bool(rule_ids(text) & TOUCH_COUNTS_RULES)


def normalize(text):
    """把历史归档中的 1 代数字编号替换为 2 代等价编号，供展示层统一。"""
    return re.sub(r"\bR5\b", "R-IMP-07/08", re.sub(r"\bR6\b", "R-IMP-09",
                  re.sub(r"\bR7\b", "R-IMP-10", str(text))))
