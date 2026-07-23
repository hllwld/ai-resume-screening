import * as pdfjs from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { TextItem } from "pdfjs-dist/types/src/display/api";
import type { ParsedResume } from "./types";

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const MAX_PAGES = 30;
const MAX_CHARS = 60000;
const MIN_TEXT_CHARS = 100;

function normalizePage(items: TextItem[]): string {
  let lastY: number | null = null;
  const lines: string[] = [];
  let current = "";

  for (const item of items) {
    const y = item.transform[5];
    const startsNewLine = lastY !== null && Math.abs(y - lastY) > 4;
    if (startsNewLine && current.trim()) {
      lines.push(current.trim());
      current = "";
    }
    current += `${current ? " " : ""}${item.str}`;
    if (item.hasEOL && current.trim()) {
      lines.push(current.trim());
      current = "";
    }
    lastY = y;
  }
  if (current.trim()) lines.push(current.trim());
  return lines.join("\n");
}

export async function parsePdf(file: File): Promise<ParsedResume> {
  const base: ParsedResume = {
    id: crypto.randomUUID(),
    fileName: file.name,
    relativePath: file.webkitRelativePath || file.name,
    size: file.size,
    pages: 0,
    chars: 0,
    text: "",
    state: "parsing",
  };

  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return { ...base, state: "error", error: "仅支持 PDF 文件" };
  }
  if (file.size > MAX_FILE_SIZE) {
    return { ...base, state: "error", error: "文件超过 10 MB" };
  }

  try {
    const data = new Uint8Array(await file.arrayBuffer());
    const document = await pdfjs.getDocument({ data }).promise;
    if (document.numPages > MAX_PAGES) {
      return {
        ...base,
        pages: document.numPages,
        state: "error",
        error: `页数超过 ${MAX_PAGES} 页`,
      };
    }

    const pages: string[] = [];
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      const page = await document.getPage(pageNumber);
      const content = await page.getTextContent();
      const items = content.items.filter(
        (item): item is TextItem => "str" in item,
      );
      pages.push(normalizePage(items));
    }
    const text = pages.join("\n\n").slice(0, MAX_CHARS).trim();
    const chars = text.replace(/\s/g, "").length;
    if (chars < MIN_TEXT_CHARS) {
      return {
        ...base,
        pages: document.numPages,
        chars,
        text,
        state: "scan",
        error: "可提取文字过少，疑似扫描件，需要 OCR",
      };
    }
    return {
      ...base,
      pages: document.numPages,
      chars,
      text,
      state: "ready",
    };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "PasswordException"
        ? "PDF 已加密，无法读取"
        : "PDF 解析失败或文件已损坏";
    return { ...base, state: "error", error: message };
  }
}
