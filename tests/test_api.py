import httpx
import pytest
from conftest import LIST_ID
from fastapi.testclient import TestClient

from cozyla import api
from cozyla.client import CozylaClient

AUTH = {"Authorization": "Bearer api-token"}


@pytest.fixture
def http(cloud, monkeypatch):
    monkeypatch.setenv("COZYLA_API_TOKEN", "api-token")
    monkeypatch.setattr(
        api,
        "client_from_env",
        lambda: CozylaClient("me@example.com", "secret", transport=httpx.MockTransport(cloud)),
    )
    with TestClient(api.app) as client:
        yield client


def test_routes_require_token(http):
    assert http.get("/health").status_code == 200
    assert http.get("/todo-lists").status_code == 401
    assert http.get("/todo-lists", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_todo_crud(http, cloud):
    created = http.post(
        f"/todo-lists/{LIST_ID}/items", json={"title": "Eggs", "flagged": True}, headers=AUTH
    )
    assert created.status_code == 201
    todo = created.json()
    assert (todo["title"], todo["flagged"], todo["completed"]) == ("Eggs", True, False)

    patched = http.patch(
        f"/todo-lists/{LIST_ID}/items/{todo['id']}", json={"completed": True}, headers=AUTH
    )
    assert patched.json()["completed"] is True

    items = http.get(f"/todo-lists/{LIST_ID}/items", headers=AUTH).json()
    assert [item["title"] for item in items] == ["Milk", "Eggs"]

    assert http.delete(f"/todo-lists/{LIST_ID}/items/{todo['id']}", headers=AUTH).status_code == 204
    assert int(todo["id"]) not in cloud.todos


def test_missing_list_is_404(http):
    response = http.get("/todo-lists/42/items", headers=AUTH)
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_cloud_error_is_502(http, cloud):
    cloud.error_code = 500
    assert http.get("/todo-lists", headers=AUTH).status_code == 502


def test_chore_completion(http, cloud):
    created = http.post(
        "/chores",
        json={"name": "Vacuum", "icon": "broom", "members": ["m-1"], "start": "2026-10-14"},
        headers=AUTH,
    )
    assert created.status_code == 201
    chore_id = created.json()["id"]

    completion = f"/chores/{chore_id}/completions/2026-10-14/m-1"
    assert http.put(completion, headers=AUTH).status_code == 204
    day = http.get("/chores/occurrences", params={"day": "2026-10-14"}, headers=AUTH).json()
    assert {(o["chore_id"], o["status"]) for o in day} >= {(chore_id, "completed")}

    assert http.delete(completion, headers=AUTH).status_code == 204
    assert cloud.chore_checks[(chore_id, "m-1", "2026-10-14")] == "pending"

    assert (
        http.put(f"/chores/{chore_id}/completions/2026-10-14/m-9", headers=AUTH).status_code == 404
    )
    assert http.delete(f"/chores/{chore_id}", headers=AUTH).status_code == 204
    assert http.get(f"/chores/{chore_id}", headers=AUTH).status_code == 404


def test_routine_completion(http, cloud):
    created = http.post(
        "/routines",
        json={"members": ["m-1"], "name": "Read", "icon": "book", "period": "evening"},
        headers=AUTH,
    )
    assert created.status_code == 201
    [routine] = created.json()

    completion = f"/routines/{routine['id']}/completions/2026-10-20"
    assert http.put(completion, headers=AUTH).status_code == 204
    day = http.get("/routines/occurrences", params={"day": "2026-10-20"}, headers=AUTH).json()
    assert {"routine_id": routine["id"], "status": "completed"}.items() <= next(
        o for o in day if o["routine_id"] == routine["id"]
    ).items()
    assert http.delete(completion, headers=AUTH).status_code == 204
    assert cloud.routine_checks[(int(routine["id"]), "2026-10-20")] == "pending"

    assert http.delete(f"/routines/{routine['id']}", headers=AUTH).status_code == 204
    assert http.get(f"/routines/{routine['id']}", headers=AUTH).status_code == 404


def test_reward_redemption(http, cloud):
    reward = http.post(
        "/rewards",
        json={"name": "Ice cream", "stars": 5, "members": ["m-1"], "needs_approval": True},
        headers=AUTH,
    ).json()

    redeemed = http.post(
        f"/rewards/{reward['id']}/redemptions", json={"member": "m-1"}, headers=AUTH
    )
    assert redeemed.status_code == 201
    redemption = redeemed.json()
    pending = http.get("/redemptions", params={"status": "pending_approval"}, headers=AUTH).json()
    assert [r["id"] for r in pending] == [redemption["id"]]

    assert http.post(f"/redemptions/{redemption['id']}/approve", headers=AUTH).status_code == 204
    assert http.get(f"/redemptions/{redemption['id']}", headers=AUTH).json()["status"] == "done"

    assert http.delete(f"/redemptions/{redemption['id']}", headers=AUTH).status_code == 204
    assert http.post(f"/redemptions/{redemption['id']}/deny", headers=AUTH).status_code == 404
    assert http.delete(f"/rewards/{reward['id']}", headers=AUTH).status_code == 204
