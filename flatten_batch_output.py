"""
Dify 批量下载后处理：将三列 CSV（resume_text, job_description, 生成结果）
展开为独立列的验收 CSV，对齐 template.csv 格式。

用法：
    python flatten_batch_output.py <dify_download.csv> [output.csv]

输出列：
    候选人别名 | 处理日期 | 综合匹配分 | 建议 | 技能匹配 | 相关经验 |
    项目相关性 | 综合质量 | 匹配技能 | 待补充信息 | 风险标记 |
    解析状态 | 人工复核结论 | 备注
"""

import csv
import json
import sys
from datetime import date
from pathlib import Path


def flatten(input_path: str, output_path: str = None):
    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_验收就绪.csv")

    rows = []
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get("生成结果", "")
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                result = {}

            # 处理可能嵌套在 parsed_json 里的情况
            if "parsed_json" in result and isinstance(result["parsed_json"], str):
                try:
                    inner = json.loads(result["parsed_json"])
                    if isinstance(inner, dict) and "match_score" in inner:
                        result = {**result, **inner}
                except (json.JSONDecodeError, TypeError):
                    pass

            flat = {
                "候选人别名": result.get("candidate_name", ""),
                "处理日期": date.today().isoformat(),
                "综合匹配分": result.get("match_score", ""),
                "建议": result.get("recommendation", ""),
                "技能匹配": result.get("skill_match", ""),
                "相关经验": result.get("experience_relevance", ""),
                "项目相关性": result.get("project_relevance", ""),
                "综合质量": result.get("overall_quality", ""),
                "匹配技能": result.get("matched_skills", ""),
                "待补充信息": result.get("missing_information", ""),
                "风险标记": result.get("risk_flags", ""),
                "解析状态": result.get("parse_status", ""),
                "人工复核结论": "",
                "备注": "",
            }
            rows.append(flat)

    if not rows:
        print("⚠ 未提取到任何数据行，请检查输入 CSV 的列名是否为「生成结果」")
        return

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ 已展开 {len(rows)} 条结果 → {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python flatten_batch_output.py <dify下载的csv> [输出文件名]")
        sys.exit(1)
    flatten(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
