import base64
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

from cozyla.models import (
    Chore,
    ChoreCreate,
    ChoreOccurrence,
    ChoreUpdate,
    Member,
    Todo,
    TodoCreate,
    TodoList,
    TodoListCreate,
    TodoUpdate,
    repeat_to_cloud,
)

BASE_URL = "https://api.cozylacal.com"
PASSWORD_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuy5lIpsXk9rk3rY/9yxWII+r6oLaMNc5pWw1XrbQaoEn2EUI"
    "0O2QXfF7C7S89FHZKoZlz0MDD0W9X6dCldWpIjZYf+5fjlsrQDOkfJULlwTn8b91pe/NYiv2YWCdfTv1Pq9tTy6rkw4C"
    "66S7PW4rxVmFxWHI1yXvaRVCLe70YFZYrOe+YUzruYRYSi4im77ITdZ7W2HAiQ2RwsJJXd8M2Y8w43aT3NXz1s/mKcpZ"
    "rABgD0MQSdYadmKs6Cdm6H6oBRYuca5YxQSfg2VAu2qliZKEU2nVV2PWAYzDcnH7a2HMv0FylabwP4on7n59yNWe0nH7"
    "L47457IL354qmJnVEQIDAQAB"
)
TOKEN_EXPIRED = {101, 102}
CHORE_DEVICE_ID = "db3860b5-9178-427a-894e-d9dfed2bcf5b"
CHORE_TYPES = {"everyone": "Everyone", "anyone": "AnyOne", "rotate": "Rotate"}


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


def _ms(dt: datetime | None) -> int:
    return -1 if dt is None else int(dt.timestamp() * 1000)


def _reminder_preset(minutes: int | None) -> str:
    presets = {0: "on_time", 5: "minutes_before_5", 30: "minutes_before_30"}
    presets |= {60: "one_hour_before", 1440: "one_day_before"}
    if minutes is None:
        return "none"
    if minutes in presets:
        return presets[minutes]
    for unit, size in (("week", 10080), ("day", 1440), ("hour", 60)):
        if minutes % size == 0:
            return f"custom_{unit}"
    return "custom_minute"


def _todo_body(todo: Todo | TodoCreate, list_id: str) -> dict:
    return {
        "todoListId": int(list_id),
        "todoTitle": todo.title,
        "todoDesc": todo.description or "",
        "assignMemberUid": todo.assignee,
        "todoStars": todo.stars,
        "isFlag": int(todo.flagged),
        "dueDateTime": _ms(todo.due),
        "reminderTime": -1 if todo.reminder_minutes is None else todo.reminder_minutes,
        "timeUnit": _reminder_preset(todo.reminder_minutes),
    }


