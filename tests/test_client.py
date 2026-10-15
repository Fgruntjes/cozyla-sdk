import asyncio
import base64
from datetime import UTC, date, datetime

import pytest
from conftest import CHORE_ID, LIST_ID, TODO_ID

from cozyla.client import CozylaError, NotFoundError, encrypt_password
from cozyla.models import (
    ChoreCreate,
    ChoreUpdate,
    Repeat,
    TodoCreate,
    TodoListCreate,
    TodoUpdate,
)


def test_password_is_rsa_encrypted():
    encrypted = encrypt_password("secret")
    assert len(base64.b64decode(encrypted)) == 256
    assert encrypted != encrypt_password("secret")


def test_requests_carry_raw_token_and_device_uid(cloud, make_client):
    lists = asyncio.run(make_client().list_todo_lists())
    assert [todo_list.title for todo_list in lists] == ["Groceries"]
    login, (path, body, headers) = cloud.requests
    assert "secret" not in str(login[1])
    assert headers["Authorization"] == "tok-1"
    assert body["deviceUid"] == "dev-1"


def test_expired_token_logs_in_again_once(cloud, make_client):
    async def run():
        client = make_client()
        await client.list_todo_lists()
        cloud.token = "tok-2"
        return await client.list_todo_lists()

    assert len(asyncio.run(run())) == 1
    assert cloud.logins == 2


def test_bad_credentials_raise(make_client):
    with pytest.raises(CozylaError) as error:
        asyncio.run(make_client(email="wrong@example.com").list_todo_lists())
    assert error.value.code == 1001


def test_todo_lifecycle(cloud, make_client):
    due = datetime(2026, 10, 12, 21, 59, tzinfo=UTC)

    async def run():
        client = make_client()
        created_list = await client.create_todo_list(TodoListCreate(title="Chores", icon="broom"))
        todo = await client.create_todo(
            created_list.id, TodoCreate(title="Vacuum", stars=3, due=due, reminder_minutes=1440)
        )
        await client.update_todo(created_list.id, todo.id, TodoUpdate(title="Vacuum hall"))
        done = await client.update_todo(created_list.id, todo.id, TodoUpdate(completed=True))
        return todo, done

    todo, done = asyncio.run(run())
    assert (todo.due, todo.reminder_minutes) == (due, 1440)
    assert (done.title, done.stars, done.due, done.completed) == ("Vacuum hall", 3, due, True)
    stored = cloud.todos[int(todo.id)]
    assert (stored["dueDateTime"], stored["timeUnit"]) == (
        int(due.timestamp() * 1000),
        "one_day_before",
    )


def test_unset_values_read_as_none(make_client):
    todo = asyncio.run(make_client().get_todo(str(LIST_ID), str(TODO_ID)))
    assert (todo.id, todo.due, todo.reminder_minutes) == (str(TODO_ID), None, None)


def test_unknown_todo_is_not_found(make_client):
    with pytest.raises(NotFoundError):
        asyncio.run(make_client().update_todo(str(LIST_ID), "999", TodoUpdate(title="x")))


def test_chore_lifecycle(cloud, make_client):
    day = date(2026, 10, 14)
    weekly = Repeat(frequency="weekly", days=["monday", "wednesday"])

    async def run():
        client = make_client()
        chore = await client.create_chore(
            ChoreCreate(name="Vacuum", icon="broom", members=["m-1"], start=day, repeat=weekly)
        )
        updated = await client.update_chore(chore.id, ChoreUpdate(stars=3))
        await client.set_chore_completed(chore.id, day, "m-1", True)
        occurrences = await client.list_chore_occurrences(day)
        await client.delete_chore(chore.id)
        return chore, updated, occurrences, await client.list_chores()

    chore, updated, occurrences, remaining = asyncio.run(run())
    assert (chore.repeat, chore.end, chore.members) == (weekly, None, ["m-1"])
    assert (updated.stars, updated.name, updated.repeat) == (3, "Vacuum", weekly)
    created = next(body for path, body, _ in cloud.requests if path.endswith("chores/create/v1"))
    assert (created["repeatsEvery"], created["repeatsIn"], created["repeatsUntil"]) == (
        "Weekly",
        "Monday,Wednesday",
        True,
    )
    mine = [o for o in occurrences if o.chore_id == chore.id]
    assert [(o.member, o.day, o.status, o.stars) for o in mine] == [("m-1", day, "completed", 3)]
    assert [c.id for c in remaining] == [CHORE_ID]


def test_cloud_chore_reads_as_model(make_client):
    chore = asyncio.run(make_client().get_chore(CHORE_ID))
    assert (chore.name, chore.type, chore.end, chore.reminder_minutes) == (
        "Feed pets",
        "anyone",
        None,
        30,
    )
    assert chore.repeat == Repeat(frequency="daily")
