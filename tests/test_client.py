import asyncio
import base64
from datetime import UTC, datetime

import pytest

from cozyla.client import CozylaError, NotFoundError, encrypt_password
from cozyla.models import TodoCreate, TodoListCreate, TodoUpdate


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
            created_list.id, TodoCreate(title="Vacuum", stars=3, due=due)
        )
        await client.update_todo(created_list.id, todo.id, TodoUpdate(title="Vacuum hall"))
        done = await client.update_todo(created_list.id, todo.id, TodoUpdate(completed=True))
        return todo, done

    todo, done = asyncio.run(run())
    assert todo.due == due
    assert (done.title, done.stars, done.due, done.completed) == ("Vacuum hall", 3, due, True)
    assert cloud.todos[todo.id]["dueDateTime"] == int(due.timestamp() * 1000)


def test_unknown_todo_is_not_found(make_client):
    with pytest.raises(NotFoundError):
        asyncio.run(make_client().update_todo(1, 999, TodoUpdate(title="x")))
