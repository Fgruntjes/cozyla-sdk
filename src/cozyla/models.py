from datetime import datetime
from typing import Annotated

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field


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
