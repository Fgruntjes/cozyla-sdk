import asyncio
import base64
from datetime import UTC, date, datetime

import pytest
from conftest import CHORE_ID, LIST_ID, REWARD_ID, ROUTINE_ID, TODO_ID

from cozyla.client import CozylaError, NotFoundError, encrypt_password
from cozyla.models import (
    ChoreCreate,
    ChoreUpdate,
    Repeat,
    RewardCreate,
    RewardUpdate,
    RoutineCreate,
    RoutineUpdate,
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


def test_routine_lifecycle(cloud, make_client):
    day = date(2026, 10, 14)

    async def run():
        client = make_client()
        created = await client.create_routines(
            RoutineCreate(
                members=["m-1", "m-2"],
                name="Brush teeth",
                icon="tooth",
                period="evening",
                start=day,
            )
        )
        routine = created[1]
        updated = await client.update_routine(routine.id, RoutineUpdate(stars=2))
        await client.set_routine_completed(routine.id, day, True)
        occurrences = await client.list_routine_occurrences(day)
        await client.delete_routine(routine.id)
        return created, updated, occurrences, await client.list_routines()

    created, updated, occurrences, remaining = asyncio.run(run())
    assert [(r.member, r.period, r.repeat) for r in created] == [
        ("m-1", "evening", Repeat()),
        ("m-2", "evening", Repeat()),
    ]
    assert (updated.name, updated.stars) == ("Brush teeth", 2)
    stored = cloud.routines[int(created[0].id)]
    assert (stored["routineType"], stored["repeatsEvery"]) == ("Evening", "Daily")
    statuses = {(o.routine_id, o.status) for o in occurrences}
    assert (created[1].id, "completed") in statuses
    assert (created[0].id, "pending") in statuses
    assert [r.id for r in remaining] == [str(ROUTINE_ID), created[0].id]


def test_reward_redemption_lifecycle(cloud, make_client):
    async def run():
        client = make_client()
        reward = await client.create_reward(
            RewardCreate(name="Ice cream", stars=5, members=["m-1"], needs_approval=True)
        )
        renamed = await client.update_reward(reward.id, RewardUpdate(name="Big ice cream"))
        denied = await client.redeem_reward(reward.id, "m-1")
        await client.approve_redemption(denied.id, False)
        approved = await client.redeem_reward(reward.id, "m-1")
        await client.approve_redemption(approved.id, True)
        history = await client.list_redemptions(member="m-1")
        await client.undo_redemption(approved.id)
        await client.delete_reward(reward.id)
        return reward, renamed, denied, history, await client.list_rewards()

    reward, renamed, denied, history, remaining = asyncio.run(run())
    assert (reward.stars, reward.needs_approval, reward.members) == (5, True, ["m-1"])
    assert (renamed.name, renamed.stars) == ("Big ice cream", 5)
    assert (denied.reward_id, denied.member, denied.status) == (
        reward.id,
        "m-1",
        "pending_approval",
    )
    assert [(r.name, r.status) for r in history] == [("Big ice cream", "done")]
    assert cloud.redemptions == {}
    assert [r.id for r in remaining] == [REWARD_ID]


def test_catalog_reward_keeps_product_on_update(cloud, make_client):
    asyncio.run(make_client().update_reward(REWARD_ID, RewardUpdate(stars=12)))
    update = next(body for path, body, _ in cloud.requests if path.endswith("rewards/update"))
    assert (update["productId"], update["coins"], update["renewable"]) == (
        "2044319487125233670",
        12,
        1,
    )


def test_one_off_chore_made_monthly_repeats_forever(cloud, make_client):
    day = date(2026, 10, 14)
    monthly = Repeat(frequency="monthly", days=["1", "15"])

    async def run():
        client = make_client()
        chore = await client.create_chore(
            ChoreCreate(name="Pay rent", icon="money", members=["m-1"], start=day)
        )
        return chore, await client.update_chore(chore.id, ChoreUpdate(repeat=monthly))

    one_off, monthly_chore = asyncio.run(run())
    assert (one_off.repeat, one_off.end) == (None, day)
    assert (monthly_chore.repeat, monthly_chore.end) == (monthly, None)
    stored = cloud.chores[monthly_chore.id]
    assert (stored["repeatsIn"], stored["repeatsUntil"]) == ("1,15", True)
