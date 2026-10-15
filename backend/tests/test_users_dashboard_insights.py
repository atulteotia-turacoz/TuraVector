def test_insights_permission(client, login_as):
    assert client.get("/api/users/manager-dashboard/insights", headers=login_as("teacher1")).status_code == 403


def test_insights(client, login_as):
    r = client.get("/api/users/manager-dashboard/insights", headers=login_as("admin"))
    assert r.status_code == 200
    d = r.json()
    assert len(d["activity"]) == 12
    assert d["recent_uploads"] and {"document_name", "uploaded_by", "is_new_document"} <= set(d["recent_uploads"][0])
    assert isinstance(d["workload"], list) and isinstance(d["waiting"], list)


def test_insights_counts_match_sql(client, login_as, db):
    """Aggregates must be real counts (a SUM over a boolean comparison once returned 1)."""
    from sqlalchemy import text
    d = client.get("/api/users/manager-dashboard/insights", headers=login_as("admin")).json()
    open_overdue = db.execute(text(
        "select count(*) from library_assignedreviewer where is_active=1 and is_completed=0 and review_date < :now"),
        {"now": __import__("app.models", fromlist=["utcnow"]).utcnow()}).scalar()
    assert sum(w["overdue"] for w in d["workload"]) == open_overdue
    new_docs = sum(a["new_documents"] for a in d["activity"])
    assert new_docs > sum(1 for a in d["activity"] if a["new_documents"])  # not capped at 1 per month


def test_insights_turnaround_and_top_contributors(client, login_as):
    d = client.get("/api/users/manager-dashboard/insights", headers=login_as("admin")).json()
    t = d["turnaround"]
    assert set(t) == {"completed_90d", "avg_days", "on_time_pct", "open", "open_avg_age_days"}
    assert t["open"] >= 0 and (t["on_time_pct"] is None or 0 <= t["on_time_pct"] <= 100)
    top = d["top_contributors"]
    assert len(top) <= 5 and all(top[i]["documents"] >= top[i + 1]["documents"] for i in range(len(top) - 1))
