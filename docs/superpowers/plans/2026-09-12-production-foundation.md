# UNG Production Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Package 1 manufacturing foundations to existing UNG-MDM and UNG-VECTOR while keeping UGATU a transaction layer and preserving current inventory behavior.

**Architecture:** UNG-MDM remains the source of truth for production definitions (materials, BOMs, routings, work centers, production versions). The deployed UNG-VECTOR service, sourced from `samtumwesigye2-create/-WMS400Vector`, owns production orders, reservations, issues, confirmations, scrap/rework, finished-goods receipt, lifecycle state, audit, and trace. UGATU production U-Codes are thin workflow mappings over VECTOR endpoints; no new UGATU service is created.

**Tech Stack:** Python, FastAPI, Pydantic, psycopg/PostgreSQL in VECTOR, existing UNG-MDM database abstraction, pytest/FastAPI TestClient.

**Spec:** `docs/superpowers/specs/2026-09-12-production-foundation-design.md`

## Global Constraints

- Do not create a new standalone production service.
- UGATU remains a transaction/U-Code layer, not a standalone service.
- Every production order carries `production_order_id`, `transaction_id`, and `correlation_id`.
- Allowed lifecycle: `CREATED -> RELEASED -> IN_PROGRESS -> COMPLETED -> CLOSED`; exceptional states are `BLOCKED` and `CANCELLED`.
- Materials cannot be issued before `RELEASED`.
- Repeated state-changing requests with the same `transaction_id` must be idempotent.
- No silent inventory mutations; every stock change must create a movement/audit record.
- Existing VECTOR inventory, reservation, health, and traceability endpoints must remain backward-compatible.
- Package 2 (MRP/ORACLE, NEXUS/PULSAR event transport) and Package 3 (costing, quality, NOC dashboards) remain out of scope.

---

### Task 1: Add typed production master-data endpoints to UNG-MDM

**Files:**
- Modify: `samtumwesigye2-create/UNG-MDM/app.py`
- Create: `samtumwesigye2-create/UNG-MDM/tests/test_production_master_data.py`

**Interfaces:**
- Consumes: existing `mdm_domains`, `mdm_records`, `connect()`, `sql()`, and IAM permission dependencies.
- Produces: `GET/POST /v1/production/materials`, `/boms`, `/work-centers`, `/routings`, `/production-versions` plus `GET /v1/production/versions/{version_code}`.

- [ ] **Step 1: Write failing MDM tests for production master data**

Create tests that seed the required domains and verify typed creation/lookup. Minimum assertions:

```python
def test_production_version_requires_active_references(client, write_headers):
    payload = {
        "version_code": "PV-BIKE-001",
        "material_code": "FG-BIKE",
        "bom_code": "BOM-BIKE-001",
        "routing_code": "RT-BIKE-001",
        "status": "active",
    }
    response = client.post("/v1/production/production-versions", json=payload, headers=write_headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "production_master_reference_invalid"


def test_create_and_read_complete_production_version(client, write_headers, read_headers):
    # create material, components, work center, BOM and routing first
    version = client.post(
        "/v1/production/production-versions",
        json={
            "version_code": "PV-BIKE-001",
            "material_code": "FG-BIKE",
            "bom_code": "BOM-BIKE-001",
            "routing_code": "RT-BIKE-001",
            "status": "active",
        },
        headers=write_headers,
    )
    assert version.status_code == 201
    read = client.get("/v1/production/versions/PV-BIKE-001", headers=read_headers)
    assert read.status_code == 200
    assert read.json()["material_code"] == "FG-BIKE"
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
pytest tests/test_production_master_data.py -v
```

Expected: FAIL because the `/v1/production/*` routes do not yet exist.

- [ ] **Step 3: Add typed Pydantic models and domain constants**

Add models equivalent to:

