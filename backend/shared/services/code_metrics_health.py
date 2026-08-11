"""Pure code-quality score calculation shared by HTTP and worker paths."""
from __future__ import annotations


def calculate_health_score(data: dict) -> dict:
    """Calculate the six-dimensional code-health score from collected metrics."""
    total_loc = max(data.get("total_loc", 1), 1)
    kloc = total_loc / 1000
    total_functions = max(data.get("total_functions", 0), 1)

    cc_adequacy = data.get("cc_adequacy", 0) or (
        (total_functions - data.get("cc_huge_count", 0)) / total_functions * 100
    )
    score_complexity = max(0, min(100, cc_adequacy))
    security_kloc = (
        data.get("unsafe_functions_count", 0) + data.get("warning_suppression_count", 0)
    ) / kloc
    score_security = max(0, 100 - security_kloc * 10)
    score_duplication = max(0, 100 - data.get("dup_ratio", 0))
    score_method_size = max(0, 100 - data.get("huge_method_ratio", 0))
    debt_kloc = (
        data.get("todo_count", 0)
        + data.get("fixme_count", 0)
        + data.get("hack_count", 0)
    ) / kloc
    score_tech_debt = max(0, 100 - debt_kloc * 5)
    lint_kloc = data.get("lint_errors", 0) / kloc
    score_lint = max(0, 100 - lint_kloc * 5)
    total = (
        score_complexity * 0.20
        + score_security * 0.20
        + score_duplication * 0.15
        + score_method_size * 0.15
        + score_tech_debt * 0.15
        + score_lint * 0.15
    )
    return {
        "health_score": round(total, 1),
        "health_score_complexity": round(score_complexity, 1),
        "health_score_security": round(score_security, 1),
        "health_score_duplication": round(score_duplication, 1),
        "health_score_method_size": round(score_method_size, 1),
        "health_score_tech_debt": round(score_tech_debt, 1),
        "health_score_lint": round(score_lint, 1),
    }
