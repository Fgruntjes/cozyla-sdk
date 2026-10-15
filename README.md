# cozyla-sdk

Unofficial Python client and documented REST API for the [Cozyla Calendar 2+](https://www.cozyla.com/) cloud, built to wire the wall calendar's apps into Home Assistant.

Cozyla publishes no API. This project talks to the same cloud endpoints the Cozyla tablet apps use, mapped by decompiling those apps — see [`docs/cozyla-cloud-api.md`](docs/cozyla-cloud-api.md) and [ADR 0001](docs/adr/0001-cloud-api-via-decompiled-app.md).
Cozyla can change that API at any time, and using it may conflict with their terms of service: use your own account, at your own risk.

## Features

| Cozyla app | Status |
|---|---|
| Tasks → To-do lists and items | ✅ list, create, update, complete, delete (due dates, reminders, assignees, stars, flags) |
| Family members (to-do assignees) | ✅ read |
| Tasks → Chores | ✅ list, create, update, delete, per-day occurrences, complete/reopen per member |
| Tasks → Routines, Rewards | planned |
| Meals → Meal plan, Grocery, Pantry | planned |
| Notes | planned |
| Calendar | use Cozyla's built-in CalDAV/Google sync and HA's CalDAV integration |

## Run

| Variable | Required | Meaning |
|---|---|---|
| `COZYLA_EMAIL` | yes | Cozyla ID email |
| `COZYLA_PASSWORD` | yes | Cozyla ID password |
| `COZYLA_API_TOKEN` | yes | Bearer token clients must send to this service |
| `COZYLA_DEVICE_SN` | no | Device serial this service logs in as (default `cozyla-sdk`); keep it stable |
| `TZ` | no | Time zone sent to Cozyla (default `UTC`) |

```bash
cp .env.example .env  # then fill it in
uv run --env-file .env uvicorn cozyla.api:app --host 0.0.0.0 --port 8000
# or
docker build -t cozyla-sdk . && docker run --env-file .env -p 8000:8000 cozyla-sdk
```

Ids are 64-bit and returned as strings. Interactive API docs live at `http://localhost:8000/docs` and the OpenAPI schema at `/openapi.json`.

```bash
curl -H "Authorization: Bearer $COZYLA_API_TOKEN" localhost:8000/todo-lists
curl -H "Authorization: Bearer $COZYLA_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"title": "Buy milk", "due": "2026-10-12T18:00:00+02:00", "reminder_minutes": 60}' \
  localhost:8000/todo-lists/<list-id>/items
```

## Home Assistant

```yaml
rest_command:
  cozyla_add_todo:
    url: "http://cozyla-sdk:8000/todo-lists/{{ list_id }}/items"
    method: post
    headers:
      Authorization: !secret cozyla_api_bearer
    content_type: application/json
    payload: '{"title": "{{ title }}"}'
  cozyla_complete_chore:
    url: "http://cozyla-sdk:8000/chores/{{ chore_id }}/completions/{{ now().date() }}/{{ member_id }}"
    method: put
    headers:
      Authorization: !secret cozyla_api_bearer

rest:
  - resource: http://cozyla-sdk:8000/todo-lists/<list-id>/items
    headers:
      Authorization: !secret cozyla_api_bearer
    scan_interval: 300
    sensor:
      - name: Cozyla open to-dos
        value_template: "{{ value_json | rejectattr('completed') | list | count }}"
```

`cozyla_api_bearer` in `secrets.yaml` is `Bearer <COZYLA_API_TOKEN>`.

## Library

```python
from cozyla.client import CozylaClient

client = CozylaClient("me@example.com", "password")
for todo in await client.list_todos():
    print(todo.title, todo.completed)
```

## Develop

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