def _chore_body(chore: Chore | ChoreCreate) -> dict:
    return {
        "icon": chore.icon,
        "choreName": chore.name,
        "coins": chore.stars,
        "choreType": CHORE_TYPES[chore.type],
        "rotateEveryCounts": chore.rotate_every,
        "startDay": chore.start.isoformat(),
        "endDay": (chore.end or chore.start).isoformat(),
        "dueTime": chore.due_time,
        "repeats": chore.repeat is not None,
        **repeat_to_cloud(chore.repeat),
        "repeatsUntil": chore.end is None,
        "choreDeviceId": CHORE_DEVICE_ID,
        "reminder": -1 if chore.reminder_minutes is None else chore.reminder_minutes,
        "memberUids": chore.members,
        "choreBank": chore.chore_bank,
        "description": chore.description,
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

    def today(self) -> date:
        return datetime.now(ZoneInfo(self._timezone)).date()

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict:
        device_info = {
            "deviceSn": self._device_sn,
            "deviceUid": self._device_uid,
            "deviceVersion": "cozyla-sdk",
            "deviceType": "Device",
            "modelName": "cozyla-sdk",
            "deviceName": "cozyla-sdk",
            "osVersion": "14",
            "appVersion": "1.0.0",
            "packageName": "com.cozyla.id",
            "deviceBrand": "Cozyla",
            "deviceManufacturer": "Cozyla",
            "screenResolution": "1920x1080",
            "timeZoneId": self._timezone,
            "loginClient": "DEVICE",
        }
        headers = {
            "timeZoneId": self._timezone,
            "modelName": "cozyla-sdk",
            "platform": "Android",
            "calendarOsVersion": "cozyla-sdk",
            "Accept-Language": "en-US,en;q=0.9",
            "X-DEVICE-INFO": base64.b64encode(json.dumps(device_info).encode()).decode(),
        }
        if self._token:
            headers["Authorization"] = self._token
        return headers

    async def _post(self, path: str, body: dict):
        response = await self._http.post(path, json=body, headers=self._headers())
        response.raise_for_status()
        envelope = response.json()
        code = int(envelope.get("code", -1))
        if code != 0:
            raise CozylaError(code, envelope.get("message") or "")
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
        try:
            return await self._post(path, {**(body or {}), "deviceUid": self._device_uid})
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

    async def get_todo_list(self, list_id: str) -> TodoList:
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

    async def update_todo_list(self, list_id: str, changes: dict) -> TodoList:
        updated = (await self.get_todo_list(list_id)).model_copy(update=changes)
        await self.call(
            "/cal-server/rewards/todosList/update",
            {
                "listId": int(list_id),
                "todoListTitle": updated.title,
                "todoListColor": updated.color,
                "todoListIcon": updated.icon,
            },
        )
        return updated

    async def delete_todo_list(self, list_id: str) -> None:
        await self.get_todo_list(list_id)
        await self.call("/cal-server/rewards/todosList/delete", {"id": int(list_id)})

    async def list_todos(self, list_id: str | None = None) -> list[Todo]:
        result = await self.call("/cal-server/rewards/todosInfo/list")
        todos = [Todo.model_validate(t) for t in result or []]
        return [t for t in todos if list_id is None or t.list_id == list_id]

    async def get_todo(self, list_id: str, todo_id: str) -> Todo:
        for todo in await self.list_todos(list_id):
            if todo.id == todo_id:
                return todo
        raise NotFoundError(f"todo {todo_id} in list {list_id}")

    async def create_todo(self, list_id: str, data: TodoCreate) -> Todo:
        await self.get_todo_list(list_id)
        result = await self.call("/cal-server/rewards/todosInfo/create", _todo_body(data, list_id))
        return await self.get_todo(list_id, str(result["todoId"]))

    async def update_todo(self, list_id: str, todo_id: str, data: TodoUpdate) -> Todo:
        current = await self.get_todo(list_id, todo_id)
        changes = data.model_dump(exclude_unset=True)
        completed = changes.pop("completed", None)
        if changes:
            body = _todo_body(current.model_copy(update=changes), list_id)
            await self.call(
                "/cal-server/rewards/todosInfo/update", {"todoId": int(todo_id), **body}
            )
        if completed is not None and completed != current.completed:
            await self.call(
                "/cal-server/rewards/todosInfo/checkTodo",
                {"todoId": int(todo_id), "completeStatus": int(completed)},
            )
        return await self.get_todo(list_id, todo_id)

    async def delete_todo(self, list_id: str, todo_id: str) -> None:
        await self.get_todo(list_id, todo_id)
        await self.call("/cal-server/rewards/todosInfo/delete", {"id": int(todo_id)})

    async def list_chores(self) -> list[Chore]:
        result = await self.call("/cal-server/rewards/chores/myChoresV1")
        return [Chore.model_validate(c) for c in result or []]

    async def get_chore(self, chore_id: str) -> Chore:
        for chore in await self.list_chores():
            if chore.id == chore_id:
                return chore
        raise NotFoundError(f"chore {chore_id}")

    async def create_chore(self, data: ChoreCreate) -> Chore:
        result = await self.call(
            "/cal-server/rewards/chores/create/v1", {**_chore_body(data), "asATemplate": False}
        )
        return Chore.model_validate(result)

    async def update_chore(self, chore_id: str, data: ChoreUpdate) -> Chore:
        current = await self.get_chore(chore_id)
        updated = current.model_copy(update=data.model_dump(exclude_unset=True))
        result = await self.call(
            "/cal-server/rewards/chores/update/v1", {"choreUid": chore_id, **_chore_body(updated)}
        )
        return Chore.model_validate(result)

    async def delete_chore(self, chore_id: str) -> None:
        await self.get_chore(chore_id)
        await self.call("/cal-server/rewards/chores/delete/v1", {"choreUid": chore_id})

    async def list_chore_occurrences(self, day: date) -> list[ChoreOccurrence]:
        result = await self.call(
            "/cal-server/rewards/chores/choreRecordByDay/v3", {"selectDay": day.isoformat()}
        )
        return [ChoreOccurrence.model_validate(r) for r in result or []]

    async def set_chore_completed(
        self, chore_id: str, day: date, member_id: str, completed: bool
    ) -> None:
        occurrences = await self.list_chore_occurrences(day)
        if not any(o.chore_id == chore_id and o.member == member_id for o in occurrences):
            raise NotFoundError(f"chore {chore_id} for member {member_id} on {day}")
        await self.call(
            "/cal-server/rewards/chores/choreCheck/v1",
            {
                "choreUid": chore_id,
                "memberUid": member_id,
                "checkFrom": "dayPage",
                "choreStatus": "completed" if completed else "pending",
                "checkDay": day.isoformat(),
                "selectDay": day.isoformat(),
            },
        )
