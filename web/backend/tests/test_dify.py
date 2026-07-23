import json

from app.dify import normalize_dify_response


def test_normalize_parsed_json():
    result = normalize_dify_response(
        {
            "data": {
                "outputs": {
                    "parsed_json": json.dumps(
                        {
                            "candidate_name": "测试候选人",
                            "match_score": 80,
                            "dimension_scores": {
                                "skill_match": 80,
                                "experience_relevance": 80,
                                "project_relevance": 80,
                                "overall_quality": 80,
                            },
                            "recommendation": "interview",
                            "matched_skills": ["Python"],
                            "missing_information": [],
                            "risk_flags": [],
                            "evidence": {
                                "skill_match": ["熟悉 Python"],
                                "experience_relevance": [],
                                "project_relevance": [],
                                "overall_quality": [],
                            },
                            "recommended_interview_questions": [],
                            "human_review_note": "仅供人工复核",
                        },
                        ensure_ascii=False,
                    )
                }
            }
        }
    )
    assert result.match_score == 80
    assert result.candidate_name == "测试候选人"
