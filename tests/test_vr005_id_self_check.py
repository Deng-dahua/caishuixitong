"""VR005 报告叙述自检：身份证号核验用工身份 + 通俗化叙述。

回归缺陷A：报告盲列『退休返聘』而不回查身份证号；
回归缺陷B：『人员-月份』术语不通俗。

来源：本会话上下文 2026-09-04 用户对杨莹（230828199201073526，1992年生，女）的反馈。
"""
import unittest

from engine.verified_rule_engine import (
    _id_card_of, _parse_id_card, _employment_candidates_and_note,
    _scan_payroll_social,
)


class TestIdCardExtraction(unittest.TestCase):
    """_id_card_of 必须兼容多种键名 + 仅接受合规格式。"""

    def test_id_card_key(self):
        self.assertEqual(_id_card_of({"id_card": "230828199201073526"}),
                         "230828199201073526")

    def test_id_number_key(self):
        self.assertEqual(_id_card_of({"id_number": "230828199201073526"}),
                         "230828199201073526")

    def test_chinese_keys(self):
        self.assertEqual(_id_card_of({"证件号码": "230828199201073526"}),
                         "230828199201073526")
        self.assertEqual(_id_card_of({"身份证号": "230828199201073526"}),
                         "230828199201073526")
        self.assertEqual(_id_card_of({"身份证": "230828199201073526"}),
                         "230828199201073526")

    def test_non_id_values_rejected(self):
        # 工号（数字但非 15/18 位）
        self.assertEqual(_id_card_of({"id_card": "1001"}), "")
        # 电话（11 位）
        self.assertEqual(_id_card_of({"id_card": "13800138000"}), "")
        # 空
        self.assertEqual(_id_card_of({"id_card": ""}), "")
        self.assertEqual(_id_card_of({"id_card": None}), "")

    def test_invalid_type(self):
        self.assertEqual(_id_card_of(None), "")
        self.assertEqual(_id_card_of("not a dict"), "")


class TestIdCardParse(unittest.TestCase):
    """_parse_id_card 解析 18 位 / 15 位身份证，校验性别与年份。"""

    def test_18digit_female_1992(self):
        y, g = _parse_id_card("230828199201073526")
        self.assertEqual(y, 1992)
        self.assertEqual(g, "女")

    def test_18digit_male(self):
        # 17 位奇数 → 男
        y, g = _parse_id_card("110101199003075517")
        self.assertEqual(y, 1990)
        self.assertEqual(g, "男")

    def test_15digit(self):
        # 15 位：19+[6:8] 年份，[14] 性别
        y, g = _parse_id_card("110101920307551")
        self.assertEqual(y, 1992)
        self.assertEqual(g, "男")

    def test_invalid_format(self):
        self.assertEqual(_parse_id_card("123"), (None, None))
        self.assertEqual(_parse_id_card(""), (None, None))
        self.assertEqual(_parse_id_card(None), (None, None))


class TestEmploymentCandidatesSelfCheck(unittest.TestCase):
    """用工身份候选自检：身份证号存在时按年龄/性别约束，无时声明数据缺口。"""

    def test_yang_ying_34_female_removes_retire(self):
        cands, note = _employment_candidates_and_note(
            "杨莹", {"杨莹": "230828199201073526"}, cur_year=2026)
        self.assertNotIn("退休返聘", cands)
        self.assertIn("在职", cands)
        self.assertIn("劳务派遣", cands)
        self.assertIn("1992", note)
        self.assertIn("女", note)
        self.assertIn("34", note)
        self.assertIn("未达法定退休年龄", note)

    def test_60_year_old_male_keeps_all(self):
        # 1966 年生，男，60 岁——已达退休下限，保留全部候选并透明披露
        cands, note = _employment_candidates_and_note(
            "老张", {"老张": "11010119660101001X"}, cur_year=2026)
        self.assertIn("退休返聘", cands)
        self.assertIn("已核身份证号", note)
        self.assertIn("60", note)

    def test_no_id_card_explicit_gap(self):
        cands, note = _employment_candidates_and_note(
            "某员工", {}, cur_year=2026)
        self.assertIn("退休返聘", cands)  # 缺数据时保留全部，标注为排查清单
        self.assertIn("系统未获取到", note)
        self.assertIn("排查清单", note)
        self.assertIn("劳动合同", note)