```python
class ProductionMaterialIn(BaseModel):
    material_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    base_uom: str = Field(min_length=1, max_length=16)
    material_type: str = Field(pattern=r"^(raw|semi_finished|finished|packaging)$")

class BomComponentIn(BaseModel):
    material_code: str
    quantity: float = Field(gt=0)
    uom: str

class BomIn(BaseModel):
    bom_code: str
    output_material_code: str
    base_quantity: float = Field(gt=0)
    components: list[BomComponentIn]
    status: str = Field(default="active", pattern=r"^(active|inactive)$")

class WorkCenterIn(BaseModel):
    work_center_code: str
    name: str
    capacity_units_per_hour: float = Field(gt=0)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")

class RoutingOperationIn(BaseModel):
    sequence: int = Field(gt=0)
    operation_code: str
    work_center_code: str
    standard_minutes: float = Field(gt=0)

class RoutingIn(BaseModel):
    routing_code: str
    output_material_code: str
    operations: list[RoutingOperationIn]
    status: str = Field(default="active", pattern=r"^(active|inactive)$")

class ProductionVersionIn(BaseModel):
    version_code: str
    material_code: str
    bom_code: str
    routing_code: str
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
```

Use existing `mdm_records` storage with domain codes `PROD_MATERIAL`, `PROD_BOM`, `PROD_WORK_CENTER`, `PROD_ROUTING`, and `PROD_VERSION`. Persist structured details in the existing `attributes` JSON column rather than introducing a second MDM storage model.

- [ ] **Step 4: Add validation helpers and typed routes**

Implement helpers that load active records and reject invalid references with:

```python
raise HTTPException(status_code=400, detail="production_master_reference_invalid")
```

For production versions, verify material, BOM, routing, and every routing work-center reference exist and are active. For BOMs, verify every component and output material exists. Return JSON-decoded attributes from typed GET endpoints.

- [ ] **Step 5: Run MDM tests**

Run:

```bash
pytest tests/test_production_master_data.py -v
```

Expected: PASS.

- [ ] **Step 6: Run existing MDM regression tests**

Run:

```bash
pytest -q
```

Expected: all prior tests plus production-master tests PASS.

- [ ] **Step 7: Commit MDM foundation**

```bash
git add app.py tests/test_production_master_data.py
git commit -m "feat(mdm): add production master data"
```

---

### Task 2: Add production-order schema and lifecycle engine to VECTOR

**Files:**
- Create: `samtumwesigye2-create/-WMS400Vector/production_control.py`
- Modify: `samtumwesigye2-create/-WMS400Vector/app.py`
- Create: `samtumwesigye2-create/-WMS400Vector/tests/test_production_control.py`

