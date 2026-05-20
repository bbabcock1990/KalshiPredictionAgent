from kalshi_agents.storage.db import CalibrationStore


def test_log_and_score(tmp_path):
    store = CalibrationStore(tmp_path / "cal.db")
    decisions = [
        {"ticker": "A", "side": "YES", "signal": "GO",
         "model_prob": 0.8, "market_prob": 0.6, "edge": 0.2,
         "confidence": 0.9, "stake_usd": 10, "max_price": 0.6,
         "contracts": 16, "rationale": ""},
        {"ticker": "B", "side": "YES", "signal": "GO",
         "model_prob": 0.3, "market_prob": 0.5, "edge": 0.2,
         "confidence": 0.9, "stake_usd": 10, "max_price": 0.5,
         "contracts": 20, "rationale": ""},
    ]
    for d in decisions:
        store.log_prediction(d)
    assert store.brier_score() is None  # no outcomes yet
    store.record_outcome("A", True)   # was 0.8 vs 1 → (0.2)^2 = 0.04
    store.record_outcome("B", False)  # was 0.3 vs 0 → (0.3)^2 = 0.09
    score = store.brier_score()
    assert score is not None
    assert abs(score - (0.04 + 0.09) / 2) < 1e-9
