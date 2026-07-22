# 交付包清单

## 可直接展示

| 材料 | 路径 | 状态 |
|---|---|---|
| 项目说明与架构图 | `README.md` | 已完成 |
| Dify System Prompt | `docs/dify/system_prompt.md` | 已完成 |
| JSON 容错代码 | `docs/dify/code_node.py` | 已完成 |
| 5 份脱敏测试简历 | `docs/test_cases/` | 已完成 |
| 预期与实际测试记录 | `docs/expected_results.csv`、`docs/test_results.csv` | 已完成（2/5 已运行） |
| Day 2 验收表 | `outputs/test_acceptance.xlsx` | 已完成 |
| 人工复核模板 | `outputs/candidate_review_template.xlsx` | 已完成 |
| Demo 讲稿 | `docs/demo_script.md` | 已完成 |
| 面试问答 | `docs/interview_qa.md` | 已完成 |

## 需要在 Dify 或外部平台完成

- 运行剩余 3 份样例与 3 个边界样例，并更新 `docs/test_results.csv` 和验收表。
- 从 Dify 导出 Workflow DSL 文件，保存到 `workflow/`。
- 依据 `docs/demo_script.md` 录制 3 分钟 Demo 视频。
- 上传交付包到网盘、Notion 或代码仓库后生成分享链接。

## 投递介绍语

我使用 Dify + DeepSeek 搭建了 AI 简历初筛与岗位匹配助手，覆盖 Prompt 设计、岗位匹配评分、证据追溯、JSON 容错和人工复核流程。已用脱敏样例验证结构化输出与异常兜底；当信息不足时，系统会引导补充材料而非自动淘汰。项目材料包含工作流架构、测试记录、Excel 验收表和演示讲稿。
