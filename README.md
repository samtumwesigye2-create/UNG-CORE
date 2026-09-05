# UNG-CORE

Standalone enterprise foundation for the Uganda National Grid software ecosystem.

## Responsibilities
- canonical enterprise service bootstrap
- IAM boundary contract to UNG-IAM
- PostgreSQL-ready persistence
- immutable-style audit/event ledger
- health/readiness endpoints
- Data Relay publishing contract
- shared conventions for downstream UNG services

## Run
`uvicorn app.main:app --reload`

## Endpoints
- `GET /health`
- `GET /ready`
- `POST /v1/audit/events`
- interactive docs at `/docs`

## Production
Set `DATABASE_URL`, `IAM_BASE_URL`, and `DATA_RELAY_BASE_URL`. Railway can use the included Procfile or Dockerfile.
