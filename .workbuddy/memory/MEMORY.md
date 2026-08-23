# 项目长期记忆（caishuixitong 税务稽查系统）

## 系统定位（用户明确，2026-08-22）
双定位，所有功能设计须同时满足：
1. **给税务稽查人员**做企业稽查分析（稽查视角）；
2. **给企业**从"被稽查视角"自查税务风险、并指引合规（自审+合规指引视角）。

## 用户核心诉求主线
- 反复强调：系统必须"有稽查实质"，不是漂亮外壳。凡属"解析了但没研判/研判薄弱"的模块，都是要持续加固的对象（BOM、进销存、委外加工、关联方、发票网络等）。
- 能力须**全行业/全企业通用**，不要只针对达冠一家公司。

## 关键架构事实
- 服务器：`python main.py` 自拉起，127.0.0.1:8001，默认数据目录 ./data；平台不自动重启，改代码后需手动重启。
- 引擎数据字典在 engine/pipeline.py 组装；BOM/进销存 已接入 `_domain_bom_verify` / `_domain_inventory_turnover`（domain_analysis.py）。
- 验证引擎纯函数可直接 `from engine.domain_analysis import _domain_*` 用 .venv 跑（.venv/Scripts/python.exe）。
- 前端上传走内容自动分类（FILE_TYPE_CONFIG，main.py:2109 起），BOM 解析器已注册，上传即被识别。
