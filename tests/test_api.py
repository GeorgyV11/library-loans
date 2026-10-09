"""Операции контракта: коды ответа, состав полей, авторизация, неверные параметры."""


def test_login_with_wrong_password_is_rejected(client):
    r = client.post("/api/login", json={"login": "librarian", "password": "wrong"})
    assert r.status_code == 401


def test_list_requires_authorization(client):
    assert client.get("/api/loans").status_code == 401


def test_summary_requires_authorization(client):
    assert client.get("/api/summary").status_code == 401


def test_list_returns_requested_page(client, authorized_client):
    r = authorized_client.get("/api/loans?page=1&size=20")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 20
    assert body["total"] == 300
    assert {"id", "title", "reader_name", "due_on", "overdue_days", "fine"} <= body["items"][0].keys()


def test_list_filter_by_status(client, authorized_client):
    body = authorized_client.get("/api/loans?status=overdue&size=100").json()
    assert body["total"] > 0
    assert all(item["overdue"] for item in body["items"])


def test_list_rejects_bad_parameters(client, authorized_client):
    assert authorized_client.get("/api/loans?size=1000").status_code == 422
    assert authorized_client.get("/api/loans?status=lost").status_code == 422


def test_loan_card_has_related_entities(client, authorized_client):
    r = authorized_client.get("/api/loans/1")
    assert r.status_code == 200
    assert {"reader", "copy", "book", "overdue_days", "fine"} <= r.json().keys()


def test_unknown_loan_is_404(client, authorized_client):
    assert authorized_client.get("/api/loans/999999").status_code == 404


def test_summary_fields(client, authorized_client):
    body = authorized_client.get("/api/summary").json()
    assert {"on_hand", "overdue", "overdue_share", "top_books"} <= body.keys()
    assert body["overdue"] <= body["on_hand"]
    loans = [b["loans"] for b in body["top_books"]]
    assert loans == sorted(loans, reverse=True)


def _free_copy_and_clean_reader(c):
    """Свободный экземпляр и читатель без просрочки из малого наполнения."""
    busy = {l["copy_id"] for l in c.get("/api/loans?status=active&size=100").json()["items"]}
    copy_id = next(i for i in range(1, 201) if i not in busy)
    reader_id = next(i for i in range(1, 51) if not c.get(f"/api/readers/{i}").json()["has_overdue"])
    return copy_id, reader_id


def test_issue_and_return_cycle(client, authorized_client):
    copy_id, reader_id = _free_copy_and_clean_reader(authorized_client)
    r = authorized_client.post("/api/loans", json={"reader_id": reader_id, "copy_id": copy_id})
    assert r.status_code == 201
    loan_id = r.json()["id"]
    # тот же экземпляр второй раз не выдаётся
    again = authorized_client.post("/api/loans", json={"reader_id": reader_id, "copy_id": copy_id})
    assert again.status_code == 409
    r = authorized_client.post(f"/api/loans/{loan_id}/return", json={})
    assert r.status_code == 200 and r.json()["returned_on"] is not None
    assert authorized_client.post(f"/api/loans/{loan_id}/return", json={}).status_code == 409


def test_issue_to_reader_with_overdue_is_409(client, authorized_client):
    overdue = authorized_client.get("/api/loans?status=overdue&size=1").json()["items"][0]
    copy_id, _ = _free_copy_and_clean_reader(authorized_client)
    r = authorized_client.post("/api/loans", json={"reader_id": overdue["reader_id"], "copy_id": copy_id})
    assert r.status_code == 409


def test_issue_unknown_reader_is_404(client, authorized_client):
    r = authorized_client.post("/api/loans", json={"reader_id": 999999, "copy_id": 1})
    assert r.status_code == 404
