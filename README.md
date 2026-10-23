# cozyla-sdk

Unofficial Python client and documented REST API for the [Cozyla Calendar 2+](https://www.cozyla.com/) cloud, built to wire the wall calendar's apps into Home Assistant.

Cozyla publishes no API. This project talks to the same cloud endpoints the Cozyla tablet apps use, mapped by decompiling those apps — see [`docs/cozyla-cloud-api.md`](docs/cozyla-cloud-api.md) and [ADR 0001](docs/adr/0001-cloud-api-via-decompiled-app.md).
Cozyla can change that API at any time, and using it may conflict with their terms of service: use your own account, at your own risk.

## Features

| Cozyla app | Status |
|---|---|
| Tasks → To-do lists and items | ✅ list, create, update, complete, delete (due dates, reminders, assignees, stars, flags) |
| Family members (assignees, star balances) | ✅ read |
| Tasks → Chores | ✅ list, create, update, delete, per-day occurrences, complete/reopen per member |
| Tasks → Routines | ✅ list, create (one per member), update, delete, per-day occurrences, complete/reopen |
| Tasks → Rewards | ✅ list, create, update, delete, redeem, approve/deny, undo redemption |
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
| `TZ` | no | Time zone sent to Cozyla and used for "today" in chores and routines (default `UTC`) |

```bash
cp .env.example .env  # then fill it in
uv run --env-file .env uvicorn cozyla.api:app --host 0.0.0.0 --port 8000
# or
docker build -t cozyla-sdk . && docker run --env-file .env -p 8000:8000 cozyla-sdk
```

All ids are returned as strings; to-do ids are 64-bit integers. Days are `YYYY-MM-DD`; `day` defaults to today. Interactive API docs live at `http://localhost:8000/docs` and the OpenAPI schema at `/openapi.json`.

```bash
curl -H "Authorization: Bearer $COZYLA_API_TOKEN" localhost:8000/todo-lists
curl -H "Authorization: Bearer $COZYLA_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"title": "Buy milk", "due": "2026-10-12T18:00:00+02:00", "reminder_minutes": 60}' \
  localhost:8000/todo-lists/<list-id>/items
curl -H "Authorization: Bearer $COZYLA_API_TOKEN" "localhost:8000/chores/occurrences?day=2026-10-16"
curl -X PUT -H "Authorization: Bearer $COZYLA_API_TOKEN" \
  localhost:8000/chores/<chore-id>/completions/2026-10-16/<member-id>
curl -H "Authorization: Bearer $COZYLA_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"member": "<member-id>"}' localhost:8000/rewards/<reward-id>/redemptions
```

`PUT` on a completion completes the chore or routine and awards its stars; `DELETE` reopens it and takes them back.
Redeeming a reward spends the member's stars at once; rewards that need approval wait for `POST /redemptions/{id}/approve` or `/deny` (deny refunds), and `DELETE /redemptions/{id}` undoes a redemption.

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
  cozyla_complete_routine:
    url: "http://cozyla-sdk:8000/routines/{{ routine_id }}/completions/{{ now().date() }}"
    method: put
    headers:
      Authorization: !secret cozyla_api_bearer
  cozyla_redeem_reward:
    url: "http://cozyla-sdk:8000/rewards/{{ reward_id }}/redemptions"
    method: post
    headers:
      Authorization: !secret cozyla_api_bearer
    content_type: application/json
    payload: '{"member": "{{ member_id }}"}'

rest:
  - resource: http://cozyla-sdk:8000/todo-lists/<list-id>/items
    headers:
      Authorization: !secret cozyla_api_bearer
    scan_interval: 300
    sensor:
      - name: Cozyla open to-dos
        value_template: "{{ value_json | rejectattr('completed') | list | count }}"
  - resource: http://cozyla-sdk:8000/chores/occurrences
    headers:
      Authorization: !secret cozyla_api_bearer
    scan_interval: 300
    sensor:
      - name: Cozyla chores left today
        value_template: "{{ value_json | selectattr('status', 'eq', 'pending') | list | count }}"
```

`cozyla_api_bearer` in `secrets.yaml` is `Bearer <COZYLA_API_TOKEN>`.

## Library

```python
from cozyla.client import CozylaClient

client = CozylaClient("me@example.com", "password")
for todo in await client.list_todos():
    print(todo.title, todo.completed)
for chore in await client.list_chore_occurrences(client.today()):
    print(chore.name, chore.member, chore.status)
```

## Develop

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
