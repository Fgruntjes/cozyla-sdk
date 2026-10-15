import json

import httpx
import pytest

from cozyla.client import CozylaClient

LIST_ID = 2105009974451359744
TODO_ID = 2105029434214182912
CHORE_ID = "c0ffee00000000000000000000000001"


class FakeCloud:
    def __init__(self):
        self.token = "tok-1"
        self.logins = 0
        self.error_code: int | None = None
        self.requests: list[tuple[str, dict, httpx.Headers]] = []
        self.lists = {
            LIST_ID: {
                "listId": LIST_ID,
                "todoListTitle": "Groceries",
                "displayOrder": 1.0,
                "isPreset": 3,
            }
        }
        self.todos = {
            TODO_ID: {
                "todoId": TODO_ID,
                "todoListId": LIST_ID,
                "todoTitle": "Milk",
                "todoStars": 2,
                "isFlag": 0,
                "completeStatus": 0,
                "completeTime": None,
                "dueDateTime": -1,
                "reminderTime": -1,
                "timeUnit": "none",
                "createTime": 1760000000000,
            }
        }
        self.chores = {
            CHORE_ID: {
                "choreUid": CHORE_ID,
                "choreName": "Feed pets",
                "icon": "czl_chores_emoji#_#bone#_#🦴",
                "coins": 5,
                "choreType": "AnyOne",
                "rotateEveryCounts": 1,
                "startDay": "2026-10-12",
                "endDay": "2026-11-12",
                "dueTime": "16:00",
                "repeats": True,
                "repeatsEvery": "Daily",
                "repeatsEveryCounts": 1,
                "repeatsIn": "",
                "repeatsUntil": True,
                "reminder": 30,
                "memberRefs": [{"memberUid": "m-1", "coins": 5}],
                "choreBank": False,
                "description": "",
            }
        }
        self.chore_checks: dict[tuple[str, str, str], str] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content or b"{}")
        self.requests.append((path, body, request.headers))
        if path == "/cal-server/users/cozUsers/signIn":
            self.logins += 1
            if "X-DEVICE-INFO" not in request.headers:
                return self.reply(99, None)
            if body["email"] != "me@example.com" or not body["encryptionPassword"]:
                return self.reply(1001, None)
            return self.reply(0, {"token": self.token, "deviceUid": "dev-1", "memberUid": "m-1"})
        if request.headers.get("Authorization") != self.token or body.get("deviceUid") != "dev-1":
            return self.reply(101, None)
        if self.error_code:
            return self.reply(self.error_code, None)
        handler = getattr(self, path.removeprefix("/cal-server/").replace("/", "_"))
        return self.reply(0, handler(body))

    @staticmethod
    def reply(code, result):
        return httpx.Response(200, json={"code": str(code), "message": "msg", "result": result})

    def users_cozUsersMember_queryMembers(self, body):
        return [{"memberUid": "m-1", "memberName": "Alex", "color": "#f00", "coins": 5}]

    def rewards_todosList_list(self, body):
        return list(self.lists.values())

    def rewards_todosList_create(self, body):
        list_id = max(self.lists) + 1
        self.lists[list_id] = {"listId": list_id, "displayOrder": 2.0, **body}
        return {"listId": list_id, "displayOrder": 2.0}

    def rewards_todosList_update(self, body):
        self.lists[body["listId"]].update(body)

    def rewards_todosList_delete(self, body):
        del self.lists[body["id"]]

    def rewards_todosInfo_list(self, body):
        return list(self.todos.values())

    def rewards_todosInfo_create(self, body):
        todo_id = max(self.todos) + 1
        self.todos[todo_id] = {"todoId": todo_id, "completeStatus": 0, **body}
        return {"todoId": todo_id}

    def rewards_todosInfo_update(self, body):
        self.todos[body["todoId"]].update(body)

    def rewards_todosInfo_checkTodo(self, body):
        self.todos[body["todoId"]].update(completeStatus=body["completeStatus"], completeTime=1)

    def rewards_todosInfo_delete(self, body):
        del self.todos[body["id"]]

    def rewards_chores_myChoresV1(self, body):
        return list(self.chores.values())

    def store_chore(self, body):
        chore = {k: v for k, v in body.items() if k not in ("memberUids", "asATemplate")}
        chore["memberRefs"] = [{"memberUid": m} for m in body["memberUids"]]
        self.chores[chore["choreUid"]] = chore
        return chore

    def rewards_chores_create_v1(self, body):
        return self.store_chore({**body, "choreUid": f"c{len(self.chores):031d}"})

    def rewards_chores_update_v1(self, body):
        return self.store_chore(body)

    def rewards_chores_delete_v1(self, body):
        del self.chores[body["choreUid"]]
        return list(self.chores.values())

    def rewards_chores_choreRecordByDay_v3(self, body):
        day = body["selectDay"]
        return [
            {
                **chore,
                "memberUid": ref["memberUid"],
                "checkDay": day,
                "choreCoins": chore["coins"],
                "status": self.chore_checks.get((uid, ref["memberUid"], day), "pending"),
            }
            for uid, chore in self.chores.items()
            for ref in chore["memberRefs"]
            if chore["startDay"] <= day
        ]

    def rewards_chores_choreCheck_v1(self, body):
        assert body["checkDay"] == body["selectDay"]
        key = (body["choreUid"], body["memberUid"], body["checkDay"])
        self.chore_checks[key] = body["choreStatus"]


@pytest.fixture
def cloud():
    return FakeCloud()


@pytest.fixture
def make_client(cloud):
    def make(email="me@example.com"):
        return CozylaClient(email, "secret", transport=httpx.MockTransport(cloud))

    return make
