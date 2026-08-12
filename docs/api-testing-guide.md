# LiMon API testing guide

This guide shows how to test every LiMon Adjustment Manager route through
Swagger UI or `curl`. Examples use the hybrid-simulation seed context:

```text
API:            http://127.0.0.1:8001
asofdate:       2026-08-06
asofdateflow:   2026-08-07T11:14:09
rowId:          SIM-ROW-0001
FO system:      Orchestrade
```

Replace these values with results returned by your running database. Do not
copy the example row ID into another snapshot.

## Swagger setup

1. Start the backend.
2. Open [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs). If the API
   uses port `8000`, change the URL accordingly.
3. Expand **Authentication** → `POST /api/auth/mock-login`.
4. Click **Try it out**, use `francois.functional`, then **Execute**.
5. The browser stores the HTTP-only session cookie automatically. Subsequent
   Swagger requests use that session.
6. Select an as-of date, version and row through read endpoints before testing
   previews or commits.

Swagger cannot display the HTTP-only cookie to JavaScript, which is expected.
Confirm the session with `GET /api/auth/me`.

## Roles used for testing

| Username | Role | Use it to test |
|---|---|---|
| `alice.reader` | `reader` | Reads and previews; commits must return `403` |
| `francois.functional` | `functional_admin` | Commit, cancel, proxy, batch and revert |
| `thomas.technical` | `technical_admin` | Health and reconciliation |
| `unauthorized.user` | no application role | Authentication succeeds but protected routes return `403` |

Mock login routes return `404` when `AUTH_MODE` is not `mock`.

## Curl setup

Use a cookie jar so every command shares the authenticated session:

```bash
export LIMON_API=http://127.0.0.1:8001
export LIMON_COOKIE=/tmp/limon-api-cookie.txt

curl -sS -c "$LIMON_COOKIE" \
  -H 'Content-Type: application/json' \
  -d '{"username":"francois.functional"}' \
  "$LIMON_API/api/auth/mock-login"
```

For all following commands:

```bash
curl -sS -b "$LIMON_COOKIE" "$LIMON_API/api/auth/me"
```

Do not store database credentials in these commands. The browser and API never
need to receive a PostgreSQL or Vertica password from the user.

## Recommended safe test order

Routes marked **read-only** or **preview** do not write business output. Routes
marked **commit** append output and audit rows.

1. Login and verify identity.
2. Read dates and versions.
3. Search a trade, then inspect detail and lineage.
4. Inspect mappings.
5. Run impact and preview.
6. Copy `rowVersion` from preview.
7. Commit only in a development snapshot.
8. Read history and lineage again.
9. Revert the committed batch if required.

## Authentication routes

### `GET /api/auth/mock-users` — read-only

Lists development identities. No session is required.

```bash
curl -sS "$LIMON_API/api/auth/mock-users"
```

### `POST /api/auth/mock-login` — session change

Request:

```json
{
  "username": "francois.functional"
}
```

Expected response contains:

```json
{
  "userId": "mock-functional-001",
  "email": "francois.functional@cacib.example",
  "displayName": "François Functional",
  "roles": ["functional_admin"],
  "permissions": ["business_write", "preview", "read"],
  "authenticated": true,
  "hasAccess": true
}
```

### `GET /api/auth/me` — read-only

Returns the current identity. Expected failure without a cookie: `401`.

### `POST /api/auth/logout` — session change

Clears the session and returns `204 No Content`.

## Snapshot and trade routes

### `GET /api/asofdates` — read-only

```bash
curl -sS -b "$LIMON_COOKIE" "$LIMON_API/api/asofdates"
```

Example response:

```json
["2026-08-06", "2026-08-05"]
```

### `GET /api/versions` — read-only

```bash
curl -sS -b "$LIMON_COOKIE" \
  "$LIMON_API/api/versions?asofdate=2026-08-06"
```

Example response:

```json
["2026-08-07T11:14:09"]
```

### `GET /api/fo-systems` — read-only

Returns distinct FO systems for one exact snapshot. Supply `asofdate` and
`asofdateflow` as query parameters, then use one returned value in batch search.

