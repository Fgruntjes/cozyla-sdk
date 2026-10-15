# Cozyla Cloud API

Reverse-engineered from decompiled APKs (static analysis only, no live calls). Field names and endpoints are taken from obfuscated Kotlin/Java sources; treat response shapes marked "inferred" as unverified until exercised against the live server.

## Source

| App | Package | Version | Role |
|---|---|---|---|
| Cozyla ID | `com.cozyla.id` | 1.0.0.2026072318 | Account, login, token issuance, members |
| Tasks/Chores | `com.cozyla.choresreward` | 1.2.8.2026091017 | To-do lists & items, chores, rewards |

Decompiled with jadx 1.5.6 from APKs pulled off a Calendar 2+ (firmware 20250826).

## Base URLs

- Production: `https://api.cozylacal.com/`
- UAT: `https://uat-api.cozyla.us/`
- Dev (Tasks): `https://smartdevicespvt.cozyla.link/`

Tasks app selector: `com/cozyla/choresreward/api/Api.java` (`getCozylaBaseUrl()` keyed on product channel `devTest`/UAT/release). ID app hardcodes production in `com/cozyla/id/a.java`. All endpoints are prefixed `/cal-server/`.

## Authentication

### Login endpoint

`POST /cal-server/users/cozUsers/signIn` → `CozylaBaseResult<RegisterResult>`
(`com/cozyla/id/api/CozylaService.java`, body built in `com/cozyla/id/ui/login/LoginViewModel$login$1.java`)

Login is **email + password**. No verification code, QR pairing, device-binding handshake, or Google sign-in is involved in the password login path. Request body (JSON):

```json
{
  "email": "user@example.com",
  "encryptionPassword": "<base64 RSA-encrypted password>",
  "app_id": "Notes",
  "deviceSn": "<device serial>",
  "loginClient": "DEVICE",
  "deviceName": "<Build.MODEL>"
}
```

- `app_id` — source-app label (`APPSourceEnum` name, e.g. `Notes`, `Chores`, `Calendar`); defaults to `Notes`. Passed from the launching intent; appears cosmetic.
- `deviceSn` — `CzlDeviceUtils.a()`: `Build.getSerial()`, else `Settings.Secure.ANDROID_ID`, else a persisted random UUID (hex, no dashes). **Client-chosen; any stable string works.**
- `loginClient` — constant `"DEVICE"`.
- `deviceName` — `Build.MODEL`.

### Password encryption

`com/cozyla/id/util/RSAEncryptionUserInfo.java`:
- Algorithm: `RSA/ECB/PKCS1Padding`, encrypt with a hardcoded X.509 public key, output Base64.
- Public key (Base64 SPKI, RSA-2048):
  ```
  MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuy5lIpsXk9rk3rY/9yxWII+r6oLaMNc5pWw1XrbQaoEn2EUI0O2QXfF7C7S89FHZKoZlz0MDD0W9X6dCldWpIjZYf+5fjlsrQDOkfJULlwTn8b91pe/NYiv2YWCdfTv1Pq9tTy6rkw4C66S7PW4rxVmFxWHI1yXvaRVCLe70YFZYrOe+YUzruYRYSi4im77ITdZ7W2HAiQ2RwsJJXd8M2Y8w43aT3NXz1s/mKcpZrABgD0MQSdYadmKs6Cdm6H6oBRYuca5YxQSfg2VAu2qliZKEU2nVV2PWAYzDcnH7a2HMv0FylabwP4on7n59yNWe0nH7L47457IL354qmJnVEQIDAQAB
  ```
- `encryptionPassword` = `RSAEncryptionUserInfo.a(plaintextPassword)`. This is a public key, so a server client can replicate it with the password alone. The plaintext password is the raw user password (not hashed first).

There is also MD5 (`util/MD5Utils.java`) and AES (`util/AESUtil.java`) in the ID app, but neither is used for the login password — AES is only for the content-provider token hand-off (below).

### Response: `RegisterResult` (`com/cozyla/id/bean/RegisterResult.java`)

Issued by `signIn`, `signUp`, `resetPassword`. Fields:

