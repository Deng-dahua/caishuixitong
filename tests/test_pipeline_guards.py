# -*- coding: utf-8 -*-
"""pipeline 守卫函数单测（2026-09-14）。

首项：工商登记状态判定。历史缺陷——原实现用**精确相等**比对白名单
（`st in ("存续","在业","开业","正常")`），而联网核查返回的状态常带后缀
（如「存续（在营、开业、在册）」）→ 不相等 → 正常企业被判为「疑似走逃（失联）企业
或非正常户」，并被挂上 RL-PTY-002「供应商高度集中且地域异常：涉嫌虚开通道」。
"""

import unittest

from engine.pipeline import is_abnormal_business_status


class BusinessStatusGuardTests(unittest.TestCase):
    def test_normal_status_with_suffix_is_not_abnormal(self):
        # 本次实测的真实返回值，修前被判为异常
        self.assertFalse(is_abnormal_business_status("存续（在营、开业、在册）"))
        self.assertFalse(is_abnormal_business_status("存续"))
        self.assertFalse(is_abnormal_business_status("在业"))
        self.assertFalse(is_abnormal_business_status("开业"))
        self.assertFalse(is_abnormal_business_status("在营"))
        self.assertFalse(is_abnormal_business_status("正常"))

    def test_abnormal_statuses_are_detected(self):
        for st in ("注销", "吊销", "吊销，未注销", "经营异常", "异常经营名录",
                   "非正常户", "失信被执行人", "责令关闭", "撤销", "清算中",
                   "停业", "破产重整", "迁出", "失联", "走逃（失联）"):
            self.assertTrue(is_abnormal_business_status(st), st)

    def test_unknown_or_empty_is_not_abnormal(self):
        # 未知状态一律不判异常——不凭空定罪
        for st in ("", None, "存续待核", "其他情形"):
            self.assertFalse(is_abnormal_business_status(st), st)

    def test_blacklist_wins_over_whitelist(self):
        # 同时出现"存续"与异常词时，以异常为准（如"吊销，未注销"类混合写法）
        self.assertTrue(is_abnormal_business_status("存续（吊销）"))


if __name__ == "__main__":
    unittest.main()
