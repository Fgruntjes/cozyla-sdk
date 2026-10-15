from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field, model_validator


def _unset_to_none(value):
    return None if value is None or (isinstance(value, int) and value < 0) else value


Id = Annotated[str, BeforeValidator(str)]
EpochMs = Annotated[datetime | None, BeforeValidator(_unset_to_none)]
Minutes = Annotated[int | None, BeforeValidator(_unset_to_none)]


def _alias(cloud: str, name: str) -> AliasChoices:
    return AliasChoices(cloud, name)


class Member(BaseModel):
    id: str = Field(validation_alias=_alias("memberUid", "id"))
    name: str = Field(validation_alias=_alias("memberName", "name"))
    role: str | None = None
    color: str | None = None
    coins: int | None = None


class TodoList(BaseModel):
    id: Id = Field(validation_alias=_alias("listId", "id"))
    title: str = Field(validation_alias=_alias("todoListTitle", "title"))
    color: str | None = Field(None, validation_alias=_alias("todoListColor", "color"))
    icon: str | None = Field(None, validation_alias=_alias("todoListIcon", "icon"))
    display_order: float | None = Field(
        None, validation_alias=_alias("displayOrder", "display_order")
    )


class TodoListCreate(BaseModel):
    title: str = Field(min_length=1)
    color: str | None = Field(None, examples=["#E9B14D"])
    icon: str | None = Field(None, examples=["icon_todolist_preset9"])


class TodoListUpdate(BaseModel):
    title: str | None = Field(None, min_length=1)
    color: str | None = None
    icon: str | None = None


class TodoCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    assignee: str | None = Field(None, description="Member id, see GET /members")
    stars: int = Field(0, ge=0, description="Reward stars earned on completion")
    flagged: bool = False
    due: datetime | None = None
    reminder_minutes: int | None = Field(
        None, ge=0, description="Remind this many minutes before due; needs due"
    )


class TodoUpdate(BaseModel):
    title: str | None = Field(None, min_length=1)
    description: str | None = None
    assignee: str | None = None
    stars: int | None = Field(None, ge=0)
    flagged: bool | None = None
    due: datetime | None = None
    reminder_minutes: int | None = Field(None, ge=0)
    completed: bool | None = None


class Todo(BaseModel):
    id: Id = Field(validation_alias=_alias("todoId", "id"))
    list_id: Id = Field(validation_alias=_alias("todoListId", "list_id"))
    title: str = Field(validation_alias=_alias("todoTitle", "title"))
    description: str | None = Field(None, validation_alias=_alias("todoDesc", "description"))
    assignee: str | None = Field(None, validation_alias=_alias("assignMemberUid", "assignee"))
    stars: int = Field(0, validation_alias=_alias("todoStars", "stars"))
    flagged: bool = Field(False, validation_alias=_alias("isFlag", "flagged"))
    due: EpochMs = Field(None, validation_alias=_alias("dueDateTime", "due"))
    reminder_minutes: Minutes = Field(
        None, validation_alias=_alias("reminderTime", "reminder_minutes")
    )
    completed: bool = Field(False, validation_alias=_alias("completeStatus", "completed"))
    created_at: EpochMs = Field(None, validation_alias=_alias("createTime", "created_at"))
    display_order: float | None = Field(
        None, validation_alias=_alias("displayOrder", "display_order")
    )


class Repeat(BaseModel):
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    interval: int = Field(1, ge=1, description="Every this many days, weeks or months")
    days: list[str] = Field(
        [],
        examples=[["monday", "wednesday"]],
        description="Weekday names for weekly, days of the month for monthly",
    )


def repeat_from_cloud(chore: dict) -> Repeat | None:
    if not chore.get("repeats", True):
        return None
    return Repeat(
        frequency=chore["repeatsEvery"].lower(),
        interval=chore.get("repeatsEveryCounts") or 1,
        days=[day.lower() for day in (chore.get("repeatsIn") or "").split(",") if day],
    )


