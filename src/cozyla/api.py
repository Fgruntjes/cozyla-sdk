import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cozyla.client import CozylaClient, CozylaError, NotFoundError
from cozyla.models import (
    Chore,
    ChoreCreate,
    ChoreOccurrence,
    ChoreUpdate,
    Member,
    Redemption,
    RedemptionCreate,
    RedemptionStatus,
    Reward,
    RewardCreate,
    RewardUpdate,
    Routine,
    RoutineCreate,
    RoutineOccurrence,
    RoutineUpdate,
    Todo,
    TodoCreate,
    TodoList,
    TodoListCreate,
    TodoListUpdate,
    TodoUpdate,
)


def client_from_env() -> CozylaClient:
    return CozylaClient(
        email=os.environ["COZYLA_EMAIL"],
        password=os.environ["COZYLA_PASSWORD"],
        device_sn=os.environ.get("COZYLA_DEVICE_SN", "cozyla-sdk"),
        timezone=os.environ.get("TZ", "UTC"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.token = os.environ["COZYLA_API_TOKEN"]
    app.state.client = client_from_env()
    yield
    await app.state.client.aclose()


app = FastAPI(
    title="Cozyla SDK",
    description="Unofficial REST API for the Cozyla Calendar 2+ cloud.",
    version="0.1.0",
    lifespan=lifespan,
)
bearer = HTTPBearer()


def cozyla(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]
) -> CozylaClient:
    if not secrets.compare_digest(credentials.credentials, request.app.state.token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return request.app.state.client


Client = Annotated[CozylaClient, Depends(cozyla)]


def problem(status_code: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        {"title": title, "status": status_code, "detail": detail},
        status_code=status_code,
        media_type="application/problem+json",
    )


@app.exception_handler(NotFoundError)
async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return problem(404, "Not found", str(exc))


@app.exception_handler(CozylaError)
async def cozyla_error(_: Request, exc: CozylaError) -> JSONResponse:
    return problem(502, "Cozyla cloud error", str(exc))


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/members", tags=["members"])
async def list_members(client: Client) -> list[Member]:
    return await client.list_members()


@app.get("/todo-lists", tags=["todos"])
async def list_todo_lists(client: Client) -> list[TodoList]:
    return await client.list_todo_lists()


@app.post("/todo-lists", status_code=201, tags=["todos"])
async def create_todo_list(data: TodoListCreate, client: Client) -> TodoList:
    return await client.create_todo_list(data)


@app.get("/todo-lists/{list_id}", tags=["todos"])
async def get_todo_list(list_id: str, client: Client) -> TodoList:
    return await client.get_todo_list(list_id)


@app.patch("/todo-lists/{list_id}", tags=["todos"])
async def update_todo_list(list_id: str, data: TodoListUpdate, client: Client) -> TodoList:
    return await client.update_todo_list(list_id, data.model_dump(exclude_unset=True))


@app.delete("/todo-lists/{list_id}", status_code=204, tags=["todos"])
async def delete_todo_list(list_id: str, client: Client) -> None:
    await client.delete_todo_list(list_id)


@app.get("/todo-lists/{list_id}/items", tags=["todos"])
async def list_todos(list_id: str, client: Client) -> list[Todo]:
    await client.get_todo_list(list_id)
    return await client.list_todos(list_id)


@app.post("/todo-lists/{list_id}/items", status_code=201, tags=["todos"])
async def create_todo(list_id: str, data: TodoCreate, client: Client) -> Todo:
    return await client.create_todo(list_id, data)


@app.get("/todo-lists/{list_id}/items/{todo_id}", tags=["todos"])
async def get_todo(list_id: str, todo_id: str, client: Client) -> Todo:
    return await client.get_todo(list_id, todo_id)


@app.patch("/todo-lists/{list_id}/items/{todo_id}", tags=["todos"])
async def update_todo(list_id: str, todo_id: str, data: TodoUpdate, client: Client) -> Todo:
    return await client.update_todo(list_id, todo_id, data)


@app.delete("/todo-lists/{list_id}/items/{todo_id}", status_code=204, tags=["todos"])
async def delete_todo(list_id: str, todo_id: str, client: Client) -> None:
    await client.delete_todo(list_id, todo_id)


@app.get("/chores", tags=["chores"])
async def list_chores(client: Client) -> list[Chore]:
    return await client.list_chores()


@app.post("/chores", status_code=201, tags=["chores"])
async def create_chore(data: ChoreCreate, client: Client) -> Chore:
    return await client.create_chore(data)


@app.get("/chores/occurrences", tags=["chores"])
async def list_chore_occurrences(client: Client, day: date | None = None) -> list[ChoreOccurrence]:
    return await client.list_chore_occurrences(day or client.today())


@app.get("/chores/{chore_id}", tags=["chores"])
async def get_chore(chore_id: str, client: Client) -> Chore:
    return await client.get_chore(chore_id)


@app.patch("/chores/{chore_id}", tags=["chores"])
async def update_chore(chore_id: str, data: ChoreUpdate, client: Client) -> Chore:
    return await client.update_chore(chore_id, data)


@app.delete("/chores/{chore_id}", status_code=204, tags=["chores"])
async def delete_chore(chore_id: str, client: Client) -> None:
    await client.delete_chore(chore_id)


@app.put("/chores/{chore_id}/completions/{day}/{member_id}", status_code=204, tags=["chores"])
async def complete_chore(chore_id: str, day: date, member_id: str, client: Client) -> None:
    await client.set_chore_completed(chore_id, day, member_id, True)


@app.delete("/chores/{chore_id}/completions/{day}/{member_id}", status_code=204, tags=["chores"])
async def uncomplete_chore(chore_id: str, day: date, member_id: str, client: Client) -> None:
    await client.set_chore_completed(chore_id, day, member_id, False)


@app.get("/routines", tags=["routines"])
async def list_routines(client: Client) -> list[Routine]:
    return await client.list_routines()


@app.post("/routines", status_code=201, tags=["routines"])
async def create_routines(data: RoutineCreate, client: Client) -> list[Routine]:
    return await client.create_routines(data)


@app.get("/routines/occurrences", tags=["routines"])
async def list_routine_occurrences(
    client: Client, day: date | None = None
) -> list[RoutineOccurrence]:
    return await client.list_routine_occurrences(day or client.today())


@app.get("/routines/{routine_id}", tags=["routines"])
async def get_routine(routine_id: str, client: Client) -> Routine:
    return await client.get_routine(routine_id)


@app.patch("/routines/{routine_id}", tags=["routines"])
async def update_routine(routine_id: str, data: RoutineUpdate, client: Client) -> Routine:
    return await client.update_routine(routine_id, data)


@app.delete("/routines/{routine_id}", status_code=204, tags=["routines"])
async def delete_routine(routine_id: str, client: Client) -> None:
    await client.delete_routine(routine_id)


@app.put("/routines/{routine_id}/completions/{day}", status_code=204, tags=["routines"])
async def complete_routine(routine_id: str, day: date, client: Client) -> None:
    await client.set_routine_completed(routine_id, day, True)


@app.delete("/routines/{routine_id}/completions/{day}", status_code=204, tags=["routines"])
async def uncomplete_routine(routine_id: str, day: date, client: Client) -> None:
    await client.set_routine_completed(routine_id, day, False)


@app.get("/rewards", tags=["rewards"])
async def list_rewards(client: Client) -> list[Reward]:
    return await client.list_rewards()


@app.post("/rewards", status_code=201, tags=["rewards"])
async def create_reward(data: RewardCreate, client: Client) -> Reward:
    return await client.create_reward(data)


@app.get("/rewards/{reward_id}", tags=["rewards"])
async def get_reward(reward_id: str, client: Client) -> Reward:
    return await client.get_reward(reward_id)


@app.patch("/rewards/{reward_id}", tags=["rewards"])
async def update_reward(reward_id: str, data: RewardUpdate, client: Client) -> Reward:
    return await client.update_reward(reward_id, data)


@app.delete("/rewards/{reward_id}", status_code=204, tags=["rewards"])
async def delete_reward(reward_id: str, client: Client) -> None:
    await client.delete_reward(reward_id)


@app.post("/rewards/{reward_id}/redemptions", status_code=201, tags=["rewards"])
async def redeem_reward(reward_id: str, data: RedemptionCreate, client: Client) -> Redemption:
    return await client.redeem_reward(reward_id, data.member)


@app.get("/redemptions", tags=["rewards"])
async def list_redemptions(
    client: Client, member: str | None = None, status: RedemptionStatus | None = None
) -> list[Redemption]:
    return await client.list_redemptions(member, status)


@app.get("/redemptions/{redemption_id}", tags=["rewards"])
async def get_redemption(redemption_id: str, client: Client) -> Redemption:
    return await client.get_redemption(redemption_id)


@app.post("/redemptions/{redemption_id}/approve", status_code=204, tags=["rewards"])
async def approve_redemption(redemption_id: str, client: Client) -> None:
    await client.approve_redemption(redemption_id, True)


@app.post("/redemptions/{redemption_id}/deny", status_code=204, tags=["rewards"])
async def deny_redemption(redemption_id: str, client: Client) -> None:
    await client.approve_redemption(redemption_id, False)


@app.delete("/redemptions/{redemption_id}", status_code=204, tags=["rewards"])
async def undo_redemption(redemption_id: str, client: Client) -> None:
    await client.undo_redemption(redemption_id)