### `GET /api/trades/batch-filters` — read-only

Returns the allowlisted filter names and types supported by the batch builder.

### `POST /api/trades/batch-search` — read-only

Returns only active, adjustable trades. Filtering and pagination happen on the
server so the browser never loads a complete output snapshot.

The batch UI translates AG Grid floating-filter models into this allowlisted
payload. Text columns use contains matching, amount supports equality/ranges,
and maturity supports date comparisons/ranges.

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "foSystem": "Orchestrade",
  "filters": {
    "portfolio": "LIQUIDITY",
    "currency": "EUR",
    "maturityDateFrom": "2026-08-06",
    "maturityDateTo": "2026-12-31",
    "amountMin": 100000,
    "amountMax": 5000000
  },
  "page": 1,
  "pageSize": 25
}
```

Unknown filter names return `422`. Raw SQL expressions are never accepted.

### `GET /api/trades` — read-only

Required filters in normal UI usage are `search` and `foSystem`. `pageSize` is
limited to 100 to protect the API from full-snapshot reads.

```bash
curl -sS -G -b "$LIMON_COOKIE" "$LIMON_API/api/trades" \
  --data-urlencode 'asofdate=2026-08-06' \
  --data-urlencode 'asofdateflow=2026-08-07T11:14:09' \
  --data-urlencode 'search=OT-982731' \
  --data-urlencode 'foSystem=Orchestrade' \
  --data-urlencode 'page=1' \
  --data-urlencode 'pageSize=10'
```

Example response shape:

```json
{
  "items": [
    {
      "rowId": "SIM-ROW-0001",
      "tradeNo": "OT-982731",
      "foSystem": "Orchestrade",
      "recordType": "BASE",
      "lineageRole": "ORIGINAL",
      "isActive": true
    }
  ],
  "total": 1
}
```

### `GET /api/trades/{row_id}` — read-only

```bash
curl -sS -G -b "$LIMON_COOKIE" \
  "$LIMON_API/api/trades/SIM-ROW-0001" \
  --data-urlencode 'asofdate=2026-08-06' \
  --data-urlencode 'asofdateflow=2026-08-07T11:14:09'
```

An already-cancelled trade is returned with `isCancelled: true` and no active
row. It remains readable but cannot be adjusted until its cancellation is
reverted.

### `GET /api/trades/{row_id}/lineage` — read-only

Uses the same context query parameters as trade detail. Response shape:

```json
{
  "isAdjusted": true,
  "adjustmentCount": 1,
  "activeRow": {"recordType": "ADJUSTMENT_REPLACEMENT"},
  "rows": [
    {"role": "ORIGINAL", "isActive": false, "row": {}},
    {"role": "REVERSAL", "isActive": false, "row": {}},
    {"role": "ADJUSTED", "isActive": true, "row": {}}
  ]
}
```

### `GET /api/trades/{row_id}/history` — read-only

```bash
curl -sS -b "$LIMON_COOKIE" \
  "$LIMON_API/api/trades/SIM-ROW-0001/history"
```

Returns committed and reverted operations across snapshots for that trade.

### `GET /api/adjustments/history` — read-only

Without filters, returns the global register. To filter one snapshot:

```bash
curl -sS -G -b "$LIMON_COOKIE" "$LIMON_API/api/adjustments/history" \
  --data-urlencode 'asofdate=2026-08-06' \
  --data-urlencode 'asofdateflow=2026-08-07T11:14:09'
```

## Mapping routes

### `GET /api/mappings/fields` — read-only

Lists fields controlled by `mapping_config.py` and their manifest-selected
Parquet source.

```bash
curl -sS -b "$LIMON_COOKIE" "$LIMON_API/api/mappings/fields"
```

### `GET /api/mappings/values` — read-only

```bash
curl -sS -G -b "$LIMON_COOKIE" "$LIMON_API/api/mappings/values" \
  --data-urlencode 'field=exposureClass' \
  --data-urlencode 'search=sov' \
  --data-urlencode 'limit=50'
