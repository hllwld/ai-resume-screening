# Day 2 测试验收记录

## 已完成测试

| 编号 | 样例 | 实际分数 | 推荐结论 | JSON 解析 | 验收 |
|---|---|---:|---|---|---|
| 01 | AI 项目匹配但工作流实操待确认 | 72 | `manual_review` | `success` | PASS |
| 02 | 信息缺失候选人 | 2 | `supplement` | `success` | PASS |

## 已验证能力

- 输入变量可正确传递至 LLM。
- LLM 可根据 JD 输出带证据的结构化判断。
- Code 节点可从包含 `<think>` 的原始文本中提取 JSON，并返回 `parse_status=success`。
- 信息不足样例被引导至补充材料，而不是自动淘汰。

## 待完成测试

`03_skill_but_junior.md`、`04_career_switcher.md`、`05_messy_format.md` 与三项边界测试仍需在 Dify 里运行。不得将未运行样例计为通过。

## Web 端到端验收（2026-07-23）

使用虚构英文 PDF 通过 Vue 页面完成真实链路验证：

- PDF.js 成功读取 1 页、288 字符。
- 浏览器提交 JD 与补充评价要求，FastAPI 调用已发布的 Dify Workflow。
- Dify 返回 `Test User`、综合匹配分 93、推荐 `interview`，四项评分、证据和面试问题均可展开查看。
- 页面任务统计为成功 1、失败 0。
- XLSX 下载成功，包含“候选人汇总”和“处理说明”两个工作表；条件格式、人工复核下拉框、长文本动态行高均通过检查。

真实测试仅使用虚构内容，不包含真实候选人信息。
