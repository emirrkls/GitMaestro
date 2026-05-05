from maestro.core.score import build_initial_score


def test_score_complexity_and_movements() -> None:
    low = build_initial_score("bug-12345", ad_hoc_budget=1, max_retries=3)
    assert low.complexity == "low"
    assert any(m.agent == "Critic" for m in low.movements)

    high = build_initial_score("security-crash-777", ad_hoc_budget=1, max_retries=3)
    assert high.complexity == "high"
    assert any(m.agent == "AdHoc" for m in high.movements)

    ambiguous = build_initial_score("12", ad_hoc_budget=1, max_retries=3)
    assert ambiguous.complexity == "ambiguous"