| Field | Type | Notes |
|---|---|---|
| `token` | string | Bearer-less auth token (see headers) |
| `deviceUid` | string | Server-assigned device/account id; sent back on requests |
| `deviceSn` | string | Echo of device serial |
| `memberUid` | string | Primary member id |
| `email` | string | |
| `calendarCode` | string | |
| `certificatePem` | string | IoT/MQTT cert material |
| `deviceRegisterVo` | object (`DeviceIotBean`) | IoT registration payload |
| `registerTime` | string | |
| `loginLimitCountdown` | int | Seconds locked out when `code==1002` |
| `content` | string | Error text when `code==1001` |

Login error codes (handled in `LoginActivity`/`LoginViewModel$login$1`): `1001` = bad credentials (message in `content`), `1002` = rate-limited/locked (`loginLimitCountdown` seconds).

### Token lifetime / refresh

No refresh endpoint exists. The token is used until the server returns envelope `code` `101`/`102` (token expired/invalid), at which point both apps clear the stored token and force re-login (`CheckTokenValidInterceptor`, `fa/b.java`). Re-authentication is a fresh `signIn`. `POST /cal-server/users/cozUsers/loginOut` invalidates server-side.

### Can a server log in with just email + password?

**Yes.** `signIn` needs only `email` + RSA-encrypted `password`; `deviceSn`/`app_id`/`deviceName`/`loginClient` are client-supplied strings (any value), and `deviceUid`/`memberUid` are returned *in the response*, not required in the request. A server can pick an arbitrary stable `deviceSn`. Caveats:
- `code 1002` indicates brute-force lockout; keep the same `deviceSn` and avoid hammering.
- The token likely binds to the `deviceSn` presented at login, so reuse the same value across requests.
- Logging in from a new `deviceSn` may displace the tablet's session (the ID app has a `keepOtherDeviceLogin` flag on email/password-change flows, implying single-session-per-device semantics).

### How the Tasks app gets the token (copy-from-tablet path)

The Tasks app does **not** log in. It reads the token from the ID app's content provider:

- Provider: `com.cozyla.id.provider`, path `cozyla_id`, `exported=true`. **The ID app declares `android:sharedUserId="android.uid.system"`** (manifest), i.e. it is a system app.
- Query URI: `content://com.cozyla.id.provider/cozyla_id?ts=<yyyyMMdd>&action=token` (built in `choresreward util/y0.d()`), parsed into `CozylaToken {deviceSn, deviceUid, email, memberUid, token}`.
- The provider gates callers: `getNameForUid(Binder.getCallingUid())` must start with `com.cozyla.`, `com.android.`, or `android.` (`CozylaIdContentProvider.b()`).
- The result row is **AES-encrypted** (`AESUtil.encrypt(json, callerPackageName, ts)`), where the key is derived by `PBKDF2WithHmacSHA256(password=callerPackageName, salt=ts, 10000 iters, 256-bit)` and IV from `ts` bytes (`AES/CBC/PKCS5Padding`). `ts` = `yyyyMMdd` of today.

