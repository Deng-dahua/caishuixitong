"""VR005 报告叙述自检：身份证号核验用工身份 + 通俗化叙述。

回归缺陷A：报告盲列『退休返聘』而不回查身份证号；
回归缺陷B：『人员-月份』术语不通俗；
回归缺陷C（2026-09-13 用户要求）：核验过程被写进报告正文——
  「（已核身份证号…未达法定退休年龄下限（女50/男60），『退休返聘』客观不成立，
  已从候选清单中剔除）」这类系统内部推理记录不该出现在给企业的对外文书里。

★ 分工：核验逻辑保留（`cands` 仍按年龄剔除『退休返聘』），
   但报告正文只写「需企业说明什么」，不写「系统怎么排除的」。
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
    """用工身份候选自检：身份证号存在时按年龄/性别约束，无时保留全部候选。

    ★ 注意：本类只断言**逻辑**（候选清单是否被正确约束），
      不断言 note 文案包含身份证号/年龄等信息——那些是内部核查记录，不进报告。
    """

    def test_yang_ying_34_female_removes_retire(self):
        cands, note = _employment_candidates_and_note(
            "杨莹", {"杨莹": "230828199201073526"}, cur_year=2026)
        # 逻辑：34 岁女性，未达退休年龄下限 → 候选清单不得含『退休返聘』
        self.assertNotIn("退休返聘", cands)
        self.assertIn("在职", cands)
        self.assertIn("劳务派遣", cands)
        # 文案：只写需企业说明的事项，不得暴露核验过程与身份证号
        self.assertNotIn("已核身份证号", note)
        self.assertNotIn("未达法定退休年龄", note)
        self.assertNotIn("230828199201073526", note)
        self.assertNotIn("客观不成立", note)
        self.assertIn("用工身份", note)
        self.assertIn("未参保原因", note)

    def test_60_year_old_male_keeps_all(self):
        # 1966 年生，男，60 岁——已达退休下限，候选清单保留全部（含退休返聘）
        cands, note = _employment_candidates_and_note(
            "老张", {"老张": "11010119660101001X"}, cur_year=2026)
        self.assertIn("退休返聘", cands)
        self.assertIn("用工身份", note)
        self.assertNotIn("已核身份证号", note)

    def test_no_id_card_keeps_all_candidates(self):
        cands, note = _employment_candidates_and_note(
            "某员工", {}, cur_year=2026)
        # 缺身份证号时无从约束，保留全部候选，由企业说明
        self.assertIn("退休返聘", cands)
        self.assertIn("身份证号", note)
        self.assertIn("用工身份", note)
        self.assertNotIn("系统未获取到", note)

    def test_note_never_leaks_internal_reasoning(self):
        """任何情况下 note 都不得出现系统内部推理与筛查动作的措辞。"""
        forbidden = ["已核身份证号", "已从候选清单中剔除", "客观不成立",
                     "系统未获取到", "系统已", "系统未",
                     "出生", "岁，", "法定退休年龄下限"]
        cases = [
            ("杨莹", {"杨莹": "230828199201073526"}, 2026),   # 未达退休线
            ("老张", {"老张": "11010119660101001X"}, 2026),   # 已达退休线
            ("某员工", {}, 2026),                              # 无身份证号
            ("错号", {"错号": "123"}, 2026),                   # 格式无法解析
        ]
        for name, ids, yr in cases:
            _, note = _employment_candidates_and_note(name, ids, cur_year=yr)
            for f in forbidden:
                self.assertNotIn(f, note, f"note 泄露内部推理「{f}」：{note}")


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
        # 杨莹必须被点名要求说明（这是报告该有的内容）
        self.assertIn("杨莹", detail)
        self.assertIn("用工身份", detail)
        self.assertIn("未参保原因", detail)
        # ★ 但身份核验过程不得出现在报告正文（2026-09-13 用户要求）
        self.assertNotIn("已核身份证号", detail)
        self.assertNotIn("230828199201073526", detail)
        self.assertNotIn("未达法定退休年龄", detail)
        self.assertNotIn("客观不成立", detail)
        self.assertNotIn("已从候选清单中剔除", detail)
        self.assertNotIn("出生于", detail)
        self.assertNotIn("当前约", detail)
        # 杨莹的候选清单不含『退休返聘』（逻辑生效），但报告不解释为什么剔除
        self.assertIn("用工身份", detail)
        self.assertNotIn("退休返聘", detail)
        # 开篇叙述必须是通俗表达，不再出现『人员-月份组合』
        self.assertNotIn("『人员-月份』组合", detail)
        self.assertIn("姓名+月份", detail)

    def test_unknown_id_no_internal_narration(self):
        salaries = [self._salary(n, "")  # 无身份证号
                    for n in ["张三", "李四", "王五", "赵六", "钱七", "杨莹"]]
        social = [self._social(n) for n in ["张三", "李四", "王五", "赵六", "钱七"]]
        result = _scan_payroll_social(
            {"salaries": salaries, "social_security": social},
            self._spec())
        detail = result[0]["detail"]
        # 无身份证号时仍要点名要求说明身份
        self.assertIn("杨莹", detail)
        self.assertIn("用工身份", detail)
        # 但不得出现系统内部动作的自述
        self.assertNotIn("系统未获取到", detail)
        self.assertNotIn("系统已", detail)
        self.assertNotIn("排查清单而非认定结论", detail)


if __name__ == "__main__":
    unittest.main()