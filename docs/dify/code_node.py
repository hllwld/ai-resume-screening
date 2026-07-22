import json
import re


def _extract_json(text: str) -> str:
    """兼容模型偶发返回的 Markdown 围栏或前后说明文字。"""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\\s*|\\s*```$", "", cleaned, flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    return cleaned[start : end + 1] if start >= 0 and end > start else cleaned


def main(llm_output: str) -> dict:
    raw_output = llm_output or ""
    empty = {
        "candidate_name": "", "match_score": 0, "recommendation": "",
        "skill_match": 0, "experience_relevance": 0,
        "project_relevance": 0, "overall_quality": 0,
        "matched_skills": "", "missing_information": "", "risk_flags": "",
    }
    try:
        parsed = json.loads(_extract_json(raw_output))
        dim = parsed.get("dimension_scores", {}) or {}
        return {
            "parsed_json": json.dumps(parsed, ensure_ascii=False),
            "parse_status": "success",
            "raw_output": raw_output,
            "candidate_name": parsed.get("candidate_name", ""),
            "match_score": parsed.get("match_score", 0),
            "recommendation": parsed.get("recommendation", ""),
            "skill_match": dim.get("skill_match", 0),
            "experience_relevance": dim.get("experience_relevance", 0),
            "project_relevance": dim.get("project_relevance", 0),
            "overall_quality": dim.get("overall_quality", 0),
            "matched_skills": "、".join(parsed.get("matched_skills", []) or []),
            "missing_information": "；".join(parsed.get("missing_information", []) or []),
            "risk_flags": "；".join(parsed.get("risk_flags", []) or []),
        }
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        fallback = {
            "error": "parse_failed",
            "message": "模型输出不是合法 JSON；请人工复核 raw_output。",
        }
        return {
            "parsed_json": json.dumps(fallback, ensure_ascii=False),
            "parse_status": f"failed: {type(exc).__name__}",
            "raw_output": raw_output,
            **empty,
        }
