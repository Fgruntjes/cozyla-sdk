import os
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cozyla.client import CozylaClient, CozylaError, NotFoundError
from cozyla.models import (
    Member,
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
    description="Unofficial REST API for the Cozyla Calendar 2+ cloud (to-dos, members).",
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
async def get_todo_list(list_id: int, client: Client) -> TodoList:
    return await client.get_todo_list(list_id)


@app.patch("/todo-lists/{list_id}", tags=["todos"])
async def update_todo_list(list_id: int, data: TodoListUpdate, client: Client) -> TodoList:
    return await client.update_todo_list(list_id, data.model_dump(exclude_unset=True))


@app.delete("/todo-lists/{list_id}", status_code=204, tags=["todos"])
async def delete_todo_list(list_id: int, client: Client) -> None:
    await client.delete_todo_list(list_id)


@app.get("/todo-lists/{list_id}/items", tags=["todos"])
async def list_todos(list_id: int, client: Client) -> list[Todo]:
    await client.get_todo_list(list_id)
    return await client.list_todos(list_id)


@app.post("/todo-lists/{list_id}/items", status_code=201, tags=["todos"])
async def create_todo(list_id: int, data: TodoCreate, client: Client) -> Todo:
    return await client.create_todo(list_id, data)


@app.get("/todo-lists/{list_id}/items/{todo_id}", tags=["todos"])
async def get_todo(list_id: int, todo_id: int, client: Client) -> Todo:
    return await client.get_todo(list_id, todo_id)


@app.patch("/todo-lists/{list_id}/items/{todo_id}", tags=["todos"])
async def update_todo(list_id: int, todo_id: int, data: TodoUpdate, client: Client) -> Todo:
    return await client.update_todo(list_id, todo_id, data)


@app.delete("/todo-lists/{list_id}/items/{todo_id}", status_code=204, tags=["todos"])
async def delete_todo(list_id: int, todo_id: int, client: Client) -> None:
    await client.delete_todo(list_id, todo_id)
