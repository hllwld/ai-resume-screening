import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "D:/wj/dmxpc+RAGyh/jlzs/outputs";
await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();
const review = workbook.worksheets.add("候选人汇总");
const rules = workbook.worksheets.add("评分规则");
const guide = workbook.worksheets.add("使用说明");

const headerStyle = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center", verticalAlignment: "center" };
const tableHeader = { fill: "#D1FAE5", font: { bold: true, color: "#134E4A" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: "#99B9B4" } };

review.showGridLines = false;
review.getRange("A1:M1").merge();
review.getRange("A1").values = [["AI 简历初筛与岗位匹配助手｜人工复核汇总"]];
review.getRange("A1:M1").format = headerStyle;
review.getRange("A1:M1").format.rowHeight = 30;
review.getRange("A3:M3").values = [["候选人别名", "处理日期", "综合匹配分", "建议", "技能匹配", "相关经验", "项目相关性", "综合质量", "匹配技能", "待补充信息", "风险标记", "人工复核结论", "备注"]];
review.getRange("A3:M3").format = tableHeader;
review.getRange("A4:M13").values = Array.from({ length: 10 }, () => Array(13).fill(null));
review.getRange("A4:M13").format = { verticalAlignment: "top", wrapText: true, borders: { preset: "inside", style: "thin", color: "#D1D5DB" } };
review.getRange("B4:B13").format.numberFormat = "yyyy-mm-dd";
review.getRange("C4:H13").format.numberFormat = "0";
review.getRange("C4:C13").conditionalFormats.add("colorScale", { colors: ["#FECACA", "#FEF3C7", "#BBF7D0"], thresholds: ["min", "50%", "max"] });
review.getRange("D4:D13").dataValidation = { rule: { type: "list", values: ["interview", "manual_review", "supplement", "reject"] } };
review.getRange("L4:L13").dataValidation = { rule: { type: "list", values: ["待复核", "进入面试", "补充材料", "不建议推进（人工确认）"] } };
const widths = [15, 13, 12, 16, 12, 12, 13, 12, 25, 28, 28, 22, 26];
widths.forEach((width, index) => review.getRangeByIndexes(0, index, 14, 1).format.columnWidth = width);
review.getRange("A4:M13").format.rowHeight = 48;
review.freezePanes.freezeRows(3);

rules.showGridLines = false;
rules.getRange("A1:D1").merge(); rules.getRange("A1").values = [["评分规则与人工复核边界"]]; rules.getRange("A1:D1").format = headerStyle;
rules.getRange("A3:D3").values = [["评分维度", "权重", "评分依据", "不可使用的信息"]]; rules.getRange("A3:D3").format = tableHeader;
rules.getRange("A4:D7").values = [
  ["技能匹配", 0.4, "与 JD 明确重合的技能与工具", "年龄、性别、籍贯、婚育、民族、健康等敏感信息"],
  ["相关经验", 0.25, "与岗位职责直接相关的经历；未提供时标待确认", "同上"],
  ["项目相关性", 0.2, "AI 自动化、工作流、数据处理、RAG/Agent/API 等项目证据", "同上"],
  ["综合质量", 0.15, "信息完整性、问题拆解、验证与复盘证据", "同上"],
];
rules.getRange("A3:D7").format = { wrapText: true, verticalAlignment: "top", borders: { preset: "all", style: "thin", color: "#D1D5DB" } };
rules.getRange("A3:D3").format = tableHeader; rules.getRange("B4:B7").format.numberFormat = "0%"; rules.getRange("A4:D7").format.rowHeight = 48;
rules.getRange("A9:D11").merge(); rules.getRange("A9").values = [["使用边界：模型输出仅辅助人工整理与复核；信息缺失时应补充材料或人工判断，不能自动决定录用或淘汰。"]];
rules.getRange("A9:D11").format = { fill: "#FFF7ED", font: { color: "#9A3412", bold: true }, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#FDBA74" } };
rules.getRange("A:D").format.columnWidth = 28;

guide.showGridLines = false;
guide.getRange("A1:B1").merge(); guide.getRange("A1").values = [["导入与复核说明"]]; guide.getRange("A1:B1").format = headerStyle;
guide.getRange("A3:B7").values = [["步骤", "操作"], ["1", "在 Dify 工作流运行后复制 parsed_json。"], ["2", "将候选人别名、日期、分数、建议、证据摘要和待确认项写入“候选人汇总”。"], ["3", "招聘人员填写“人工复核结论”，并保留与候选人的沟通依据。"], ["4", "不得将 recommendation 作为自动录用或淘汰的唯一依据。"]];
guide.getRange("A3:B7").format = { wrapText: true, verticalAlignment: "top", borders: { preset: "all", style: "thin", color: "#D1D5DB" } };
guide.getRange("A3:B3").format = tableHeader; guide.getRange("A4:A7").format.columnWidth = 10; guide.getRange("B3:B7").format.columnWidth = 75; guide.getRange("A4:B7").format.rowHeight = 35;

const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 30 }, summary: "formula error scan" });
if (errors.ndjson && /#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/.test(errors.ndjson)) throw new Error("Workbook contains formula errors");
const preview = await workbook.render({ sheetName: "候选人汇总", range: "A1:M13", scale: 1.4, format: "png" });
await fs.writeFile(`${outputDir}/candidate_review_template_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/candidate_review_template.xlsx`);
console.log("Created candidate_review_template.xlsx");