**Interfaces:**
- Consumes: `conn`, `auth`, `now`, `vector_inventory`, `vector_movements`, existing reservation patterns.
- Produces: production order tables, lifecycle validation, and base production endpoints.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_new_order_starts_created(client, auth_headers):
    r = client.post("/v1/production/orders", json={
        "production_order_id": "PO-1001",
        "transaction_id": "TX-1001",
        "correlation_id": "CORR-1001",
        "production_version_code": "PV-BIKE-001",
        "material_code": "FG-BIKE",
        "planned_quantity": 10,
        "plant_code": "PLANT-01",
        "storage_location": "FG-01"
    }, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["status"] == "CREATED"


def test_issue_before_release_is_rejected(client, auth_headers):
    r = client.post("/v1/production/orders/PO-1001/material-issues", json={
        "transaction_id": "TX-ISSUE-1",
        "correlation_id": "CORR-1001",
        "reservation_code": "PO-1001-RM-001"
    }, headers=auth_headers)
    assert r.status_code == 409
    assert r.json()["detail"] == "production_order_not_released"
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
pytest tests/test_production_control.py -v
```

Expected: FAIL because production routes are missing.

- [ ] **Step 3: Create production tables in `init_production_control()`**

Create tables:

```sql
vector_production_orders(
  id UUID PRIMARY KEY,
  production_order_id TEXT UNIQUE NOT NULL,
  production_version_code TEXT NOT NULL,
  material_code TEXT NOT NULL,
  planned_quantity DOUBLE PRECISION NOT NULL CHECK(planned_quantity>0),
  received_quantity DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK(received_quantity>=0),
  plant_code TEXT NOT NULL,
  storage_location TEXT NOT NULL,
  status TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
)
```

```sql
vector_production_transactions(
  id UUID PRIMARY KEY,
  transaction_id TEXT UNIQUE NOT NULL,
  production_order_id TEXT NOT NULL,
  ucode TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
)
```

```sql
vector_production_audit(
  id UUID PRIMARY KEY,
  production_order_id TEXT NOT NULL,
  transaction_id TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  action TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
)
```

Also create `vector_production_confirmations` and `vector_production_exceptions` with order ID, operation/reason fields, quantities, transaction ID, correlation ID, and timestamps.

- [ ] **Step 4: Implement lifecycle transition validation**

Use an explicit transition map:

```python
ALLOWED_TRANSITIONS = {
    "CREATED": {"RELEASED", "BLOCKED", "CANCELLED"},
    "RELEASED": {"IN_PROGRESS", "BLOCKED", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "BLOCKED", "CANCELLED"},
    "BLOCKED": {"RELEASED", "IN_PROGRESS", "CANCELLED"},
    "COMPLETED": {"CLOSED"},
    "CLOSED": set(),
    "CANCELLED": set(),
}
```

Invalid transitions return HTTP 409 `invalid_production_order_transition`.

- [ ] **Step 5: Implement idempotency helper**

Before every mutating action, query `vector_production_transactions` by `transaction_id`. If present, return the stored `result_json` without repeating inventory or lifecycle changes. After a successful action, store the exact response in the transaction table in the same DB transaction.

- [ ] **Step 6: Install production router into `app.py`**

Add:

```python
from production_control import init_production_control, install_production_routes
```

Call `init_production_control(conn)` from `init_db()` and `install_production_routes(app, conn, auth)` beside the existing module installers. Add `production-orders` and `production-trace` to `/v1/system` capabilities.

- [ ] **Step 7: Run lifecycle and existing regression tests**

```bash
pytest tests/test_production_control.py -v
pytest -q
```

Expected: PASS with existing inventory behavior unchanged.

- [ ] **Step 8: Commit VECTOR lifecycle foundation**

```bash
git add app.py production_control.py tests/test_production_control.py
git commit -m "feat(vector): add production order lifecycle"
```

---

### Task 3: Implement U-PP-001 through U-PP-004 (create, release, reserve, issue)

**Files:**
- Modify: `samtumwesigye2-create/-WMS400Vector/production_control.py`
- Modify: `samtumwesigye2-create/-WMS400Vector/inventory_control.py`
- Create: `samtumwesigye2-create/-WMS400Vector/tests/test_production_material_flow.py`

**Interfaces:**
- Consumes: Task 2 lifecycle/idempotency helpers, existing `vector_reservations`, `vector_inventory_status`, `vector_movements`.
- Produces: `/create`, `/release`, `/reservations`, and `/material-issues` production workflows mapped to U-Codes.

- [ ] **Step 1: Write failing reservation and issue tests**

Verify BOM quantity scaling uses:

```text
required_component_qty = bom_component_qty * planned_order_qty / bom_base_quantity
```

Test insufficient stock returns HTTP 409 `insufficient_available_inventory` without partially creating reservations.

- [ ] **Step 2: Implement `U-PP-001` create**

`POST /v1/production/orders` validates required identifiers, creates `CREATED` order, writes audit row with `ucode="U-PP-001"`, and records idempotent transaction result.

- [ ] **Step 3: Implement `U-PP-002` release**

`POST /v1/production/orders/{production_order_id}/release` validates current state `CREATED`, records master-data snapshot identifiers supplied by the caller/MDM adapter, transitions to `RELEASED`, and audits `U-PP-002`.

- [ ] **Step 4: Implement atomic `U-PP-003` reservations**

`POST /v1/production/orders/{production_order_id}/reservations` accepts resolved BOM components, validates all required inventory before writing any reservation, then creates reservations using existing `vector_reservations` semantics. Reservation codes use `PROD-{production_order_id}-{line_number}`.

- [ ] **Step 5: Implement `U-PP-004` material issue**

`POST /v1/production/orders/{production_order_id}/material-issues` consumes an active reservation only when order state is `RELEASED` or `IN_PROGRESS`, decrements physical stock, decrements reserved stock, writes a `vector_movements` row with `movement_type='production_issue'`, and stores/audits the idempotent result.

Update movement validation so `production_issue` can only be created through production control, not the generic movement endpoint.

- [ ] **Step 6: Run focused and regression tests**

```bash
pytest tests/test_production_material_flow.py -v
pytest -q
```

Expected: PASS; repeated `transaction_id` does not double-decrement inventory.

- [ ] **Step 7: Commit production material flow**

```bash
git add production_control.py inventory_control.py tests/test_production_material_flow.py
git commit -m "feat(vector): add production reservations and issues"
```

---

### Task 4: Implement U-PP-005 through U-PP-008 (confirm, scrap/rework, receipt, close)

**Files:**
- Modify: `samtumwesigye2-create/-WMS400Vector/production_control.py`
- Create: `samtumwesigye2-create/-WMS400Vector/tests/test_production_completion.py`

**Interfaces:**
- Consumes: production order lifecycle and transaction ledger.
- Produces: operation confirmation, exception, finished-goods receipt, and close workflows.

- [ ] **Step 1: Write failing completion tests**

Cover:
- first operation confirmation moves `RELEASED -> IN_PROGRESS`;
- duplicate confirmation transaction is idempotent;
- receipt before required operations are confirmed returns 409 `required_operations_incomplete`;
- scrap/rework records do not silently alter finished-goods stock;
- successful receipt increments finished-goods inventory exactly once;
- close only accepts `COMPLETED` orders.

- [ ] **Step 2: Implement `U-PP-005` operation confirmation**

`POST /v1/production/orders/{production_order_id}/confirmations` stores operation code, confirmed quantity, actor context, IDs, and timestamp. The first valid confirmation transitions `RELEASED` to `IN_PROGRESS`.

- [ ] **Step 3: Implement `U-PP-006` scrap/rework reporting**

`POST /v1/production/orders/{production_order_id}/exceptions` accepts `exception_type` in `{scrap,rework}`, quantity > 0, reason code, transaction ID, and correlation ID. Persist to `vector_production_exceptions` and audit it. Do not mutate finished-goods inventory here.

- [ ] **Step 4: Implement `U-PP-007` finished-goods receipt**

`POST /v1/production/orders/{production_order_id}/receipt` verifies required operation confirmations, posts quantity to `vector_inventory` at the order storage location, writes `vector_movements` with `movement_type='production_receipt'`, updates `received_quantity`, and transitions to `COMPLETED` when received quantity reaches planned quantity.

- [ ] **Step 5: Implement `U-PP-008` close**

`POST /v1/production/orders/{production_order_id}/close` only accepts `COMPLETED`, transitions to `CLOSED`, and records the transaction/audit result.

- [ ] **Step 6: Run focused and full tests**

```bash
pytest tests/test_production_completion.py -v
pytest -q
```

Expected: PASS with no double receipts under replay.

- [ ] **Step 7: Commit completion workflows**

```bash
git add production_control.py tests/test_production_completion.py
git commit -m "feat(vector): add production confirmation and completion"
```

---

### Task 5: Implement U-PP-009 and U-PP-010 status/trace views

**Files:**
- Modify: `samtumwesigye2-create/-WMS400Vector/production_control.py`
- Create: `samtumwesigye2-create/-WMS400Vector/tests/test_production_trace.py`

**Interfaces:**
- Consumes: production order, audit, confirmation, exception, reservation, transaction, inventory/movement tables.
- Produces: stable order status and complete correlation trace endpoints.

- [ ] **Step 1: Write failing trace test**

Build one order through create -> release -> reserve -> issue -> confirm -> receipt -> close using one correlation ID and assert every returned trace event contains the same `correlation_id`.

- [ ] **Step 2: Implement `U-PP-009` status endpoint**

`GET /v1/production/orders/{production_order_id}` returns order header, status, planned/received quantities, reservations, confirmations, and exceptions.

- [ ] **Step 3: Implement `U-PP-010` trace endpoint**

`GET /v1/production/orders/{production_order_id}/trace` returns a time-ordered event list assembled from `vector_production_audit`, relevant material movements, confirmations, exceptions, and transaction records. Every item exposes `production_order_id`, `transaction_id`, `correlation_id`, `event_type`, and timestamp.

- [ ] **Step 4: Run trace and regression tests**

```bash
pytest tests/test_production_trace.py -v
pytest -q
```

Expected: PASS and one `correlation_id` is visible across the full lifecycle.

- [ ] **Step 5: Commit status/trace support**

```bash
git add production_control.py tests/test_production_trace.py
git commit -m "feat(vector): add production status and trace"
```

---

### Task 6: Add UGATU U-Code catalog mapping without creating a service

**Files:**
- Create: `samtumwesigye2-create/-WMS400Vector/ugatu_production.py`
- Modify: `samtumwesigye2-create/-WMS400Vector/app.py`
- Create: `samtumwesigye2-create/-WMS400Vector/tests/test_ugatu_production.py`

**Interfaces:**
- Consumes: production endpoints from Tasks 2-5.
- Produces: U-Code catalog/metadata and workflow mapping for `U-PP-001` through `U-PP-010`.

- [ ] **Step 1: Write failing U-Code catalog test**

```python
def test_production_ucode_catalog(client, auth_headers):
    r = client.get("/v1/ugatu/production/codes", headers=auth_headers)
    assert r.status_code == 200
    codes = {row["code"] for row in r.json()["results"]}
    assert codes == {f"U-PP-{n:03d}" for n in range(1, 11)}
```

- [ ] **Step 2: Implement static production U-Code registry**

Expose exactly:

```python
PRODUCTION_UCODES = [
    ("U-PP-001", "Create Production Order", "POST", "/v1/production/orders"),
    ("U-PP-002", "Release Production Order", "POST", "/v1/production/orders/{production_order_id}/release"),
    ("U-PP-003", "Reserve Materials", "POST", "/v1/production/orders/{production_order_id}/reservations"),
    ("U-PP-004", "Issue Materials", "POST", "/v1/production/orders/{production_order_id}/material-issues"),
    ("U-PP-005", "Confirm Operation", "POST", "/v1/production/orders/{production_order_id}/confirmations"),
    ("U-PP-006", "Report Scrap/Rework", "POST", "/v1/production/orders/{production_order_id}/exceptions"),
    ("U-PP-007", "Receive Finished Goods", "POST", "/v1/production/orders/{production_order_id}/receipt"),
    ("U-PP-008", "Close Production Order", "POST", "/v1/production/orders/{production_order_id}/close"),
    ("U-PP-009", "View Order Status", "GET", "/v1/production/orders/{production_order_id}"),
    ("U-PP-010", "Trace Production Chain", "GET", "/v1/production/orders/{production_order_id}/trace"),
]
```

`GET /v1/ugatu/production/codes` returns this metadata. This is a layer over VECTOR functionality; it must not duplicate execution logic.

- [ ] **Step 3: Install UGATU production metadata router**

Register it in `app.py` beside the existing UGATU fulfillment layer.

- [ ] **Step 4: Run U-Code and full regression tests**

```bash
pytest tests/test_ugatu_production.py -v
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit UGATU production mapping**

```bash
git add app.py ugatu_production.py tests/test_ugatu_production.py
git commit -m "feat(ugatu): map production U-Codes"
```

---

### Task 7: Package 1 acceptance and deployment verification

**Files:**
- Modify: `samtumwesigye2-create/UNG-MDM/README.md`
- Modify: `samtumwesigye2-create/-WMS400Vector/README.md` if present; otherwise create it.

**Interfaces:**
- Consumes: all Package 1 APIs.
- Produces: reproducible acceptance evidence before Package 2 begins.

- [ ] **Step 1: Run complete repository test suites**

In UNG-MDM:

```bash
pytest -q
```

In `-WMS400Vector`:

```bash
pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run one complete production-order acceptance flow**

Use a test material/version and one correlation ID across U-PP-001 through U-PP-010. Verify the finished-goods balance increases by the receipt quantity and component balance decreases only by issued quantity.

- [ ] **Step 3: Replay mutating transaction IDs**

Repeat create/release/reserve/issue/confirm/receipt/close requests using the same transaction IDs and assert no stock, audit, reservation, or lifecycle action is duplicated.

- [ ] **Step 4: Verify live health after deployment**

Expected service health endpoints:

```text
UNG-MDM: /health -> healthy
UNG-VECTOR: /health -> {"status":"ok", ...}
UNG-VECTOR: /ready -> database connected
```

- [ ] **Step 5: Verify backward compatibility**

Exercise existing VECTOR `/v1/inventory`, `/v1/inventory-control/balances`, existing reservation flows, traceability routes, and `/v1/system`; confirm they continue to respond with their established behavior.

- [ ] **Step 6: Document the production API and U-Code mapping**

Add the ten U-Codes, lifecycle, master-data ownership, and example correlation trace to the READMEs.

- [ ] **Step 7: Commit acceptance documentation**

```bash
git add README.md
git commit -m "docs: document production foundation acceptance"
```

Package 1 is complete only after both repositories pass their full suites and the live deployed health/regression checks succeed.