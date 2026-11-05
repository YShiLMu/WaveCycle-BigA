# -*- coding: utf-8 -*-
"""规则编号统一解析 —— 2 代公理编号（R-IMP-07）与 1 代数字编号（R5）并存时的唯一出处。

报告校验（report_common）与失效追踪（invalidation_check）都依赖"这条失效依据是不是
由可复算的数值边界推出的"。2 代公理体系统一用 R-IMP/R-DIA/R-ZZ… 编号，1 代旧报告与
旧脚本文案用 R5/R6/R7；两种写法必须在同一处归一，避免各脚本各写一套正则。

等价的数值边界规则（两侧含义一致）：
    R-IMP-07 ↔ R5   第 2 浪不得越过第 1 浪起点（100% 回撤上限）
    R-IMP-08 ↔ R5   第 3 浪必须突破第 1 浪终点（同属可复算价位比较，1 代无独立编号）
    R-IMP-09 ↔ R6   第 3 浪不得是 1/3/5 中最短
    R-IMP-10 ↔ R7   第 4 浪不得进入第 1 浪价格区域
2 代不再把"失败浪（Truncation）"列为硬公理，故 1 代 R17/R29 不进入可推导集合——
失败浪预期应按"结构失效"登记，不得以规则失效冒充。
"""

import re

RULE_ID_PATTERN = re.compile(r"R-(?:[A-Z]{2,4})-\d{1,2}|\bR\d{1,2}\b")

# 能推出硬价位（比较符可复算）的规则编号：2 代新编号 + 1 代数字编号兼容写法。
DERIVABLE_RULES = frozenset({"R-IMP-07", "R-IMP-08", "R-IMP-09", "R-IMP-10",
                             "R5", "R6", "R7"})

# 「触及即失效」的规则：浪 4 与浪 1 重叠含等号边界（其余按越过判定，不含等号）。
TOUCH_COUNTS_RULES = frozenset({"R-IMP-10", "R7"})


def rule_ids(text):
    """抽取文本中出现的全部规则编号（新旧两种写法）。"""
    return set(RULE_ID_PATTERN.findall(str(text)))


def has_derivable_rule(text):
    """该依据是否引用了可推出数值边界的规则。"""
    return bool(rule_ids(text) & DERIVABLE_RULES)


def touch_counts(text):
    """该依据是否属于「触及即失效」的规则（含等号边界）。"""
    return bool(rule_ids(text) & TOUCH_COUNTS_RULES)


def normalize(text):
    """把 1 代数字编号替换为 2 代等价编号，供报告文案统一展示。"""
    return re.sub(r"\bR5\b", "R-IMP-07/08", re.sub(r"\bR6\b", "R-IMP-09",
                  re.sub(r"\bR7\b", "R-IMP-10", str(text))))
