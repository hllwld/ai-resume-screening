import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = "D:/wj/dmxpc+RAGyh/jlzs/outputs";

async function importBook(name) {
  const file = await FileBlob.load(`${outputDir}/${name}`);
  return SpreadsheetFile.importXlsx(file);
}

async function savePreview(workbook, sheetName, previewName) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1.15, format: "png" });
  await fs.writeFile(`${outputDir}/${previewName}`, new Uint8Array(await preview.arrayBuffer()));
}

const candidateBook = await importBook("candidate_review_template.xlsx");
await savePreview(candidateBook, "候选人汇总", "candidate_review_before_widen.png");
const candidateSheet = candidateBook.worksheets.getItem("候选人汇总");
candidateSheet.getRange("I:M").format.columnWidth = 30;
candidateSheet.getRange("J:K").format.columnWidth = 40;
candidateSheet.getRange("L:L").format.columnWidth = 28;
await savePreview(candidateBook, "候选人汇总", "candidate_review_after_widen.png");
const candidateOut = await SpreadsheetFile.exportXlsx(candidateBook);
await candidateOut.save(`${outputDir}/candidate_review_template.xlsx`);

const acceptanceBook = await importBook("test_acceptance.xlsx");
await savePreview(acceptanceBook, "验收结果", "test_acceptance_before_widen.png");
const acceptanceSheet = acceptanceBook.worksheets.getItem("验收结果");
acceptanceSheet.getRange("A:A").format.columnWidth = 40;
acceptanceSheet.getRange("D:E").format.columnWidth = 22;
acceptanceSheet.getRange("H:H").format.columnWidth = 44;
acceptanceSheet.getRange("I:I").format.columnWidth = 16;
await savePreview(acceptanceBook, "验收结果", "test_acceptance_after_widen.png");
const acceptanceOut = await SpreadsheetFile.exportXlsx(acceptanceBook);
await acceptanceOut.save(`${outputDir}/test_acceptance.xlsx`);

const candidateCheck = await candidateBook.inspect({ kind: "table", range: "候选人汇总!A1:M13", include: "values,formulas", tableMaxRows: 13, tableMaxCols: 13 });
const acceptanceCheck = await acceptanceBook.inspect({ kind: "table", range: "验收结果!A1:I11", include: "values,formulas", tableMaxRows: 11, tableMaxCols: 9 });
if (!candidateCheck.ndjson.includes("AI 简历初筛与岗位匹配助手")) throw new Error("Candidate template verification failed");
if (!acceptanceCheck.ndjson.includes("02 信息缺失候选人")) throw new Error("Acceptance template verification failed");
console.log("Templates widened and verified.");
