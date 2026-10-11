import json

import httpx
import pytest

from cozyla.client import CozylaClient


class FakeCloud:
    def __init__(self):
        self.token = "tok-1"
        self.logins = 0
        self.error_code: int | None = None
        self.requests: list[tuple[str, dict, httpx.Headers]] = []
        self.lists = {
            1: {"listId": 1, "todoListTitle": "Groceries", "displayOrder": 1.0, "isPreset": 0}
        }
        self.todos = {
            10: {
                "todoId": 10,
                "todoListId": 1,
                "todoTitle": "Milk",
                "todoStars": 2,
                "isFlag": 0,
                "completeStatus": 0,
                "completeTime": 0,
                "dueDateTime": 1760131140000,
                "createTime": 1760000000000,
            }
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content or b"{}")
        self.requests.append((path, body, request.headers))
        if path == "/cal-server/users/cozUsers/signIn":
            self.logins += 1
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
        return httpx.Response(200, json={"code": code, "message": "msg", "result": result})

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


@pytest.fixture
def cloud():
    return FakeCloud()


@pytest.fixture
def make_client(cloud):
    def make(email="me@example.com"):
        return CozylaClient(email, "secret", transport=httpx.MockTransport(cloud))

    return make