```

Example response:

```json
{
  "field": {
    "fieldName": "exposureClass",
    "mappingName": "exposure_class_mapping",
    "outputColumn": "EXPOSURE_CLASS"
  },
  "values": ["SOVEREIGN"]
}
```

### `GET /api/mappings/{mapping_name}/rows` — read-only

```bash
curl -sS -G -b "$LIMON_COOKIE" \
  "$LIMON_API/api/mappings/exposure_class_mapping/rows" \
  --data-urlencode 'search=BANK' \
  --data-urlencode 'page=1' \
  --data-urlencode 'pageSize=20'
```

Expected `422`: mapping name is unknown, manifest path is missing, Parquet is
unreadable, or the configured output column does not exist.

## Standard adjustment routes

### `POST /api/adjustments/impact` — preview

Shows which calculation stages a draft would trigger without reading or
writing a trade.

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "rowId": "SIM-ROW-0001",
  "changes": {
    "amount": 1250000,
    "exposureClass": "SOVEREIGN"
  }
}
```

Example response:

```json
{
  "impactedStages": [
    "buckets",
    "eur_amount",
    "hqla",
    "reporting_lines",
    "lcr_impacts"
  ]
}
```

### `POST /api/adjustments/preview` — preview

Use the same body as impact. The response contains:

- `original`: effective row read from output;
- `cancellation`: negative reversal that would be inserted;
- `replacement`: recalculated active row that would be inserted;
- `differences`: before/after calculated values;
- `mappingOverrides`: exact Parquet references used;
- `rowVersion`: required by commit.

No output or metadata row is written.

### `POST /api/adjustments/commit` — commit

Use `rowVersion` returned by the latest preview and a UUID that represents this
one commit intention:

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "rowId": "SIM-ROW-0001",
  "changes": {
    "amount": 1250000,
    "exposureClass": "SOVEREIGN"
  },
  "reason": "Correct classification after source review",
  "expectedVersion": "COPY-rowVersion-FROM-preview",
  "idempotencyKey": "a9baa15f-2062-448d-845b-402842ace870"
}
```

Example response:

```json
{
  "adjustmentBatchId": "ADJ-20260812-123456789012",
  "status": "COMMITTED",
  "insertedRecords": 2,
  "adjustedTrades": 1
}
```

Retrying the exact request with the same idempotency key returns the existing
result. Reusing that key for a different user intention is invalid application
behavior. Expected `409`: the effective row changed after preview.

## Cancellation routes

The UI calls cancellation preview internally; users see only **Cancel trade**.

### `POST /api/adjustments/cancel/preview` — preview

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "rowId": "SIM-ROW-0001"
}
```

Copy `rowVersion` from the response.

### `POST /api/adjustments/cancel/commit` — commit

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "rowId": "SIM-ROW-0001",
  "reason": "Trade cancelled by source system owner",
  "expectedVersion": "COPY-rowVersion-FROM-cancellation-preview",
  "idempotencyKey": "f2ddf44c-4474-49e0-a1e9-b4b465125403"
}
```

This appends one `ADJUSTMENT_CANCEL` row. Nothing is deleted. Expected `422`:
the trade is already cancelled and has no effective row.

## Proxy routes

Use the same UUID as `draftId` for preview and commit. It deterministically
generates a trade number such as `PROXY-20260806-4ED537C0`.

### `POST /api/adjustments/proxy/preview` — preview

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "draftId": "4ed537c0-5ad0-4b3f-b296-ced603c44b31",
  "fields": {
    "foSystem": "Orchestrade",
    "targetInstrumentType": "SECURITY",
    "isin": "FR0000000001",
    "issue": "Development proxy",
    "valueDate": "2026-08-06",
    "maturityDate": "2026-08-25",
    "currency": "EUR",
    "amount": 500000,
    "portfolio": "LIQUIDITY",
    "counterparty": "CP_PROXY"
  }
}
```

### `POST /api/adjustments/proxy/commit` — commit

Use the preview body and add:

