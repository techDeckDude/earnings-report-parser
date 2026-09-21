from __future__ import annotations


# ── Pages ─────────────────────────────────────────────────────────────────────

def test_root_200(flask_client):
    assert flask_client.get("/").status_code == 200


def test_news_page_200(flask_client):
    assert flask_client.get("/news").status_code == 200


# ── /api/revenue ──────────────────────────────────────────────────────────────

def test_api_revenue_is_list(flask_client):
    data = flask_client.get("/api/revenue").get_json()
    assert isinstance(data, list)


def test_api_revenue_has_required_keys(flask_client):
    data = flask_client.get("/api/revenue").get_json()
    assert len(data) > 0
    row = data[0]
    for key in ("ticker", "period", "revenue"):
        assert key in row, f"missing key: {key}"


# ── /api/tickers ──────────────────────────────────────────────────────────────

def test_api_tickers_is_list(flask_client):
    data = flask_client.get("/api/tickers").get_json()
    assert isinstance(data, list)


def test_api_tickers_has_required_keys(flask_client):
    data = flask_client.get("/api/tickers").get_json()
    assert len(data) > 0
    for key in ("ticker", "name"):
        assert key in data[0]


def test_api_tickers_includes_known_tickers(flask_client):
    tickers = {t["ticker"] for t in flask_client.get("/api/tickers").get_json()}
    assert "PLTR" in tickers
    assert "MRVL" in tickers


# ── /api/metrics/<ticker> ─────────────────────────────────────────────────────

def test_api_metrics_pltr(flask_client):
    resp = flask_client.get("/api/metrics/PLTR").get_json()
    assert isinstance(resp, dict)
    assert "data" in resp
    for section in ("income_statement", "balance_sheet", "cash_flow"):
        assert section in resp["data"], f"missing section: {section}"


def test_api_metrics_mrvl(flask_client):
    resp = flask_client.get("/api/metrics/MRVL").get_json()
    assert isinstance(resp, dict)
    assert "data" in resp
    for section in ("income_statement", "balance_sheet", "cash_flow"):
        assert section in resp["data"]


def test_api_metrics_pltr_has_revenue(flask_client):
    resp = flask_client.get("/api/metrics/PLTR").get_json()
    assert "revenue" in resp["data"]["income_statement"]


# ── /api/news ─────────────────────────────────────────────────────────────────

def test_api_news_is_list(flask_client):
    data = flask_client.get("/api/news").get_json()
    assert isinstance(data, list)


def test_api_news_has_required_keys(flask_client):
    data = flask_client.get("/api/news").get_json()
    assert len(data) > 0
    run = data[0]
    for key in ("week_start", "week_end", "period", "headlines", "summary_stats"):
        assert key in run, f"missing key: {key}"


def test_api_news_headlines_have_required_keys(flask_client):
    data = flask_client.get("/api/news").get_json()
    assert len(data) > 0
    headlines = data[0]["headlines"]
    assert len(headlines) > 0
    for key in ("headline", "source", "sentiment_score", "sentiment_label"):
        assert key in headlines[0], f"missing key: {key}"
