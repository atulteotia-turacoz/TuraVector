"""Rate cards: the standard services list and each university's own rate card."""
import uuid

from sqlalchemy import select

from app.models import Organisation

URL = "/api/superadmin/rates"


def _service(client, h, **kw):
    body = {"name": f"Svc {uuid.uuid4().hex[:6]}", "unit": "per_document", "standard_rate": "1000", "tax_percent": 18, **kw}
    r = client.post(f"{URL}/services", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()["service"]


def test_standard_services_crud_and_validation(client, login_as):
    h = login_as("admin")
    assert client.get(f"{URL}/services", headers=login_as("teacher1")).status_code == 403
    s = _service(client, h, name="Manuscript review T", standard_rate="2500.5")
    assert s["standard_rate"] == 2500.5 and s["unit_label"] == "Per document" and s["currency"] == "INR"
    assert client.post(f"{URL}/services", headers=h, json={"name": "manuscript REVIEW t", "unit": "per_page"}).status_code == 400
    assert client.post(f"{URL}/services", headers=h, json={"name": "X", "unit": "per_year"}).status_code == 400
    assert client.post(f"{URL}/services", headers=h, json={"name": "Y", "standard_rate": "-1"}).status_code == 400
    r = client.put(f"{URL}/services/{s['id']}", headers=h, json={"name": "Manuscript review T", "unit": "per_page",
                                                                  "standard_rate": 3000, "tax_percent": 5})
    assert r.json()["service"]["unit"] == "per_page" and r.json()["service"]["tax_percent"] == 5
    assert client.delete(f"{URL}/services/{s['id']}", headers=h).status_code == 200


def test_university_card_picks_standard_services_at_its_own_rates(client, db, login_as):
    h = login_as("admin")
    smbt = db.execute(select(Organisation).where(Organisation.slug == "smbt")).scalar_one()
    review = _service(client, h, standard_rate="1000")
    editing = _service(client, h, unit="per_word", standard_rate="2")
    card = client.get(f"{URL}/organisations/{smbt.id}", headers=h).json()
    assert {review["id"], editing["id"]} <= {s["id"] for s in card["available"]}

    r = client.post(f"{URL}/organisations/{smbt.id}/items", headers=h,
                    json={"items": [{"service_id": review["id"]}, {"service_id": editing["id"], "rate": "1.5"}]})
    assert r.status_code == 200, r.text
    items = {i["service_id"]: i for i in r.json()["items"]}
    assert items[review["id"]]["rate"] == 1000 and items[editing["id"]]["rate"] == 1.5
    assert items[editing["id"]]["difference"] == -0.5
    assert review["id"] not in {s["id"] for s in r.json()["available"]}

    item_id = items[review["id"]]["id"]
    u = client.put(f"{URL}/organisations/{smbt.id}/items/{item_id}", headers=h, json={"rate": "850", "notes": "Agreed 2026"})
    assert next(i for i in u.json()["items"] if i["id"] == item_id)["rate"] == 850
    # standard rate changes do not change the university's agreed rate
    client.put(f"{URL}/services/{review['id']}", headers=h, json={"name": review["name"], "unit": "per_document", "standard_rate": 1200})
    again = client.get(f"{URL}/organisations/{smbt.id}", headers=h).json()
    row = next(i for i in again["items"] if i["id"] == item_id)
    assert row["rate"] == 850 and row["standard_rate"] == 1200

    # a service on a card cannot be deleted from the standard list
    d = client.delete(f"{URL}/services/{review['id']}", headers=h)
    assert d.status_code == 400 and "rate card" in d.json()["detail"]
    assert client.post(f"{URL}/organisations/{smbt.id}/items", headers=h, json={"items": [{"service_id": 999999}]}).status_code == 400
    assert client.delete(f"{URL}/organisations/{smbt.id}/items/{item_id}", headers=h).status_code == 200
    assert client.delete(f"{URL}/services/{review['id']}", headers=h).status_code == 200


def test_rate_cards_only_for_universities_and_organisations(client, db, login_as):
    h = login_as("admin")
    team = db.execute(select(Organisation).where(Organisation.kind == "system")).scalar_one()
    s = _service(client, h)
    r = client.post(f"{URL}/organisations/{team.id}/items", headers=h, json={"items": [{"service_id": s["id"]}]})
    assert r.status_code == 400


def test_unit_is_optional(client, login_as):
    h = login_as("admin")
    r = client.post(f"{URL}/services", headers=h, json={"name": f"No unit {uuid.uuid4().hex[:6]}", "standard_rate": 500})
    assert r.status_code == 200, r.text
    s = r.json()["service"]
    assert s["unit"] == "" and s["unit_label"] == ""


def test_university_admin_sees_own_rate_card(client, db, login_as):
    from tests.test_org_isolation import _h, _join, _org, _user
    h = login_as("admin")
    uni = _org(db, "Rate Uni")
    uni_admin = _user(db, "rateadmin")
    _join(db, uni, uni_admin, "admin")
    s = _service(client, h, standard_rate="1000")
    client.post(f"{URL}/organisations/{uni.id}/items", headers=h, json={"items": [{"service_id": s["id"], "rate": "800"}]})
    d = client.get("/api/org/rate-card", headers=_h(uni_admin)).json()
    assert [(i["name"], i["rate"]) for i in d["items"]] == [(s["name"], 800)]
    assert "standard_rate" not in d["items"][0]  # the standard rate stays internal
    smbt_admin_card = client.get("/api/org/rate-card", headers=login_as("teacher1"))
    assert smbt_admin_card.status_code == 403  # members are not admins
