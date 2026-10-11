import base64
from datetime import datetime

import httpx
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

from cozyla.models import Member, Todo, TodoCreate, TodoList, TodoListCreate, TodoUpdate

BASE_URL = "https://api.cozylacal.com"
PASSWORD_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuy5lIpsXk9rk3rY/9yxWII+r6oLaMNc5pWw1XrbQaoEn2EUI"
    "0O2QXfF7C7S89FHZKoZlz0MDD0W9X6dCldWpIjZYf+5fjlsrQDOkfJULlwTn8b91pe/NYiv2YWCdfTv1Pq9tTy6rkw4C"
    "66S7PW4rxVmFxWHI1yXvaRVCLe70YFZYrOe+YUzruYRYSi4im77ITdZ7W2HAiQ2RwsJJXd8M2Y8w43aT3NXz1s/mKcpZ"
    "rABgD0MQSdYadmKs6Cdm6H6oBRYuca5YxQSfg2VAu2qliZKEU2nVV2PWAYzDcnH7a2HMv0FylabwP4on7n59yNWe0nH7"
    "L47457IL354qmJnVEQIDAQAB"
)
TOKEN_EXPIRED = {101, 102}


class CozylaError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"Cozyla error {code}: {message}")
        self.code = code
        self.message = message


class NotFoundError(LookupError):
    pass


def encrypt_password(password: str) -> str:
    key = load_der_public_key(base64.b64decode(PASSWORD_KEY))
    return base64.b64encode(key.encrypt(password.encode(), padding.PKCS1v15())).decode()


def _ms(dt: datetime | None) -> int | None:
    return None if dt is None else int(dt.timestamp() * 1000)


def _todo_body(todo: Todo | TodoCreate, list_id: int) -> dict:
    return {
        "todoListId": list_id,
        "todoTitle": todo.title,
        "todoDesc": todo.description,
        "assignMemberUid": todo.assignee,
        "todoStars": todo.stars,
        "isFlag": int(todo.flagged),
        "dueDateTime": _ms(todo.due),
        "reminderTime": todo.reminder_time,
        "timeUnit": todo.reminder_unit,
    }


class CozylaClient:
    def __init__(
        self,
        email: str,
        password: str,
        device_sn: str = "cozyla-sdk",
        timezone: str = "UTC",
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._email = email
        self._password = password
        self._device_sn = device_sn
        self._timezone = timezone
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=20)
        self._token: str | None = None
        self._device_uid = ""

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(self, path: str, body: dict, headers: dict | None = None):
        response = await self._http.post(path, json=body, headers=headers)
        response.raise_for_status()
        envelope = response.json()
        if envelope.get("code") != 0:
            raise CozylaError(envelope.get("code", -1), envelope.get("message") or "")
        return envelope.get("result")

    async def login(self) -> None:
        result = await self._post(
            "/cal-server/users/cozUsers/signIn",
            {
                "email": self._email,
                "encryptionPassword": encrypt_password(self._password),
                "app_id": "Chores",
                "deviceSn": self._device_sn,
                "loginClient": "DEVICE",
                "deviceName": "cozyla-sdk",
            },
        )
        self._token = result["token"]
        self._device_uid = result["deviceUid"]

    async def call(self, path: str, body: dict | None = None, *, retry: bool = True):
        if self._token is None:
            await self.login()
        headers = {"Authorization": self._token, "timeZoneId": self._timezone}
        try:
            return await self._post(path, {**(body or {}), "deviceUid": self._device_uid}, headers)
        except CozylaError as e:
            if retry and e.code in TOKEN_EXPIRED:
                self._token = None
                return await self.call(path, body, retry=False)
            raise

    async def list_members(self) -> list[Member]:
        result = await self.call("/cal-server/users/cozUsersMember/queryMembers", {"app": 1})
        return [Member.model_validate(m) for m in result or []]

    async def list_todo_lists(self) -> list[TodoList]:
        result = await self.call("/cal-server/rewards/todosList/list")
        return [TodoList.model_validate(t) for t in result or []]

    async def get_todo_list(self, list_id: int) -> TodoList:
        for todo_list in await self.list_todo_lists():
            if todo_list.id == list_id:
                return todo_list
        raise NotFoundError(f"todo list {list_id}")

    async def create_todo_list(self, data: TodoListCreate) -> TodoList:
        result = await self.call(
            "/cal-server/rewards/todosList/create",
            {
                "todoListTitle": data.title,
                "todoListColor": data.color,
                "todoListIcon": data.icon,
                "version": 0,
            },
        )
        return TodoList(
            **data.model_dump(), id=result["listId"], display_order=result.get("displayOrder")
        )

    async def update_todo_list(self, list_id: int, changes: dict) -> TodoList:
        updated = (await self.get_todo_list(list_id)).model_copy(update=changes)
        await self.call(
            "/cal-server/rewards/todosList/update",
            {
                "listId": list_id,
                "todoListTitle": updated.title,
                "todoListColor": updated.color,
                "todoListIcon": updated.icon,
            },
        )
        return updated

    async def delete_todo_list(self, list_id: int) -> None:
        await self.get_todo_list(list_id)
        await self.call("/cal-server/rewards/todosList/delete", {"id": list_id})

    async def list_todos(self, list_id: int | None = None) -> list[Todo]:
        result = await self.call("/cal-server/rewards/todosInfo/list")
        todos = [Todo.model_validate(t) for t in result or []]
        return [t for t in todos if list_id is None or t.list_id == list_id]

    async def get_todo(self, list_id: int, todo_id: int) -> Todo:
        for todo in await self.list_todos(list_id):
            if todo.id == todo_id:
                return todo
        raise NotFoundError(f"todo {todo_id} in list {list_id}")

    async def create_todo(self, list_id: int, data: TodoCreate) -> Todo:
        await self.get_todo_list(list_id)
        result = await self.call("/cal-server/rewards/todosInfo/create", _todo_body(data, list_id))
        return await self.get_todo(list_id, result["todoId"])

    async def update_todo(self, list_id: int, todo_id: int, data: TodoUpdate) -> Todo:
        current = await self.get_todo(list_id, todo_id)
        changes = data.model_dump(exclude_unset=True)
        completed = changes.pop("completed", None)
        if changes:
            body = _todo_body(current.model_copy(update=changes), list_id)
            await self.call("/cal-server/rewards/todosInfo/update", {"todoId": todo_id, **body})
        if completed is not None and completed != current.completed:
            await self.call(
                "/cal-server/rewards/todosInfo/checkTodo",
                {"todoId": todo_id, "completeStatus": int(completed)},
            )
        return await self.get_todo(list_id, todo_id)

    async def delete_todo(self, list_id: int, todo_id: int) -> None:
        await self.get_todo(list_id, todo_id)
        await self.call("/cal-server/rewards/todosInfo/delete", {"id": todo_id})