Implication for a "copy token from tablet" client: you can pull the raw token off the tablet (it is stored in the ID app's `czl_token_prefs` SharedPreferences via `TokenManager`, and broadcast via the provider), then send it as the `Authorization` header from your own client. The provider's package-name gate and AES wrapping only matter if you read it *through the provider as another app*; a root/ADB read of the prefs file, or decrypting with your own package name + today's `ts`, both work. The token value itself carries the auth — no device attestation on normal API calls.

ID app also broadcasts lifecycle intents consumed by `CozylaIdReceiver` in the Tasks app: `com.cozyla.id.ACTION_NOTIFY_LOGIN`, `ACTION_NOTIFY_LOGOUT`, `ACTION_SUBSCRIPTION_CHANGE`, `ACTION_NOTIFY_MEMBER_CHANGE`, `ACTION_EXIT`.

## Request headers

No request signing, HMAC, nonce, or timestamp signature exists in either app. Auth is the bare token in `Authorization`.

Added by the Tasks app interceptor (`fa/c.java`, case 0) on non-GET requests when a token is present:

| Header | Value |
|---|---|
| `Authorization` | raw token, **no `Bearer` prefix** |
| `timeZoneId` | `TimeZone.getDefault().getID()` (e.g. `Europe/Amsterdam`) |
| `Accept-Language` | `<lang-tag>,<lang>;q=0.9` |
| `X-DEVICE-INFO` | Base64 of a Gson-serialized `DeviceInfo` (below) |

ID app interceptor (`com/cozyla/id/network/ParamInterceptor.java`) adds the same plus `modelName` (`Build.MODEL`), `platform` (`Android`), `calendarOsVersion` (`Build.DISPLAY`). Image loads (Glide/Coil) send only `Authorization` (raw) and `timeZoneId` (`nc/c.java`, `sb/o.java`).

`X-DEVICE-INFO` decodes to JSON with keys (`@SerializedName`, `com/cozyla/.../bean/DeviceInfo.java`): `deviceSn`, `deviceUid`, `deviceVersion` (Build.DISPLAY), `deviceType` (`"Device"`), `modelName` (Build.MODEL), `deviceName` (Build.DEVICE), `osVersion` (Build.VERSION.RELEASE), `appVersion`, `packageName`, `deviceBrand` (Build.BRAND), `deviceManufacturer`, `screenResolution` (`WxH`), `timeZoneId`, `loginClient` (`"DEVICE"`). `deviceSn`/`deviceUid` come from the stored token. The server appears to tolerate requests without it (header is best-effort), but sending it with the token's `deviceSn`/`deviceUid` is safest.

### `deviceUid` injected into the body

The Tasks interceptor also **injects `deviceUid` into the request body** of POST/PUT requests (`fa/c.java`): for form bodies it adds a `deviceUid` field; for JSON bodies it parses the JSON and adds `"deviceUid": "<token.deviceUid>"`. This is why every `*Param` extends `CzlBaseParam` (field `deviceUid`, populated from the token). A hand-rolled client should include `deviceUid` in each JSON body rather than rely on the interceptor.

## Response envelope

`CozylaBaseResult<T>` (`com/cozyla/id/bean/CozylaBaseResult.java`), parsed by `CozylaBaseResultDeserializer`:

```json
{ "code": 0, "message": "success", "requestId": "...", "result": { } }
```

| Field | Type | Notes |
|---|---|---|
| `code` | int | `0` = success (`isSuccess() { code == 0 }`) |
| `message` | string | human-readable; `msg()` accessor |
| `requestId` | string | |
| `result` | T | payload; `data()` accessor |

Token-expired / invalid: `code` `101` or `102` → clients clear the token and force re-login. Login-specific: `1001` bad credentials, `1002` rate-limited.

## Members

`POST /cal-server/users/cozUsersMember/queryMembers`

Tasks app body — `GetFamilyMembersParam`: `{ "app": 1, "deviceUid": "<uid>" }` (`app` defaults to `1` in the Tasks app). Returns a list of family members.

ID app variant takes an empty/minimal JSON body plus the device headers and returns `List<ResultMeberInfo>`.

Member object (union of `FamilyMemberBean` / `ResultMeberInfo` / `db/reward/MemberBean`):

| Field | Type | Notes |
|---|---|---|
| `memberUid` | string | **This is what `assignMemberUid` on a to-do references** |
| `memberName` | string | |
| `headPortrait` | string | avatar URL (relative; prefix with base URL, send `Authorization` to fetch) |
| `color` | string | |
| `gender` | string | |
| `role` | string | |
| `coins` | int | reward balance |
| `memberType` | int | |
| `mainMemberUid` | string | parent/primary account uid |
| `deviceMemberId` | string | |

Related: `POST /cal-server/users/cozUsersMember/queryMembersWithRing`, `addUserMember`, `updateUserMember`, `deleteUserMember`.

## To-do lists

All POST, JSON body, each extends `CzlBaseParam` (so every body also carries `deviceUid`). No `@SerializedName` renames anywhere in the to-do DTOs — JSON keys equal the Kotlin field names. DTOs: `com/cozyla/choresreward/api/v1_1_4/*`, `db/todolist/*`, `db/todo/*`. Interface: `com/cozyla/choresreward/api/CozylaService.java`.

### `TodoListNetBean` (list item in responses)

| Field | Type | Meaning |
|---|---|---|
| `listId` | long | list id |
| `todoListTitle` | string | |
| `todoListColor` | string | |
| `todoListIcon` | string | icon name/key |
| `displayOrder` | double | sort key (fractional for reordering) |
| `isPreset` | int | 1 = built-in/preset list |
| `userId` | int | |
| `createDate` | long | epoch ms |
| `version` | long | optimistic-concurrency / sync version |

### `GET list` — `POST /cal-server/rewards/todosList/list`
Request `GetTodoListParam`: body is just `{ "deviceUid": "<uid>" }` (no other fields).
Response: `CozylaBaseResult<List<TodoListNetBean>>`.

### `create` — `POST /cal-server/rewards/todosList/create`
`CreateTodoListParam`:
```json
{ "deviceUid":"<uid>", "todoListTitle":"Groceries", "todoListColor":"#FFAA00", "todoListIcon":"cart", "version":0 }
```
Response `CreateTodoListRsp`: `{ "listId": <long>, "displayOrder": <double>, "version": <long>, "createDate": <long> }`.

### `update` — `POST /cal-server/rewards/todosList/update`
`UpdateTodoListParam`:
```json
{ "deviceUid":"<uid>", "listId":123, "todoListTitle":"...", "todoListColor":"...", "todoListIcon":"..." }
```
Response: `CozylaBaseResult<Object>` (no typed payload).

### `delete` — `POST /cal-server/rewards/todosList/delete`
`DeleteTodoListParam`: `{ "deviceUid":"<uid>", "id": 123 }` (`id` = listId). Response: `Object`.

### `updateDisplayOrder` — `POST /cal-server/rewards/todosList/updateDisplayOrder`
`UpdateListOrderParam`: `{ "deviceUid":"<uid>", "id":123, "displayOrder": 1.5 }`. Response: `Object`.

### Offline sync — `POST /cal-server/rewards/todosList/offline/syncUpdateTodosList`
`UploadOfflineTodoListParam` (batch upload for offline edits; not needed for an online client).

## To-do items

### `TodoNetBean` (item in responses) — `db/todo/TodoNetBean.java`

| Field | Type | Meaning |
|---|---|---|
| `todoId` | long | item id |
| `todoListId` | long | parent list id |
| `todoTitle` | string | |
| `todoDesc` | string | description |
| `assignMemberUid` | string | `memberUid` of assignee; null/empty = unassigned |
| `todoStars` | int | reward stars/points attached to the task |
| `isFlag` | int | flag/important marker: `1` = flagged, `0` = not (used as boolean in UI) |
| `completeStatus` | int | `1` = completed, `0` = open (Room filters `completeStatus = 1` as done) |
| `completeTime` | long | epoch ms when completed, `0` if open |
| `createTime` | long | epoch ms |
| `displayOrder` | double | sort key in a list |
| `profileDisplayOrder` | double | sort key in a member's profile view |
| `dueDateTime` | long (nullable) | **epoch milliseconds** (derived from `Date.getTime()`); all-day due dates use `HH:mm = 23:59` |
| `reminderTime` | int (nullable) | reminder lead amount; `-1`/absent = no reminder |
| `timeUnit` | string (nullable) | reminder unit; observed `"none"` and `"day"`; paired with `reminderTime` (e.g. N days before due). Other units (hour/minute/week) likely but not confirmed in strings |
| `version` | long | sync/concurrency version |

### `GET list` — `POST /cal-server/rewards/todosInfo/list`
`GetTodoInfosParam`: body `{ "deviceUid":"<uid>" }` only. Response: `CozylaBaseResult<List<TodoNetBean>>` (all items across lists; client filters by `todoListId`/`assignMemberUid`/`completeStatus`).

### `create` — `POST /cal-server/rewards/todosInfo/create`
`CreateTodoInfoParam`:
```json
{
  "deviceUid":"<uid>",
  "todoListId": 123,
  "todoTitle": "Buy milk",
  "todoDesc": "2 liters",
  "assignMemberUid": "<memberUid or null>",
  "todoStars": 3,
  "isFlag": 0,
  "dueDateTime": 1760131140000,
  "reminderTime": 1,
  "timeUnit": "day"
}
```
(`todoListId`, `dueDateTime`, `reminderTime` are nullable; `todoStars`/`isFlag` are primitive ints.) Response `CreateTodoInfoRsp`: `{ "todoId":<long>, "todoListId":<long>, "displayOrder":<double>, "profileDisplayOrder":<double>, "createTime":<long>, "version":<long> }`.

### `update` — `POST /cal-server/rewards/todosInfo/update`
`UpdateTodoInfoParam` (requires `todoId` + `todoListId`; `isFlag`/`todoStars` nullable here):
```json
{ "deviceUid":"<uid>", "todoId":456, "todoListId":123, "todoTitle":"...", "todoDesc":"...",
  "assignMemberUid":"...", "todoStars":3, "isFlag":1, "dueDateTime":1760131140000, "reminderTime":2, "timeUnit":"day" }
```
Response: `CozylaBaseResult<TodoNetBean>` (the updated item).

### `checkTodo` — `POST /cal-server/rewards/todosInfo/checkTodo`
`CheckTodoInfoParam`: `{ "deviceUid":"<uid>", "todoId":456, "completeStatus":1 }` (toggle complete/open). Response `CheckTodoInfoRsp`: `{ "todoId":<long>, "completeStatus":<int>, "completeTime":<long>, "version":<long> }`.

### `delete` — `POST /cal-server/rewards/todosInfo/delete`
`DeleteTodoInfoParam`: `{ "deviceUid":"<uid>", "id":456 }` (`id` = todoId). Response: `Object`.

### `updateDisplayOrder` — `POST /cal-server/rewards/todosInfo/updateDisplayOrder`
`UpdateTodoDisplayOrderParam`: `{ "deviceUid":"<uid>", "id":456, "displayOrder":2.0, "profileDisplayOrder":1.0 }` (order fields nullable `Double`). Response: `Object`.

### `deleteTodoByTime` — `POST /cal-server/rewards/todosInfo/deleteTodoByTime`
Two body shapes hit the same path:
- `DeleteListTodoParam`: `{ "deviceUid":"<uid>", "listId":123, "deleteTime":<int> }` — clear completed items in a list.
- `DeleteMemberTodoParam`: `{ "deviceUid":"<uid>", "memberUid":"<uid>", "deleteTime":<int> }` — clear completed items for a member.
(`deleteTime` is an int flag/threshold selecting what to purge; exact encoding not resolved statically.) Response: `Object`.

### Offline sync — `POST /cal-server/rewards/todosInfo/offline/syncUpdateTodos`
`UploadOfflineTodosParam` (batch; not needed online). Also `POST /cal-server/rewards/todosInfo/needNotifiedTodoInfos` returns items due for reminder notification.

## Chores

From `com.cozyla.choresreward` 1.2.8.2026091017: `api/CozylaService.java`, DTOs in `api/` (`NewChoreParam`, `EditChoreParam`, `ChoreCheckParam`, `CozylaChoreTaskBean`, `CozylaChoreBean`). No `@SerializedName` renames; JSON keys equal the field names. Paths are under `/cal-server/rewards/chores/`.

Dates are `yyyy-MM-dd` strings and times `HH:mm` throughout chores and routines; no epoch values in request bodies.

### Schedule fields (shared with routines)

| Field | Type | Meaning |
|---|---|---|
| `repeats` | bool | `false` = one-off chore spanning `startDay`..`endDay` (chores only) |
| `repeatsEvery` | string | `Daily`, `Weekly`, `Monthly` |
| `repeatsEveryCounts` | int | every N days/weeks/months |
| `repeatsIn` | string | Daily: `""`; Weekly: full English day names, comma-separated, e.g. `Monday,Wednesday`; Monthly: days of month, e.g. `1,15` |
| `weekFirstDate` | int | in responses: `0` = weeks start Sunday, `1` = Monday |

### Chore definition

`CozylaChoreTaskBean` (also the create/update response):

| Field | Type | Meaning |
|---|---|---|
| `choreUid` | string | id (32 hex chars) |
| `choreName` | string | at most 50 characters |
| `icon` | string | e.g. `czl_chores_emoji#_#broom#_#🧹` (`czl_chores_emoji#_#<name>#_#<emoji>`) |
| `coins` | int | stars per completion |
| `choreType` | string | `Everyone` (each member does it), `AnyOne` (first to finish), `Rotate` |
| `rotateEveryCounts` | int | Rotate: switch assignee every N occurrences |
| `startDay`, `endDay` | string | `endDay` is ignored when `repeats` and `repeatsUntil` are both true |
| `dueTime` | string | `HH:mm`, app default `23:59` |
| `repeatsUntil` | bool | `true` = repeats forever |
| `reminder` | int | minutes before due; `-1` = none; app offers 5/10/30/60/120 |
| `memberRefs` | list | `{memberUid, memberName, coins, ...}` per assignee |
| `choreBank` | bool | unassigned chore any member can claim |
| `choreDeviceId` | string | the app always sends `db3860b5-9178-427a-894e-d9dfed2bcf5b` |
| `description` | string | |

Also `id` (numeric), `status` (int, meaning unknown), `displayOrder`, `weekFirstDate`, `createDate`/`updateDate` (ISO strings).

| Path | Body (beyond `deviceUid`) | Result |
|---|---|---|
| `myChoresV1` | none | all chore definitions |
| `create/v1` | `NewChoreParam`: the definition fields above minus `choreUid`, with `memberUids: [..]` instead of `memberRefs`, plus `asATemplate: bool` (also save to the chore library) | the created chore |
| `update/v1` | `EditChoreParam`: the create body minus `asATemplate`, plus `choreUid`; all fields required | the updated chore |
| `delete/v1` | `{ "choreUid": ".." }` | remaining chores |
| `choreRecordByDay/v3` | `{ "selectDay": "2026-10-15" }` | one record per member per chore occurring that day |
| `choreCheck/v1` | see below | none |

Occurrence record (`CozylaChoreBean`): the chore's schedule fields plus `choreMemberRecordUid` (`<choreUid>_<memberUid>_<day>`), `memberUid`, `checkDay`, `choreCoins`, `status` (`pending`, `completed`, `expired`), `checkTimestamp`, `memberRefIds` (comma-separated), `expiredCard`, `nextOccurDay`.

Complete or reopen one member's occurrence (`ChoreCheckParam`):

```json
{ "choreUid": "..", "memberUid": "..", "checkFrom": "dayPage", "choreStatus": "completed", "checkDay": "2026-10-15", "selectDay": "2026-10-15" }
```

`choreStatus` is the target state: `completed` or `pending`. `checkFrom` is the UI page (`dayPage`, `weekPage`, `memberPage`, `widget`). For a one-off chore whose `endDay` has passed, the app sends `endDay` as `checkDay`; otherwise `checkDay` is the occurrence day. The server adds the chore's `coins` to the member on completion and takes them back on reopen.

Not used by this project: `chores/detail`, `updateDisplayOrder`, `choreTipByDay`/`choreTipGetIt` (AnyOne compete tips), `choreTemplate/*` (chore library), `chores/batchCreate` (onboarding), `offline/*` sync.

## Routines

From `com.cozyla.choresreward` 1.2.8.2026091017: `api/CozylaService.java`, DTOs in `api/v1_1_2/` (`CreateRoutineStepParam`, `UpdateRoutineStepParam`, `RoutineRecordCheckParam`) and `db/userroutine/`. Paths are under `/cal-server/rewards/`. Chores and routines share no endpoints or ids; they share only the schedule fields above.

A routine belongs to one member. Creating a routine for several members creates one routine each.

Routine (`UserRoutineStepNetBean`):

| Field | Type | Meaning |
|---|---|---|
| `id` | int | routine id |
| `memberUid` | string | owner |
| `routineTitle`, `routineIcon` | string | icon key, e.g. `routine_property_bed` |
| `routineType` | string | `Morning`, `Afternoon`, `Evening` |
| `coins` | int | stars per completion |
| `repeatsEvery`, `repeatsEveryCounts`, `repeatsIn` | | schedule, as for chores; always repeating |
| `startDay` | string | `endDay` is `null` |
| `description` | string | |
| `habitEnabled`, `habitBonusStars` | int | habit tracking (0/1) and its bonus; `habitMilestones` lists the streak milestones (`[3, 7, 21, 66, 100]`) |
| `weekFirstDate` | int | `0` = Sunday, `1` = Monday |

| Path | Body (beyond `deviceUid`) | Result |
|---|---|---|
| `routineUser/getRoutineList/v1` | `{ "memberUids": [], "routineType": "" }` (empty = all) | routines |
| `routineUser/createRoutine` | `memberUids`, `routineTitle`, `routineType`, `routineIcon`, `coins`, `habitBonusStars`, `habitEnabled`, `repeatsEvery`, `repeatsEveryCounts`, `repeatsIn`, `startDay`, `asATemplate`, `description`; all required | `[{ "routineId": .., "memberId": .., "memberUid": "..", "routineTemplateId": .. }]` |
| `routineUser/updateRoutine` | create body minus `memberUids`/`asATemplate`, plus `id` and `toDay` (today; the edit applies from that day) | none |
| `routineUser/delRoutine` | `{ "id": 123, "toDay": "2026-10-15" }` | none |
| `routineUserRecord/getRoutineRecordByDay/v1` | `{ "selectDay": "2026-10-15", "memberUids": [] }` | one record per routine occurring that day |
| `routineUserRecord/checkUserRoutine` | `{ "routineId": 123, "checkDay": "2026-10-15", "status": "completed", "weekFirstDate": 1 }` | none |

Occurrence record (`RoutineRecordNetBean`): `routineId`, `memberUid`, `routineType`, `status` (`pending`, `completed`), `checkDay`, `routineTitle`, `routineIcon`, `coins`, the schedule fields, habit counters and `weekFirstDate`. `checkUserRoutine` sets `status` to `completed` or `pending`; the server adds or removes the routine's `coins` on the member.

The app uses `getRoutineList/v2` instead of `v1` when the account setting `reward:habit` is `"0"`.

Not used by this project: `routineUser/updateDisplayOrder`, `routineUser/createBathRoutine` (onboarding), `routineUserRecord/getRoutineRecordByScope` (date range), `routineTemplate/*` (routine library), `routineUserRecord/offline/*` sync.

## Rewards

From `com.cozyla.choresreward` 1.2.8.2026091017. Reward calls are not in `CozylaService`: the app posts plain maps to path constants in `api/Api.java` (`ee/n.java`, bodies built in `ui/reward/create/CreateRewardDialog.java`, `ui/reward/*.java`, `sb/*.java`). Paths are under `/cal-server/rewards/`. Members' star balance is `coins` in `queryMembers`.

Reward (`bean/RewardListDataBean`):

| Field | Type | Meaning |
|---|---|---|
| `rewardUid` | string | id |
| `name`, `description`, `link` | string | |
| `icon` | string | `czl_reward_gift` or an image URL |
| `coins` | int | stars a member spends |
| `renewable` | int | `1` = can be redeemed again |
| `approval` | int | `1` = a parent approves each redemption |
| `members` | list | `{memberUid, memberName, headPortrait}` who can redeem it |
| `productId` | long or null | set on rewards taken from the ideas catalog (`rewards/product/list`) |

| Path | Body (beyond `deviceUid`) | Result |
|---|---|---|
| `rewards/list/v1` | none | rewards |
| `rewards/create` | `name`, `description`, `icon`, `coins`, `productId` (string, `""` if none), `link`, `renewable`, `approval`, `rewardDeviceId` (random 32-hex string), `memberUids: [..]` | the reward, with `rewardMemberList` instead of `members` |
| `rewards/update` | create body plus `rewardUid` | none |
| `rewards/delete` | `{ "rewardUid": ".." }` | none |
| `rewards/redeem/v1` | `{ "memberUid": "..", "rewardUid": ".." }` | `{ rewardMemberRecordUid, redeemStatus, consumeCoins, .. }` |
| `rewards/rewardApprove/v1` | `{ "rewardMemberRecordUid": "..", "approveStatus": 1 }` (`0` = deny) | none |
| `rewards/unRedeem` | `{ "rewardMemberRecordUid": ".." }` | none |
| `offline/findMemberAllRewards/v1` | `{ "memberUids": [], "rewardStatus": "" }` (empty = all) | redemption records, see below |

`findMemberAllRewards/v1` returns one row per reward per member plus one row per redemption. Rows with `rewardMemberRecordUid: null` are availability (`rewardStatus` `WAITING` = enough stars, `CANNOT` = not enough). Redemption rows carry `rewardMemberRecordUid`, `rewardStatus` (`WAIT_APPROVE`, `ALREADY`, `DONE`), `memberUid`, the reward fields and `updateDateTimestamp` (epoch ms).

Redemption flow: `redeem/v1` takes the stars and creates a `WAIT_APPROVE` record when `approval` is `1`, else a `DONE` record. Approving moves it to `DONE`; denying deletes it and refunds the stars. `unRedeem` deletes any record and refunds.

Not used by this project: `rewards/done` (`doneStatus` 1/0; meant to move `ALREADY` → `DONE`), `rewards/getAwaitRewardControls` (counts), `rewards/addStars` (manual star adjustment), `rewards/getRecord` (star history), `rewards/product/list` (ideas catalog), `files/file/UploadReq` (custom icon upload), `familyView/selectChoresRoutineStarsNumInfo/v1` (stars earned per day).

## Confirmed against the live API

Checked on 2026-10-12 with a real account, logging in as a server (`deviceSn` `cozyla-sdk`).

- `signIn` with email + RSA-encrypted password works from a server; no tablet serial is needed.
- `signIn` without the ID app's device headers (`X-DEVICE-INFO`, `modelName`, `platform`, `calendarOsVersion`, `Accept-Language`, `timeZoneId`) returns `code` `99` "Error"; with them it succeeds.
- The returned `deviceUid` is `deviceSn` + `memberUid` concatenated, and the result also carries `tokenUid`.
- Envelope `code` arrives as a JSON **string** (`"0"`), not a number.
- List and to-do ids are 64-bit integers above 2^53 (e.g. `2105009974451359744`); JavaScript clients lose precision, so this project's REST API returns them as strings.
- "Not set" is `-1`: `dueDateTime: -1`, `reminderTime: -1`. `completeTime` can be `null` or a stale timestamp on an open item.
- `reminderTime` is **minutes before `dueDateTime`** (1440 = one day). `timeUnit` is the app's preset label: `none`, `on_time`, `minutes_before_5`, `minutes_before_30`, `one_hour_before`, `one_day_before`, `custom_minute`, `custom_hour`, `custom_day`, `custom_week` (enum in the Tasks app).
- `isPreset` is an integer type code (seen `1` and `3`), not a boolean.
- `todosList/list` items also carry `todoNum` and `sourceType`; `todosInfo/list` items also carry `todoListTitle`, `memberName`, `assignMemberId`, `headPortrait`, `color`, `virtualDeviceUid`, `showMemberUidList`, `sourceType`.
- `queryMembers` with `{"app": 1}` returns all family members with `memberUid`, `memberName`, `role`, `color`, `coins`, `memberType` (0 = main account, 1 = family member).
- Create, update, `checkTodo` (complete and reopen) and delete for items, and create, update and delete for lists, all succeed with the bodies documented above; `update` keeps fields only when they are re-sent.

Checked on 2026-10-15:

- Chore create, update, delete, `choreRecordByDay/v3` and `choreCheck/v1` (complete and reopen) succeed with the bodies documented above; completing awards the chore's stars to the member's `coins` and reopening removes them.
- `repeatsUntil: true` repeats past `endDay`; `repeatsUntil: false` stops at it.
- Routine create, update, delete, `getRoutineRecordByDay/v1` and `checkUserRoutine` (complete and reopen) succeed with the bodies documented above; stars move like chores. Update keeps the routine `id`.
- Reward create, update, delete, `redeem/v1`, `rewardApprove/v1` (approve and deny) and `unRedeem` succeed with the bodies documented above.
- Approving goes straight from `WAIT_APPROVE` to `DONE`; no `ALREADY` state was seen, and `rewards/done` changed nothing on a `DONE` record.
- Redeeming takes the stars at once, also while waiting for approval; deny and `unRedeem` refund them.

## Open questions

- **Token lifetime**: no TTL is visible; expiry is detected via `code` `101`/`102`.
- **Session eviction**: whether a server login with its own `deviceSn` signs the tablet out.
- **`deleteTime` semantics** in `deleteTodoByTime`.
- **Rate-limit policy** behind `code` `1002`.
- **Meaning of the `isPreset` codes.**
- **Chore `status` int**, `taskData`/`taskUid` on occurrence records.
- **Habit bonus**: when `habitBonusStars` is awarded.
- **When rewards reach `ALREADY`**, and what `rewards/done` does then.
