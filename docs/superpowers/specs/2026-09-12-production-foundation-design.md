# UNG Production Foundation Design

## Purpose
Extend the existing UNG architecture with manufacturing/production-planning foundations without creating a new standalone production system.

## Ownership Boundaries

### UNG-MDM
Owns production master data:
- Material master records used for production
- Bills of material (BOM)
- Routings and routing operations
- Work centers
- Production versions binding material + BOM + routing

MDM is the source of truth for definitions. It does not own stock quantities or production execution state.

### UNG-VECTOR / WMS400Vector
Owns production inventory and execution state:
- Plant and storage-location inventory views
- Production orders and lifecycle state
- Material reservations
- Goods issue to production
- Operation confirmations
- Scrap/rework reporting
- Finished-goods receipt
- Production traceability

The deployed Railway service is sourced from `samtumwesigye2-create/-WMS400Vector` and already contains inventory/material/traceability modules plus `ugatu_fulfillment.py`; the production extension must follow those existing patterns.

### UGATU Layer
UGATU remains a transaction/U-Code layer, not a standalone service. Production U-Codes are implemented against existing service workflows and share the same IDs used by MDM/VECTOR.

Initial production U-Codes:
- `U-PP-001` Create Production Order
- `U-PP-002` Release Production Order
- `U-PP-003` Reserve Materials
- `U-PP-004` Issue Materials
- `U-PP-005` Confirm Operation
- `U-PP-006` Report Scrap/Rework
- `U-PP-007` Receive Finished Goods
- `U-PP-008` Close Production Order
- `U-PP-009` View Order Status
- `U-PP-010` Trace Production Chain

## Shared Identifiers
Every production order carries:
- `production_order_id`: stable business identifier for the order
- `transaction_id`: identifier for the current state-changing transaction
- `correlation_id`: end-to-end trace identifier propagated across MDM, VECTOR, NEXUS/PULSAR later

These identifiers must be included in audit/event payloads and exposed by status/trace endpoints.

## Production Order Lifecycle
Allowed primary state sequence:

`CREATED -> RELEASED -> IN_PROGRESS -> COMPLETED -> CLOSED`

Exceptional states:
- `BLOCKED`
- `CANCELLED`

Rules:
- Materials cannot be issued before `RELEASED`.
- Operation confirmation transitions a released order to `IN_PROGRESS`.
- Finished-goods receipt can complete the order only when required confirmations are satisfied.
- `CLOSED` is terminal for normal execution.
- Every state change is auditable and correlated.

## Data Flow
1. MDM defines material, BOM, routing, work center, and production version.
2. `U-PP-001` creates a production order in VECTOR referencing an active production version.
3. `U-PP-002` validates master data and releases the order.
4. `U-PP-003` creates material reservations from the BOM quantities.
5. `U-PP-004` posts material issue movements against reservations.
6. `U-PP-005` records routing-operation confirmations.
7. `U-PP-006` records scrap/rework quantities and reasons.
8. `U-PP-007` posts finished-goods receipt and updates stock.
9. `U-PP-008` closes the production order.
10. `U-PP-009` and `U-PP-010` expose current state and complete trace history.

## API/Behavior Requirements
- Idempotency for state-changing U-Code requests using `transaction_id`.
- Referential validation for material/BOM/routing/work-center/version references.
- Explicit 4xx responses for invalid transitions or insufficient stock.
- No silent stock changes.
- Audit record for every state-changing production action.
- Existing non-production VECTOR inventory behavior must remain backward-compatible.

## Testing Requirements
- Unit tests for lifecycle transitions and invalid transitions.
- Unit tests for BOM reservation quantity calculation.
- Inventory tests for issue/receipt and insufficient-stock rejection.
- Idempotency tests for repeated `transaction_id`.
- Traceability test proving one `correlation_id` appears across the full order lifecycle.
- Regression tests for existing VECTOR health and inventory endpoints.

## Out of Scope for Package 1
- MRP, forecasting, capacity leveling, and production scheduling (Package 2 / ORACLE)
- NEXUS/PULSAR production-event transport (Package 2)
- Standard costing, variance analysis, quality-management workflows, and NOC production dashboards (Package 3)
