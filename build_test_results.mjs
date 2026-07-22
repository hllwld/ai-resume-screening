import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "D:/wj/dmxpc+RAGyh/jlzs/outputs";
await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("验收结果");
const notes = workbook.worksheets.add("验收说明");

sheet.showGridLines = false;
sheet.getRange("A1:I1").merge();
sheet.getRange("A1").values = [["Day 2 工作流验收结果"]];
sheet.getRange("A1:I1").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center" };
sheet.getRange("A3:I3").values = [["样例", "预期分数", "实际分数", "预期推荐", "实际推荐", "解析状态", "验收", "风险标记 / 备注", "运行状态"]];
sheet.getRange("A3:I3").format = { fill: "#D1FAE5", font: { bold: true, color: "#134E4A" }, horizontalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: "#99B9B4" } };
sheet.getRange("A4:I11").values = [
  ["01 AI项目匹配但工作流实操待确认", "65–80", 72, "manual_review", "manual_review", "success", "PASS", "Dify/Coze/n8n 实操待确认", "已运行"],
  ["02 信息缺失候选人", "0–59", 2, "supplement", "supplement", "success", "PASS", "信息不足，要求补充材料", "已运行"],
  ["03 技能匹配但经验不足", "60–79", null, "manual_review", null, null, "PENDING", "待运行", "待运行"],
  ["04 跨行业转行候选人", "55–75", null, "manual_review", null, null, "PENDING", "待运行", "待运行"],
  ["05 格式混乱候选人", "40–70", null, "supplement", null, null, "PENDING", "待运行", "待运行"],
  ["EDGE-01 空白简历", "不适用", null, "supplement", null, null, "PENDING", "待运行", "待运行"],
  ["EDGE-02 纯乱码文本", "不适用", null, "不报错", null, null, "PENDING", "待运行", "待运行"],
  ["EDGE-03 超长简历", "不适用", null, "不报错", null, null, "PENDING", "待运行", "待运行"],
];
sheet.getRange("A4:I11").format = { verticalAlignment: "top", wrapText: true, borders: { preset: "inside", style: "thin", color: "#D1D5DB" } };
sheet.getRange("C4:C11").format.numberFormat = "0";
sheet.getRange("G4:G11").conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#DCFCE7", font: { color: "#166534", bold: true } } });
sheet.getRange("G4:G11").conditionalFormats.add("containsText", { text: "PENDING", format: { fill: "#FEF3C7", font: { color: "#92400E", bold: true } } });
sheet.getRange("G4:G11").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FEE2E2", font: { color: "#991B1B", bold: true } } });
sheet.getRange("A3:I11").format.autofitColumns();
const widths = [31, 12, 12, 18, 18, 12, 12, 34, 12];
widths.forEach((width, index) => sheet.getRangeByIndexes(0, index, 12, 1).format.columnWidth = width);
sheet.getRange("A4:I11").format.rowHeight = 38;
sheet.freezePanes.freezeRows(3);

notes.showGridLines = false;
notes.getRange("A1:D1").merge();
notes.getRange("A1").values = [["验收口径"]];
notes.getRange("A1:D1").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center" };
notes.getRange("A3:B7").values = [
  ["项目", "规则"],
  ["PASS", "分数落在预期区间、推荐结论符合预期、parse_status=success。"],
  ["DEVIATION", "结果可运行但分数偏差超过 5 分，或推荐结论不同。"],
  ["FAIL", "工作流报错、JSON 无法解析且未返回兜底状态。"],
  ["PENDING", "尚未在 Dify 中运行；不得计为通过。"],
];
notes.getRange("A3:B7").format = { wrapText: true, verticalAlignment: "top", borders: { preset: "all", style: "thin", color: "#D1D5DB" } };
notes.getRange("A3:B3").format = { fill: "#D1FAE5", font: { bold: true, color: "#134E4A" }, horizontalAlignment: "center", borders: { preset: "all", style: "thin", color: "#99B9B4" } };
notes.getRange("A4:A7").format.columnWidth = 16;
notes.getRange("B3:B7").format.columnWidth = 82;
notes.getRange("A4:B7").format.rowHeight = 35;

const check = await workbook.inspect({ kind: "table", range: "验收结果!A1:I11", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 9 });
if (!check.ndjson.includes("02 信息缺失候选人")) throw new Error("Verification failed: expected test row missing");
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 50 }, summary: "formula error scan" });
if (errors.ndjson && /#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/.test(errors.ndjson)) throw new Error("Workbook contains formula errors");
const preview = await workbook.render({ sheetName: "验收结果", range: "A1:I11", scale: 1.5, format: "png" });
await fs.writeFile(`${outputDir}/test_acceptance_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/test_acceptance.xlsx`);
console.log("Created test_acceptance.xlsx");