```json
{
  "reason": "Temporary proxy for missing source trade",
  "idempotencyKey": "7f77c364-e274-40cb-8139-aa86efca19c4"
}
```

In Swagger, add those properties at the root beside `context`, `draftId`, and
`fields`. Commit inserts one `PROXY` row.

## Batch routes

All items must use the same snapshot context, and the same row cannot appear
twice.

### `POST /api/adjustments/batch/preview` — preview

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "items": [
    {
      "rowId": "SIM-ROW-0001",
      "changes": {"amount": 1250000}
    },
    {
      "rowId": "SIM-ROW-0002",
      "changes": {"maturityDate": "2026-09-30"}
    }
  ]
}
```

Copy each item's `rowVersion` from `items` in the response.

### `POST /api/adjustments/batch/commit` — commit

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "items": [
    {
      "rowId": "SIM-ROW-0001",
      "changes": {"amount": 1250000},
      "expectedVersion": "COPY-FIRST-rowVersion"
    },
    {
      "rowId": "SIM-ROW-0002",
      "changes": {"maturityDate": "2026-09-30"},
      "expectedVersion": "COPY-SECOND-rowVersion"
    }
  ],
  "reason": "Apply reviewed corrections for the reporting run",
  "idempotencyKey": "20c2edc2-7487-42f1-ac9c-cae01aa2af02"
}
```

Expected `409`: at least one item changed after preview. No item should be
silently accepted as a partial business batch.

## Revert route

### `POST /api/adjustments/{batch_id}/revert` — commit

Get `batch_id`, `rowId`, `baseAsOfDate`, and `baseAsOfDateFlow` from trade
history or the adjustment register.

```json
{
  "context": {
    "asofdate": "2026-08-06",
    "asofdateflow": "2026-08-07T11:14:09"
  },
  "rowId": "SIM-ROW-0001",
  "reason": "Revert after functional review",
  "idempotencyKey": "c36303ac-fc38-41a9-9ca2-7ee879920746"
}
```

Example URL:

```text
POST /api/adjustments/ADJ-20260812-123456789012/revert
```

Revert creates a new linked `REVERT` batch. It never deletes the target batch.
An already-reverted commit is not revertible again.

## Operational routes

### `GET /api/health` — technical read

Requires `thomas.technical`. Response includes storage mode, project, output
health, metadata health and active simulated failure point.

### `POST /api/adjustments/{batch_reference}/reconcile` — technical write

Requires `thomas.technical` and hybrid storage. The body is empty:

```bash
curl -sS -b "$LIMON_COOKIE" -X POST \
  "$LIMON_API/api/adjustments/ADJ-20260812-123456789012/reconcile"
```

Use only for a register entry with status `RECONCILIATION_REQUIRED`. The route
checks output rows by stable batch reference and finalizes missing metadata. It
does not insert the output rows again.

## Common responses and diagnosis

| Status | Meaning | What to check |
|---:|---|---|
| `200` | Request succeeded | Inspect response and refresh related reads |
| `204` | Logout succeeded | No response body is expected |
| `401` | No valid session | Login again; check cookie and expiry |
| `403` | Role lacks permission | Use the role required by the route |
| `404` | Mock login disabled or route/reference unavailable | Check `AUTH_MODE`, URL and identifier |
| `409` | Preview is stale or state conflicts | Refresh trade and generate a new preview |
| `422` | Payload/domain validation failed | Read the response `detail`; verify context, field and value |
| `503` | Output/metadata infrastructure failure | Inspect health and reconciliation state |

FastAPI request-schema validation also returns `422` with a structured `detail`
array. Domain validation returns `422` with a human-readable `detail` string.

## Testing authorization deliberately

Useful negative tests:

1. Login as `alice.reader` and call `/api/adjustments/preview`: expect success.
2. With the same identity call `/api/adjustments/commit`: expect `403`.
3. Login as `thomas.technical` and call `/api/health`: expect success.
4. With that identity call a business commit: expect `403`.
5. Logout and call `/api/asofdates`: expect `401`.

These checks confirm that authorization is enforced by FastAPI rather than only
by hidden buttons in React.
