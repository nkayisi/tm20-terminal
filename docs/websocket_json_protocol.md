# Cloud Solution — WebSocket + JSON Protocol (v2.x)

> Source: `websocket_json_protocol2_7.pdf` (vendor document, author "Chingzou").
> Converted to Markdown for machine readability. Original wording is kept in English.
> JSON examples have been **normalized to valid syntax** (the PDF contains many typos: `,` instead of `:`, missing commas, curly quotes, keys with trailing spaces).
> Comments are kept inside ` ```jsonc ` blocks; **strip `//` comments before sending real messages.**
> All known inconsistencies of the original document are listed in [Section 6 — Known issues](#6-known-issues-and-ambiguities-in-the-source-document). Do not silently "fix" them in code: verify against a real device.

---

## 0. Revision history

| Date | Version | Change |
|---|---|---|
| 2016-03-25 | 1.0 | Original version |
| 2016-04-20 | 1.1 | `senduser`, `getuserinfo`, `setfp`, `setcard`, `setpwd`: added user name. Added `deleteuserlock`, `cleanuserlock` |
| 2016-04-21 | 1.2 | Added `setuserinfo` (sets fingerprint/password/card). Removed `setfp`, `setcard`, `setpwd` (replaced by `setuserinfo`). `deleteuser` backupnum: 0–9 delete finger, 10 password, 11 card, 12 all fingerprints, 13 all info (fp, pwd, card, name). `getuserlist`, `getnewlog`, `getalllog`: empty → success with `count: 0` |
| 2016-05-17 | 1.3 | Added `reboot` |
| 2016-05-25 | 1.4 | Added `settime` |
| 2016-07-06 | 1.5 | Added log notes |
| 2017-11-06 | 1.7 | Added enable/disable user; `sendlog` reply tells whether access is granted |
| 2018-06-07 | 1.8 | Added `sn` to all commands; `opendoor` with `doornum` (4-door access controller); `weekzone2`/`weekzone3` in `setuserlock`/`getuserlock` |
| 2019-03-27 | 1.9 | `sendlog`: added `logindex` |
| 2021-02-02 | 2.0 | AI device photo (backupnum 50), log image and temperature |

Commands 26–35 (`gettime`, QR code, questionnaire, holidays, user profile, `adduser`) appear in the body but are **not** listed in the revision history.

---

## 1. General rules

1. Transport: **WebSocket, RFC 6455, version 13**. Default listen port **7788**. **No TLS.**
2. Payload format: **JSON**.
3. All JSON keys are **lowercase** (exception in the doc: `InputAlarm`). Names and any non-ASCII (e.g. Chinese) text are **UTF-8**.
4. The **terminal (device) connects to the server**. The server listens on 7788.
5. Message direction convention:
   - A message that initiates an action has key **`cmd`**.
   - A reply has key **`ret`** (same value as the `cmd` it answers) plus **`result`** (bool).
   - On failure: `"result": false` and `"reason": <int or string>`.
6. Since v1.8, messages carry **`sn`** (terminal serial number).

### 1.1 `backupnum` — credential type/slot

| Value | Meaning |
|---|---|
| 0–9 | Fingerprint slot (max 10 fingerprints per user) |
| 10 | Password (max 8 digits) |
| 11 | RFID card |
| 12 | (`deleteuser` only) all fingerprints of the user |
| 13 | (`deleteuser` only) all data of the user (fp, pwd, card, name) |
| 20–27 | Static face |
| 30–37 | Palm |
| 50 | Photo (Base64) |

One user: up to 10 fingerprints, 1 password, 1 RFID card.

### 1.2 `record` field type depends on `backupnum`

| backupnum | `record` type | Constraint |
|---|---|---|
| 0–9 (fingerprint) | string (template) | length < 1620 for THbio3.0, < 1024 for THbio1.0 |
| 10 (password) | number | max 8 digits |
| 11 (card) | number | card number |
| 50 (photo) | string | Base64 |

### 1.3 `admin` values

| Value | Meaning |
|---|---|
| 0 | Normal user |
| 1 | Administrator |
| 2 | Super user (can only add users and download logs via USB disk) |

### 1.4 Command index

| # | Direction | `cmd` | Purpose |
|---|---|---|---|
| T1 | Terminal → Server | `reg` | Register |
| T2 | Terminal → Server | `sendlog` | Push attendance/access logs |
| T3 | Terminal → Server | `senduser` | Push user enrolled on keypad |
| T4 | Terminal → Server | `sendqrcode` | Push scanned QR code |
| S1 | Server → Terminal | `getuserlist` | List users (paginated) |
| S2 | Server → Terminal | `getuserinfo` | Get one credential of a user |
| S3 | Server → Terminal | `setuserinfo` | Upload a credential for a user |
| S4 | Server → Terminal | `deleteuser` | Delete credential(s) |
| S5 | Server → Terminal | `getusername` | Get name |
| S6 | Server → Terminal | `setusername` | Set names (batch) |
| S7/S8 | Server → Terminal | `enableuser` | Enable (`enflag:1`) / disable (`enflag:0`) |
| S9 | Server → Terminal | `cleanuser` | Delete all users |
| S10 | Server → Terminal | `getnewlog` | Get new (unread) logs (paginated) |
| S11 | Server → Terminal | `getalllog` | Get all logs (paginated, optional date range) |
| S12 | Server → Terminal | `cleanlog` | Delete all logs |
| S13 | Server → Terminal | `initsys` | Delete all users and logs (settings kept) |
| S14 | Server → Terminal | `reboot` | Reboot (no reply) |
| S15 | Server → Terminal | `cleanadmin` | Demote all admins to normal users |
| S16 | Server → Terminal | `settime` | Set device clock |
| S17 | Server → Terminal | `setdevinfo` | Set device parameters |
| S18 | Server → Terminal | `getdevinfo` | Get device parameters |
| S19 | Server → Terminal | `opendoor` | Open door |
| S20 | Server → Terminal | `setdevlock` | Set access-control parameters |
| S21 | Server → Terminal | `getdevlock` | Get access-control parameters |
| S22 | Server → Terminal | `getuserlock` | Get a user's access parameters |
| S23 | Server → Terminal | `setuserlock` | Set users' access parameters (batch) |
| S24 | Server → Terminal | `deleteuserlock` | Delete a user's access parameters |
| S25 | Server → Terminal | `cleanuserlock` | Delete all users' access parameters |
| S26 | Server → Terminal | `gettime` | Get device clock |
| S29 | Server → Terminal | `getquestionnaire` | Get questionnaire settings |
| S30 | Server → Terminal | `setquestionnaire` | Set questionnaire settings |
| S31 | Server → Terminal | `getholiday` | Get holidays |
| S32 | Server → Terminal | `setholiday` | Set holidays (max 30) |
| S33 | Server → Terminal | `setuserprofile` | Set user/public profile text |
| S34 | Server → Terminal | `getuserprofile` | Get user profile text |
| S35 | Server → Terminal | `adduser` | Remote enrollment trigger |

### 1.5 Pagination (`getuserlist`, `getnewlog`, `getalllog`)

1. Server sends `{"cmd": X, "stn": true}` (first request).
2. Terminal replies with a page: `from`, `to`, `count`, `record[]`.
3. Server sends `{"cmd": X, "stn": false}` to request the next page.
4. Repeat until no more data. Empty dataset → `result: true`, `count: 0`, `record: []`.

Page size: `getuserlist` ≤ 40 records; logs examples use 50 (`from 0 to 49`).
The stop condition is **not specified** — see Known issues.

---

## 2. Terminal → Server messages

### T1. Register — `reg`

Terminal sends:
```jsonc
{
  "cmd": "reg",
  "sn": "ZX0006827500",      // terminal serial number, fixed by manufacturer, unique
  "cpusn": "123456789",      // CPU serial number, fixed
  "devinfo": {
    "modelname": "tfs30",
    "usersize": 3000,        // user capacity 1000/3000/5000
    "fpsize": 3000,          // fingerprint capacity 1000/3000/5000
    "cardsize": 3000,        // RFID card capacity 1000/3000/5000/10000
    "pwdsize": 3000,         // password capacity
    "logsize": 100000,       // log capacity
    "useduser": 1000,
    "usedfp": 1000,
    "usedcard": 2000,
    "usedpwd": 400,
    "usedlog": 100000,
    "usednewlog": 5000,
    "fpalgo": "thbio3.0",    // fingerprint algorithm: thbio1.0 or thbio3.0
    "firmware": "th600w v6.1",
    "time": "2016-03-25 13:49:30",   // terminal datetime
    "mac": "00-01-A9-01-00-01"       // LAN MAC address
  }
}
```

Server reply — success:
```jsonc
{
  "ret": "reg",
  "result": true,
  "cloudtime": "2016-03-25 13:49:30",  // server current time
  "nosenduser": true                   // tells terminal whether to auto-send newly enrolled users
}
```

Server reply — fail:
```jsonc
{
  "ret": "reg",
  "result": false,
  "reason": "did not reg"   // displayed on the terminal screen
}
```

### T2. Send logs — `sendlog`

Terminal sends:
```jsonc
{
  "cmd": "sendlog",
  "sn": "zx12345678",
  "count": 2,
  "logindex": 10,            // added 2019-03-27
  "record": [
    {
      "enrollid": 1,
      "time": "2016-03-25 13:49:30",
      "mode": 0,             // see mode table (CONFLICTING definitions, see Known issues)
      "inout": 0,            // 0: in, 1: out
      "event": 0,            // normal 0; tfs20/tfs30 F1–F4 keys, customizable
      "temp": 36.5,          // body temperature (temperature devices only)
      "verifymode": 13,      // AI devices only; 13 = QR code verify
      "image": "gesg524hgd"  // real-time punch image, Base64 (AI face devices only)
    },
    {
      "enrollid": 2,
      "time": "2016-03-25 13:49:30",
      "mode": 0,
      "inout": 0,
      "event": 1,
      "verifymode": 13,
      "temp": 36.5,
      "image": "gesg524hgd"
    }
  ]
}
```

Server reply — success:
```jsonc
{
  "ret": "sendlog",
  "result": true,
  "count": 2,                // added 2019-03-27 (echo)
  "logindex": 10,            // added 2019-03-27 (echo)
  "cloudtime": "2016-03-25 13:49:30",
  "access": 1,               // 1: open the door, 0: do not open (extended function)
  "message": "message"       // when AI face device is in Server mode: text shown on device
}
```

Server reply — fail:
```json
{ "ret": "sendlog", "result": false, "reason": 1 }
```

#### Log field semantics

**When `enrollid != 0`** (user punch):

| Field | Meaning |
|---|---|
| `mode` | Verification method (see conflicting tables below) |
| `inout` | 0 = in, 1 = out. Master machine (usually inside) vs child/slave reader (usually outside) |
| `event` | 0–16, customizable, must be interpreted by the software. F1 pressed + verified → 1 (e.g. mapped to "on duty") |
| `verifymode` | 13 = QR code (AI devices). Other values undocumented |

`mode` — three contradictory definitions in the source:

| Source location | 0 | 1 | 2 | 3 | 8 |
|---|---|---|---|---|---|
| `sendlog` example comment | — | fingerprint | password | card | face |
| "Note: about the logs" | fingerprint | card | password | — | — |
| `getnewlog` / `getalllog` comments | fingerprint | card | password | — | — |

**When `enrollid == 0`** (door/system event): `mode = 0`, `inout = 1`, `event` = door event:

| `event` | Enum name | Meaning |
|---|---|---|
| 0 | UI_MGLOG_CLOSED | Door closed |
| 1 | UI_MGLOG_OPENED | Door opened |
| 2 | UI_MGLOG_HAND_OPEN | Opened with exit button |
| 3 | UI_MGLOG_PROG_OPEN | Opened by software |
| 4 | UI_MGLOG_PROG_CLOSE | Closed by software |
| 5 | UI_MGLOG_ILLEGAL_OPEN | Door opened illegally |
| 6 | UI_MGLOG_ILLEGAL_REMOVE | Device removed (tamper) |
| 7 | UI_MGLOG_ALARM | Input alarm |

(Numeric values inferred from C `enum` declaration order; not written explicitly in the source.)

### T3. Send user information — `senduser`

Sent when a new user is enrolled on the device keypad.

Fingerprint:
```jsonc
{
  "cmd": "senduser",
  "sn": "zx12345678",
  "enrollid": 1,
  "name": "chingzou",
  "backupnum": 0,            // 0–9 fp, 20–27 face, 30–37 palm, 50 photo
  "admin": 0,
  "record": "kajgksjgaglas"  // < 1620 chars (THbio3.0), < 1024 (THbio1.0)
}
```

RFID card:
```json
{ "cmd": "senduser", "sn": "zx12345678", "enrollid": 1, "name": "chingzou", "backupnum": 11, "admin": 0, "record": 2352253 }
```

Password:
```jsonc
{ "cmd": "senduser", "sn": "zx12345678", "enrollid": 1, "name": "chingzou", "backupnum": 10, "admin": 0, "record": 12345678 }  // max 8 digits
```

Server reply:
```json
{ "ret": "senduser", "result": true, "cloudtime": "2016-03-25 13:49:30" }
```
```json
{ "ret": "senduser", "result": false, "reason": 1 }
```

### T4. QR code — `sendqrcode` (source sections 27–28)

Terminal sends:
```json
{ "cmd": "sendqrcode", "sn": "AI07F123456", "record": "123456" }
```

Server reply:
```jsonc
{
  "ret": "sendqrcode",
  "sn": "AI07F1234567",
  "result": true,
  "access": 1,          // optional: 1 open door, 0 do not open
  "enrollid": 10,
  "username": "tom",
  "message": "ok",
  "voice": "ok"
}
```

---

## 3. Server → Terminal messages — users

### S1. Get user list — `getuserlist` (paginated)

Server:
```jsonc
{ "cmd": "getuserlist", "stn": true }   // true for first request, false for following pages
```

Terminal (page):
```jsonc
{
  "ret": "getuserlist",
  "sn": "zx12345678",
  "result": true,
  "count": 40,               // records in THIS package, max 40
  "from": 0,
  "to": 39,
  "record": [
    { "enrollid": 1, "admin": 0, "backupnum": 0 },
    { "enrollid": 2, "admin": 1, "backupnum": 0 },
    { "enrollid": 3, "admin": 0, "backupnum": 10 }
  ]
}
```
Each record = one credential (a user with several credentials appears several times).

Next page: server sends `{"cmd": "getuserlist", "stn": false}`; terminal answers with `from: 40, to: 79`, etc.

Empty:
```json
{ "ret": "getuserlist", "sn": "zx12345678", "result": true, "count": 0, "from": 0, "to": 0, "record": [] }
```
Fail:
```json
{ "ret": "getuserlist", "result": false, "reason": 1 }
```

### S2. Get user information — `getuserinfo`

Server:
```json
{ "cmd": "getuserinfo", "sn": "zx12345678", "enrollid": 1, "backupnum": 0 }
```
(`backupnum`: 0–9 fingerprint, 10 password, 11 card, 50 photo.)

Terminal success:
```jsonc
{
  "ret": "getuserinfo",
  "sn": "zx12345678",
  "result": true,
  "enrollid": 1,
  "name": "chingzou",
  "backupnum": 0,
  "admin": 0,
  "record": "aabbccddeeffggddssiifdjdkjfkjdsjlkjal"  // string for fp/photo(Base64), number for pwd/card
}
```
Examples in the source: backupnum 50 → `record` Base64 string; backupnum 11 → `record: 23532253`; backupnum 10 → `record: 23532253`.

Fail:
```json
{ "ret": "getuserinfo", "result": false, "reason": 1 }
```

### S3. Download (upload to device) user information — `setuserinfo`

```jsonc
// Fingerprint
{ "cmd": "setuserinfo", "enrollid": 1, "name": "chingzou", "backupnum": 0,  "admin": 0, "record": "aabbccddeeffggddssiifdjdkjfkjdsjlkjalflsgsadg" }
// Photo (Base64)
{ "cmd": "setuserinfo", "enrollid": 1, "name": "chingzou", "backupnum": 50, "admin": 0, "record": "<base64>" }
// Password
{ "cmd": "setuserinfo", "enrollid": 1, "name": "chingzou", "backupnum": 10, "admin": 0, "record": 12345678 }
// RFID card
{ "cmd": "setuserinfo", "enrollid": 1, "name": "chingzou", "backupnum": 11, "admin": 0, "record": 2352253 }
```

Terminal:
```json
{ "ret": "setuserinfo", "result": true }
```
```json
{ "ret": "setuserinfo", "result": false, "reason": 1 }
```

### S4. Delete user information — `deleteuser`

```jsonc
{ "cmd": "deleteuser", "enrollid": 1, "backupnum": 0 }
// backupnum: 0–9 one fp; 10 password; 11 card; 12 all fp; 13 everything (fp, card, pwd, name)
```
Reply: `{"ret":"deleteuser","result":true}` / `{"ret":"deleteuser","result":false,"reason":1}`

### S5. Get user name — `getusername`

```json
{ "cmd": "getusername", "sn": "zx12345678", "enrollid": 1 }
```
```jsonc
{ "ret": "getusername", "result": true, "record": "chingzou" }   // UTF-8 or ASCII
```
Fail: `{"ret":"getusername","result":false,"reason":1}`

### S6. Set user name — `setusername` (batch)

```jsonc
{
  "cmd": "setusername",
  "count": 50,                 // max 50 records per package
  "record": [
    { "enrollid": 1, "name": "chingzou" },
    { "enrollid": 2, "name": "chingzou2" }
  ]
}
```
Reply: `{"ret":"setusername","result":true}` / `{"ret":"setusername","result":false,"reason":1}`

### S7 / S8. Enable / disable user — `enableuser`

```jsonc
{ "cmd": "enableuser", "enrollid": 1, "enflag": 1 }   // 1 = enable, 0 = disable
```
Reply: `{"ret":"enableuser","sn":"zx12345678","result":true}` / `{"ret":"enableuser","result":false,"reason":1}`

### S9. Clean all users — `cleanuser`

```json
{ "cmd": "cleanuser" }
```
Reply: `{"ret":"cleanuser","sn":"zx12345678","result":true}` / `{"ret":"cleanuser","sn":"zx12345678","result":false,"reason":1}`

### S33. Set user profile — `setuserprofile`

```jsonc
{ "cmd": "setuserprofile", "enrollid": 1, "profile": "message" }  // max 200 bytes
// enrollid 0 = public information; enrollid 1, 2, 3… = personal information
```
Reply:
```json
{ "ret": "setuserprofile", "sn": "AI07F1234567", "enrollid": 1, "result": true }
```

### S34. Get user profile — `getuserprofile`

```json
{ "cmd": "getuserprofile", "enrollid": 1 }
```
```json
{ "ret": "getuserprofile", "sn": "AI07F1234567", "enrollid": 1, "record": "message", "result": true }
```

### S35. Remote add user — `adduser`

```jsonc
{
  "cmd": "adduser",
  "enrollid": 1,
  "backupnum": 50,    // 0–9 fp, 10 pwd, 11 card, 20–27 face, 30–37 palm, 50 photo
  "admin": 0,
  "name": "TEST",
  "flag": 10          // 10 = automatic registration
}
```
No reply format documented.

---

## 4. Server → Terminal messages — logs & system

### S10. Get new logs — `getnewlog` (paginated)

```json
{ "cmd": "getnewlog", "stn": true }
```
Terminal page:
```jsonc
{
  "ret": "getnewlog",
  "sn": "zx12345678",
  "result": true,
  "count": 1000,           // appears to be TOTAL number of logs (page is from/to)
  "from": 0,
  "to": 49,
  "record": [
    { "enrollid": 1, "time": "2016-03-25 13:49:30", "mode": 0, "inout": 0, "event": 0 },
    { "enrollid": 2, "time": "2016-03-25 13:49:30", "mode": 0, "inout": 0, "event": 1 }
  ]
}
```
Next page: `{"cmd":"getnewlog","stn":false}` → `from: 50, to: 99`, …
Empty: `{"ret":"getnewlog","sn":"zx12345678","result":true,"count":0,"from":0,"to":0,"record":[]}`
Fail: `{"ret":"getnewlog","result":false,"reason":1}`

### S11. Get all logs — `getalllog` (paginated)

```jsonc
{
  "cmd": "getalllog",
  "stn": true,
  "from": "2018-11-1",     // optional start date
  "to": "2018-12-30"       // optional end date
}
```
Replies: same structure as `getnewlog` with `"ret": "getalllog"`. Next page: `{"cmd":"getalllog","stn":false}`.
Fail: `{"ret":"getalllog","sn":"zx12345678","result":false,"reason":1}`

### S12. Clean all logs — `cleanlog`

```json
{ "cmd": "cleanlog" }
```
Reply: `{"ret":"cleanlog","sn":"zx12345678","result":true}` / `{"ret":"cleanlog","result":false,"reason":1}`

### S13. Initialize system — `initsys`

Deletes all users and all logs; settings are kept.
```json
{ "cmd": "initsys" }
```
Reply: `{"ret":"initsys","sn":"zx12345678","result":true}` / `{"ret":"initsys","result":false,"reason":1}`

### S14. Reboot — `reboot`

Device reboots immediately. **No reply.**
```json
{ "cmd": "reboot" }
```

### S15. Clean all administrators — `cleanadmin`

All admins become normal users.
```json
{ "cmd": "cleanadmin" }
```
Reply: `{"ret":"cleanadmin","sn":"zx12345678","result":true}` / `{"ret":"cleanadmin","sn":"zx12345678","result":false,"reason":1}`

### S16. Set time — `settime`

```json
{ "cmd": "settime", "cloudtime": "2016-03-25 13:49:30" }
```
Reply: `{"ret":"settime","sn":"zx12345678","result":true}` / `{"ret":"settime","result":false,"reason":1}`

### S26. Get time — `gettime`

```json
{ "cmd": "gettime" }
```
```json
{ "ret": "gettime", "sn": "zx12345678", "time": "2022-11-09 19:31:49" }
```
(No `result` field in the documented reply.)

### S17. Set terminal parameters — `setdevinfo`

All fields are optional; send only those to change, in any order.
```jsonc
{
  "cmd": "setdevinfo",
  "deviceid": 1,        // terminal id
  "language": 0,        // language code (table not provided in source)
  "volume": 6,          // 0–10, default 6
  "screensaver": 0,     // 0 = none; 1–255 = seconds of inactivity before screensaver
  "verifymode": 0,      // see verify mode table
  "sleep": 0,           // 0 = no sleep; 1 = sleep (fp sensor stays on). Boolean accepted: true=1, false=0
  "userfpnum": 3,       // fingerprints per user, 1–10, default 3
  "loghint": 1000,      // warn when free log space < this; 0 = no warning
  "reverifytime": 0     // re-verify time, 0–255 minutes
}
```
Minimal example: `{"cmd":"setdevinfo","volume":8,"sleep":1}`

Verify mode:

| Value | Enum | Meaning |
|---|---|---|
| 0 | VERIFY_KIND_FP_CARD_PWD | Card **or** fingerprint **or** password |
| 1 | VERIFY_KIND_CARD_ADD_FP | Card **and** fingerprint |
| 2 | VERIFY_KIND_PWD_ADD_FP | Password **and** fingerprint |
| 3 | VERIFY_KIND_CARD_ADD_FP_ADD_PWD | Card **and** fingerprint **and** password |
| 4 | VERIFY_KIND_CARD_ADD_PWD | Card **and** password |

Reply: `{"ret":"setdevinfo","sn":"zx12345678","result":true}` / `{"ret":"setdevinfo","sn":"zx12345678","result":false,"reason":1}`

### S18. Get terminal parameters — `getdevinfo`

```json
{ "cmd": "getdevinfo" }
```
```json
{
  "ret": "getdevinfo", "sn": "zx12345678", "result": true,
  "deviceid": 1, "language": 0, "volume": 0, "screensaver": 0, "verifymode": 0,
  "sleep": 0, "userfpnum": 3, "loghint": 1000, "reverifytime": 0
}
```
Fail: `{"ret":"getdevinfo","sn":"zx12345678","result":false,"reason":1}`

---

## 5. Server → Terminal messages — access control

### S19. Open door — `opendoor`

```jsonc
{ "cmd": "opendoor", "doornum": 1 }
// doornum 1–4: only for 4-door access controllers. Omit to open ALL doors.
// Normal access / attendance terminals do not need doornum.
```
Reply: `{"ret":"opendoor","sn":"zx12345678","result":true}` / `{"ret":"opendoor","sn":"zx12345678","result":false,"reason":1}`

### S20. Set access parameters — `setdevlock`

All fields optional.
```jsonc
{
  "cmd": "setdevlock",
  "opendelay": 5,       // door open (relay) delay
  "doorsensor": 0,      // 0 disabled, 1 NC (normally closed), 2 NO (normally open)
  "alarmdelay": 0,      // alarm if door left open > 1–255 minutes; 0 disabled
  "threat": 0,          // duress: 0 disabled, 1 open + alarm, 2 alarm only, 3 open only
  "InputAlarm": 0,      // 0 disabled, 1 alarm1 output, 2 alarm2 output  (note: capital letters)
  "antpass": 0,         // anti-passback: 0 disabled, 1 host inside, 2 host outside
  "interlock": 0,       // 0 disabled, 1 enabled
  "mutiopen": 0,        // multi-user open: 0 disabled, 1–4 users must verify together
  "tryalarm": 0,        // alarm after 1–10 wrong attempts; 0 disabled
  "tamper": 0,          // 0 disabled, 1 enabled
  "wgformat": 0,        // Wiegand: 0 = 26-bit, 1 = 34-bit
  "wgoutput": 0,        // Wiegand data: 0 enrollid, 1 "1"+enrollid, 2 deviceid+enrollid
  "cardoutput": 0,      // 1: if user has a card, fingerprint verify outputs card number on Wiegand
  "dayzone": [          // max 8 day zones; each max 5 time sections
    { "day": [
        { "section": "06:00~07:00" },
        { "section": "08:30~12:00" },
        { "section": "13:00~17:00" },
        { "section": "18:00~21:00" },
        { "section": "22:00~23:30" }
    ] },
    { "day": [ { "section": "00:01~23:59" } ] }
  ],
  "weekzone": [         // max 8 week zones; 7 entries Monday→Sunday, value = dayzone index
    { "week": [ {"day":1},{"day":1},{"day":1},{"day":1},{"day":1},{"day":2},{"day":2} ] },
    { "week": [ {"day":1},{"day":1},{"day":1},{"day":1},{"day":1},{"day":2},{"day":2} ] }
  ],
  "lockgroup": [        // multi-group combinations (see explanation)
    { "group": 1234 }, { "group": 126 }, { "group": 348 }, { "group": 139 }, { "group": 15 }
  ]
}
```
Minimal example:
```json
{ "cmd": "setdevlock", "dayzone": [ { "day": [ { "section": "07:00~18:00" } ] } ], "weekzone": [ { "week": [ { "day": 1 } ] } ] }
```
Reply: `{"ret":"setdevlock","sn":"zx12345678","result":true}` / `{"ret":"setdevlock","sn":"zx12345678","result":false,"reason":1}`

#### Time-zone resolution logic

`user.weekzone (e.g. 3)` → `weekzone[3]` → entry for today (e.g. Monday → dayzone 1) → `dayzone[1].sections` → if current time falls in a section → open; otherwise refuse.

Example: dayzone 1 = `00:01~23:59`, dayzone 2 = `00:00~00:00`. Weekzone 3 maps Monday→1, Tuesday→2. The user can open on Monday all day, never on Tuesday.
Indexes appear to be **1-based**; `00:00~00:00` means "no access".

#### `lockgroup` logic

Each digit of a `group` value is a user group number (1–9). Users of the listed groups must verify **at the same time** to open.
Example: Finance = group 1 (Tom, Obama, Lily), Sales = group 2 (Clinton, Bush), Warehouse = group 9 (Cruz, Hilari).
- `lockgroup 129` → one user from group 1 + one from group 2 + one from group 9.
- `lockgroup 119` → two users from group 1 + one from group 9.

### S21. Get access parameters — `getdevlock`

```json
{ "cmd": "getdevlock" }
```
Reply: same fields as `setdevlock`, plus `"ret": "getdevlock"`, `"sn"`, `"result": true`.
Fail (as written in source): `{"ret":"setdevlock","sn":"zx12345678","result":false,"reason":1}` — see Known issues.

### S22. Get user access parameters — `getuserlock`

```json
{ "cmd": "getuserlock", "enrollid": 1 }
```
```jsonc
{
  "ret": "getuserlock",
  "sn": "zx12345678",
  "result": true,
  "enrollid": 1,
  "weekzone": 1,      // door 1 (or the only door)
  "weekzone2": 1,     // door 2 (4-door controller only)
  "weekzone3": 1,     // door 3 (4-door controller only)
  "weekzone4": 1,     // door 4 (4-door controller only)
  "group": 1,         // 0 = no group; 1–9 = group number
  "starttime": "2016-03-25 01:00:00",   // validity start
  "endtime": "2099-03-25 23:59:00"      // validity end
}
```
Fail: `{"ret":"getuserlock","sn":"zx12345678","result":false,"reason":1}`

### S23. Set users access parameters — `setuserlock` (batch)

```jsonc
{
  "cmd": "setuserlock",
  "count": 40,
  "record": [
    { "enrollid": 1, "weekzone": 1, "weekzone2": 1, "weekzone3": 1, "weekzone4": 1, "group": 1,
      "starttime": "2016-03-25 01:00:00", "endtime": "2099-03-25 23:59:00" },
    { "enrollid": 2, "weekzone": 1, "group": 1,
      "starttime": "2016-03-25 01:00:00", "endtime": "2099-03-25 23:59:00" }
  ]
}
```
Reply: `{"ret":"setuserlock","sn":"zx12345678","result":true}` / `{"ret":"setuserlock","sn":"zx12345678","result":false,"reason":1}`

### S24. Delete user access parameters — `deleteuserlock`

```json
{ "cmd": "deleteuserlock", "enrollid": 1 }
```
Reply: `{"ret":"deleteuserlock","sn":"zx12345678","result":true}` / `{…"result":false,"reason":1}`

### S25. Clean all user access parameters — `cleanuserlock`

```json
{ "cmd": "cleanuserlock" }
```
Reply: `{"ret":"cleanuserlock","sn":"zx12345678","result":true}` / `{…"result":false,"reason":1}`

### S29. Get questionnaire — `getquestionnaire`

```json
{ "cmd": "getquestionnaire", "stn": true }
```
```json
{
  "ret": "getquestionnaire",
  "sn": "AI07F1234567",
  "result": true,
  "title": "inout event",
  "voice": "please select",
  "errmsg": "please select",
  "radio": true,
  "optionflag": 0,
  "usequestion": false,
  "useschedule": false,
  "card": 0,
  "items": ["in", "out", "onduty", "offduty"],
  "schedules": ["00:01-11:12*1", "11:30-12:30*3", "13:00-19:00*4", "00:00-00:00*0",
                "00:00-00:00*0", "00:00-00:00*0", "00:00-00:00*0", "00:00-00:00*0"]
}
```

### S30. Set questionnaire — `setquestionnaire`

```jsonc
{
  "cmd": "setquestionnaire",
  "title": "inout event",        // displayed at top
  "voice": "please select",      // spoken prompt (English or Chinese only); omit for no voice
  "errmsg": "please select",     // shown when a mandatory choice is missing (multiple choice mode)
  "radio": true,                 // single vs multiple choice (polarity not specified)
  "optionflag": 0,               // multiple choice: which items are mandatory (encoding not specified)
  "usequestion": true,           // enable questionnaire
  "useschedule": true,           // enable schedule
  "card": 0,                     // swipe card to start questionnaire
  "items": ["in", "out", "onduty", "offduty"],   // max 8 (multiple choice) / 16 (single choice)
  "schedules": ["00:01-11:12*1", "11:30-12:30*3", "13:00-19:00*4", "00:00-00:00*0",
                "00:00-00:00*0", "00:00-00:00*0", "00:00-00:00*0", "00:00-00:00*0"]  // max 8, format "HH:MM-HH:MM*N"
}
```
Reply: `{"ret":"setquestionnaire","sn":"AI07F1234567","result":true}` / `{"ret":"setquestionnaire","sn":"zx12345678","result":false,"reason":1}`

### S31. Get holidays — `getholiday`

```json
{ "cmd": "getholiday", "stn": true }
```
```json
{
  "ret": "getholiday",
  "sn": "AI07F1234567",
  "result": true,
  "holidays": [
    { "name": "holiday1", "startday": "01-01", "endday": "01-01", "shift": 0, "dayzone": 0 },
    { "name": "holiday2", "startday": "02-01", "endday": "02-07", "shift": 0, "dayzone": 0 },
    { "name": "holiday3", "startday": "05-01", "endday": "05-03", "shift": 0, "dayzone": 0 }
  ]
}
```

### S32. Set holidays — `setholiday`

```jsonc
{
  "cmd": "setholiday",
  "holidays": [            // max 30
    { "name": "holiday1",  // holiday name
      "startday": "01-01", // MM-DD
      "endday": "01-01",   // MM-DD
      "shift": 0,          // attendance shift
      "dayzone": 0 }       // day zone
  ]
}
```
Reply: `{"ret":"setholiday","sn":"AI07F1234567","result":true}` / `{"ret":"setholiday","sn":"zx12345678","result":false,"reason":1}`

---

## 6. Known issues and ambiguities in the source document

Implementation-relevant; verify each on real hardware.

### 6.1 Contradictions
1. **`mode` codes conflict** (see T2 table): `sendlog` says 1=fp, 2=pwd, 3=card, 8=face; the log notes and `getnewlog`/`getalllog` say 0=fp, 1=card, 2=pwd. Likely the newer AI firmware uses the first table. Log every raw value you receive before mapping.
2. `getuserlist` example comment says `backupnum 10` = RFID card, but the global table says 10 = password, 11 = card.
3. **`count` meaning differs**: in `getuserlist` it is the number of records in the page (max 40); in `getnewlog`/`getalllog` examples it is 1000 while the page holds 50 → probably the total.
4. `getdevlock` failure reply uses `"ret": "setdevlock"` (probable copy-paste error).
5. `getquestionnaire` reply contains the key `sn` **twice** (`zx12345678` and `AI07F1234567`) — duplicate keys; most JSON parsers keep the last one.
6. Rule "all keys lowercase" is violated by `InputAlarm`.
7. Since v1.8 "`sn` for all commands", yet many server examples and some replies omit `sn`.

### 6.2 Missing specifications
8. **Pagination stop condition** not defined (likely: `to + 1 >= count`, or page smaller than page size, or `count: 0`).
9. `reason` values: only `1` shown; no error code table. In `reg` it is a string.
10. No reply documented for `reboot` (intentional), `adduser`, and no failure format for `setuserprofile`, `getuserprofile`, `gettime`, `sendqrcode`, `getquestionnaire`, `getholiday`.
11. `language` code table referenced ("tips option below") but never provided.
12. `verifymode` in logs: only 13 (QR) documented.
13. `adduser.flag`: only 10 documented.
14. `optionflag` encoding, `radio` polarity, `schedules` `*N` suffix meaning, holiday `shift`/`dayzone` semantics: not explained.
15. `alarmdelay` unit stated as minutes (unusual; could be seconds).
16. No heartbeat/keep-alive, reconnection, or timeout behavior described.
17. Numeric values of door `event` enum only implied by C declaration order.
18. `getalllog` date format uses non-padded day (`2018-11-1`); padding tolerance unknown.

### 6.3 Typos preserved as real key names (must be sent exactly as spelled)
`mutiopen`, `antpass`, `tryalarm`, `enflag`, `stn`, `cloudtime`, `nosenduser`, `InputAlarm`.

### 6.4 Formatting defects fixed in this conversion
- `"sn","ZX…"`, `"cpusn","…"`, `"devinfo",{`, `"record",…`, `"backupnum",0`, `"from",0`, `"record",[` → colon instead of comma.
- Keys/values with trailing spaces (`"count "`, `"enrollid "`, `"record "`, `"time "`, `"ret":" getuserinfo "`, `" setdevlock "`…) → trimmed. **Real devices may actually send the spaces**: trim keys and `ret` values defensively when parsing.
- Missing commas (`"result":false "reason":1`), trailing commas, missing quote in `"sn":AI07F1234567"`, curly quotes → fixed.
- Source TOC numbering does not match the body (TOC skips 26 and 28; body has 26 `gettime`, 27 QR send, 28 QR reply).

### 6.5 Security notes
- **No TLS and no authentication**: identity rests only on `sn`, sent in clear text. Anyone on the network path can read biometric templates, photos, card numbers and PINs, or impersonate the server and send `opendoor`, `cleanuser`, `initsys`, `cleanadmin`.
- A device spoofing an `sn` can inject fake logs (attendance fraud).
- Mitigations on the server side: isolate devices on a dedicated VLAN/VPN, whitelist device IPs + `sn`, put a TLS-terminating reverse proxy only if the firmware supports `wss://` (not stated), log and alert on destructive commands, never expose port 7788 to the Internet.
- Biometric data and photos are personal data: store encrypted, restrict access, and check applicable data-protection law.
