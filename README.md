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


## Machine learning layer
UNG-CORE includes governed ML services for linear and logistic models, anomaly detection, forecasting, preprocessing, cross-validation and tuning, model registry/versioning, drift monitoring, controlled retraining, explainability, uncertainty, audited predictions, ensembles, serving policies, health dashboards and alerts, scheduled monitoring, ground-truth feedback, production performance gates, champion/challenger lifecycle management, automated rollback, probability calibration, human-review rules, and multi-feature linear/logistic models.

ML outputs remain decision-support signals. Promotion, rollback, serving, and review decisions are explicitly gated and audited.