def repeat_to_cloud(repeat: Repeat | None) -> dict:
    repeat = repeat or Repeat()
    return {
        "repeatsEvery": repeat.frequency.capitalize(),
        "repeatsEveryCounts": repeat.interval,
        "repeatsIn": ",".join(day.capitalize() for day in repeat.days),
    }


class Repeating(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _read_cloud_repeat(cls, data):
        if isinstance(data, dict) and "repeatsEvery" in data:
            return {**data, "repeat": repeat_from_cloud(data)}
        return data


ChoreType = Literal["everyone", "anyone", "rotate"]
ChoreStatus = Literal["pending", "completed", "expired"]


class ChoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    icon: str = Field(examples=["czl_chores_emoji#_#broom#_#\N{BROOM}"])
    members: list[str] = Field([], description="Member ids, see GET /members")
    type: ChoreType = Field(
        "everyone",
        description="everyone: each member does it; anyone: first to finish; rotate: take turns",
    )
    rotate_every: int = Field(1, ge=1, description="Rotate the assignee every this many times")
    chore_bank: bool = Field(False, description="Unassigned chore any member can claim")
    stars: int = Field(1, ge=0, description="Stars earned per completion")
    start: date = Field(default_factory=date.today)
    end: date | None = Field(None, description="Last day; none repeats forever")
    due_time: str = Field("23:59", pattern=r"^\d{2}:\d{2}$")
    repeat: Repeat | None = Field(None, description="None is a one-off chore from start to end")
    reminder_minutes: int | None = Field(None, ge=0)
    description: str = ""


class ChoreUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    icon: str | None = None
    members: list[str] | None = None
    type: ChoreType | None = None
    rotate_every: int | None = Field(None, ge=1)
    chore_bank: bool | None = None
    stars: int | None = Field(None, ge=0)
    start: date | None = None
    end: date | None = None
    due_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    repeat: Repeat | None = None
    reminder_minutes: int | None = Field(None, ge=0)
    description: str | None = None


class Chore(Repeating):
    id: str = Field(validation_alias=_alias("choreUid", "id"))
    name: str = Field(validation_alias=_alias("choreName", "name"))
    icon: str
    members: list[str] = Field([], validation_alias=_alias("memberRefs", "members"))
    type: ChoreType = Field(validation_alias=_alias("choreType", "type"))
    rotate_every: int = Field(1, validation_alias=_alias("rotateEveryCounts", "rotate_every"))
    chore_bank: bool = Field(False, validation_alias=_alias("choreBank", "chore_bank"))
    stars: int = Field(validation_alias=_alias("coins", "stars"))
    start: date = Field(validation_alias=_alias("startDay", "start"))
    end: date | None = Field(None, validation_alias=_alias("endDay", "end"))
    due_time: str = Field(validation_alias=_alias("dueTime", "due_time"))
    reminder_minutes: Minutes = Field(None, validation_alias=_alias("reminder", "reminder_minutes"))
    repeat: Repeat | None = None
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def _read_cloud_chore(cls, data):
        if isinstance(data, dict) and "choreUid" in data:
            data = {
                **data,
                "choreType": data["choreType"].lower(),
                "memberRefs": [ref["memberUid"] for ref in data.get("memberRefs") or []],
                "description": data.get("description") or "",
            }
            if data.get("repeats") and data.get("repeatsUntil"):
                data["endDay"] = None
        return data


class ChoreOccurrence(BaseModel):
    chore_id: str = Field(validation_alias=_alias("choreUid", "chore_id"))
    member: str = Field(validation_alias=_alias("memberUid", "member"))
    day: date = Field(validation_alias=_alias("checkDay", "day"))
    name: str = Field(validation_alias=_alias("choreName", "name"))
    icon: str = ""
    stars: int = Field(validation_alias=_alias("choreCoins", "stars"))
    due_time: str = Field(validation_alias=_alias("dueTime", "due_time"))
    status: ChoreStatus