class TestVR005SelfCheckNarrative(unittest.TestCase):
    """端到端：_scan_payroll_social 必须按身份证号自检并约束候选清单。"""

    def _spec(self):
        return {
            "id": "VR005",
            "required_sources": ["salaries", "social_security"],
            "name": "VR005 工资名册与社保清单人员范围",
        }

    def _salary(self, name, id_card, period="2025-01", amount=10000):
        return {"name": name, "id_card": id_card, "salary": amount,
                "period_start": period + "-01"}

    def _social(self, name, period="2025-01", base=5000):
        return {"name": name, "base": base, "period_start": period + "-01"}

    def test_yang_ying_excluded_from_retire_candidates(self):
        # 6 个名字 + 杨莹仅在工资名册中（无社保），杨莹 1992 年生 / 女
        # 前 5 人给虚拟 18 位身份证号（格式合法即可，年龄不影响 narrative——他们不在 only_salary）
        dummy_ids = [
            "230828198001010011",  # 1980 男
            "230828198501010012",  # 1985 男
            "230828198801010013",  # 1988 男
            "230828199001010014",  # 1990 男
            "230828199301010015",  # 1993 男
        ]
        names = ["张三", "李四", "王五", "赵六", "钱七", "杨莹"]
        salaries = [self._salary(n, dummy_ids[i])
                    for i, n in enumerate(names[:5])]
        salaries.append(self._salary("杨莹", "230828199201073526"))
        # 让前 5 人都有社保、杨莹无社保
        social = [self._social(n) for n in names[:5]]
        result = _scan_payroll_social(
            {"salaries": salaries, "social_security": social},
            self._spec())
        self.assertEqual(len(result), 1)
        detail = result[0]["detail"]
        # 杨莹叙述必须出现身份证号、年龄、性别，且『退休返聘』不再作为候选
        self.assertIn("杨莹", detail)
        self.assertIn("230828199201073526", detail)
        self.assertIn("1992", detail)
        self.assertIn("女", detail)
        self.assertIn("34", detail)
        self.assertIn("未达法定退休年龄", detail)
        self.assertIn("退休返聘", detail)  # 文档总体仍提及，但要带『客观不成立』标注
        self.assertIn("客观不成立", detail)
        # 杨莹的候选清单应是『在职、劳务派遣、兼职、非雇员劳务』（已剔除『退休返聘』）
        # 出现的『退休返聘』只应作为「已剔除」陈述，不应作为并列候选
        self.assertIn("用工身份（在职、劳务派遣、兼职、非雇员劳务）", detail)
        self.assertNotIn("用工身份（在职、退休返聘、劳务派遣、兼职、非雇员劳务）", detail)
        # 文档总体仍提及『退休返聘』，但必须带「客观不成立」或类似剔除标注
        self.assertIn("客观不成立", detail)
        # 开篇叙述必须是通俗表达，不再出现『人员-月份组合』
        self.assertNotIn("『人员-月份』组合", detail)
        self.assertIn("姓名+月份", detail)

    def test_unknown_id_explicit_data_gap(self):
        salaries = [self._salary(n, "")  # 无身份证号
                    for n in ["张三", "李四", "王五", "赵六", "钱七", "杨莹"]]
        social = [self._social(n) for n in ["张三", "李四", "王五", "赵六", "钱七"]]
        result = _scan_payroll_social(
            {"salaries": salaries, "social_security": social},
            self._spec())
        detail = result[0]["detail"]
        # 未获取身份证号：必须显式声明数据缺口，且仍含全部候选但标注为『排查清单』
        self.assertIn("系统未获取到", detail)
        self.assertIn("排查清单", detail)
        self.assertIn("劳动合同", detail)


if __name__ == "__main__":
    unittest.main()