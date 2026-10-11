from datetime import datetime
from typing import Annotated

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field

EpochMs = Annotated[datetime | None, BeforeValidator(lambda v: v or None)]


class Member(BaseModel):
    id: str = Field(validation_alias=AliasChoices("memberUid", "id"))
    name: str = Field(validation_alias=AliasChoices("memberName", "name"))
    color: str | None = None
    role: str | None = None
    coins: int | None = None


class TodoList(BaseModel):
    id: int = Field(validation_alias=AliasChoices("listId", "id"))
    title: str = Field(validation_alias=AliasChoices("todoListTitle", "title"))
    color: str | None = Field(None, validation_alias=AliasChoices("todoListColor", "color"))
    icon: str | None = Field(None, validation_alias=AliasChoices("todoListIcon", "icon"))
    display_order: float | None = Field(
        None, validation_alias=AliasChoices("displayOrder", "display_order")
    )
    preset: bool = Field(False, validation_alias=AliasChoices("isPreset", "preset"))


class TodoListCreate(BaseModel):
    title: str = Field(min_length=1)
    color: str | None = None
    icon: str | None = None


class TodoListUpdate(BaseModel):
    title: str | None = Field(None, min_length=1)
    color: str | None = None
    icon: str | None = None


class TodoFields(BaseModel):
    description: str | None = None
    assignee: str | None = Field(None, description="Member id, see GET /members")
    stars: int = Field(0, ge=0, description="Reward stars earned on completion")
    flagged: bool = False
    due: datetime | None = None
    reminder_time: int | None = Field(None, description="Remind this many reminder_unit before due")
    reminder_unit: str | None = Field(None, description='e.g. "day"')


class TodoCreate(TodoFields):
    title: str = Field(min_length=1)


class TodoUpdate(BaseModel):
    title: str | None = Field(None, min_length=1)
    description: str | None = None
    assignee: str | None = None
    stars: int | None = Field(None, ge=0)
    flagged: bool | None = None
    due: datetime | None = None
    reminder_time: int | None = None
    reminder_unit: str | None = None
    completed: bool | None = None


class Todo(TodoFields):
    id: int = Field(validation_alias=AliasChoices("todoId", "id"))
    list_id: int = Field(validation_alias=AliasChoices("todoListId", "list_id"))
    title: str = Field(validation_alias=AliasChoices("todoTitle", "title"))
    description: str | None = Field(None, validation_alias=AliasChoices("todoDesc", "description"))
    assignee: str | None = Field(None, validation_alias=AliasChoices("assignMemberUid", "assignee"))
    stars: int = Field(0, validation_alias=AliasChoices("todoStars", "stars"))
    flagged: bool = Field(False, validation_alias=AliasChoices("isFlag", "flagged"))
    due: EpochMs = Field(None, validation_alias=AliasChoices("dueDateTime", "due"))
    reminder_time: int | None = Field(
        None, validation_alias=AliasChoices("reminderTime", "reminder_time")
    )
    reminder_unit: str | None = Field(
        None, validation_alias=AliasChoices("timeUnit", "reminder_unit")
    )
    completed: bool = Field(False, validation_alias=AliasChoices("completeStatus", "completed"))
    completed_at: EpochMs = Field(
        None, validation_alias=AliasChoices("completeTime", "completed_at")
    )
    created_at: EpochMs = Field(None, validation_alias=AliasChoices("createTime", "created_at"))
    display_order: float | None = Field(
        None, validation_alias=AliasChoices("displayOrder", "display_order")
    )
