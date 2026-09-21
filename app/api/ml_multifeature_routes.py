from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, Principal
from app.services.audit import record_audit
from app.services.ml.evaluation import evaluate_predictions, train_test_split_indices
from app.services.ml.model_registry import (
    activate_model,
    get_active_model,
    get_model,
    record_validation,
    register_model,
    serialize_model,
)
from app.services.ml.multifeature import (
    predict_multifeature,
    serialize_multifeature_model,
    train_multifeature,
)

router = APIRouter(prefix="/v1/ml/multifeature", tags=["machine-learning-multifeature"])


class MultiFeatureTrainRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=160)
    algorithm: str
    x: list[list[float]] = Field(min_length=5, max_length=100000)
    y: list[float] = Field(min_length=5, max_length=100000)
    learning_rate: float = Field(default=0.01, gt=0)
    epochs: int = Field(default=1000, ge=1, le=100000)
    threshold: float = Field(default=0.5, gt=0, lt=1)
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    seed: int = 42
    preprocessing: str = "standardize"
    promote_if_passed: bool = False


class MultiFeaturePredictRequest(BaseModel):
    features: list[float] = Field(min_length=2, max_length=1000)
    context: dict = Field(default_factory=dict)


@router.post("/train")
async def train(
    body: MultiFeatureTrainRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.train")),
):
    try:
        if len(body.x) != len(body.y):
            raise ValueError("x and y must contain the same number of samples")
        train_idx, test_idx = train_test_split_indices(
            len(body.x), test_fraction=body.test_fraction, seed=body.seed
        )
        train_x = [body.x[i] for i in train_idx]
        train_y = [body.y[i] for i in train_idx]
        test_x = [body.x[i] for i in test_idx]
        test_y = [body.y[i] for i in test_idx]
        trained, training_metrics = train_multifeature(
            train_x,
            train_y,
            algorithm=body.algorithm,
            learning_rate=body.learning_rate,
            epochs=body.epochs,
            threshold=body.threshold,
            preprocessing=body.preprocessing,
        )
        artifact = serialize_multifeature_model(trained)
        predictions = predict_multifeature(artifact, test_x)
        task = "regression" if body.algorithm == "multivariate_linear_regression" else "binary_classification"
        evaluation = evaluate_predictions(
            task=task,
            actual=test_y,
            predicted=predictions["outputs"],
            threshold=body.threshold,
            gates=(),
        )
        row = await register_model(
            db,
            model_key=body.model_key,
            algorithm=body.algorithm,
            artifact=artifact,
            metrics={"training": training_metrics},
            metadata={"feature_count": artifact["feature_count"]},
            created_by=principal.subject,
        )
        row = await record_validation(
            db,
            body.model_key,
            row.version,
            task=evaluation.task,
            metrics=evaluation.metrics,
            baseline_metrics=None,
            baseline_improvement=None,
            gates=evaluation.gates,
            passed=evaluation.passed,
            validated_by=principal.subject,
        )
        promoted = False
        if body.promote_if_passed and evaluation.passed:
            row = await activate_model(db, body.model_key, row.version)
            promoted = True
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "model": serialize_model(row),
        "evaluation": {
            "passed": evaluation.passed,
            "metrics": evaluation.metrics,
            "gates": evaluation.gates,
        },
        "promoted": promoted,
    }


async def _resolve(db, model_key: str, version: int | None):
    row = await (get_active_model(db, model_key) if version is None else get_model(db, model_key, version))
    if row is None:
        raise LookupError("model not found")
    return row


@router.post("/{model_key}/predict")
async def predict_active(
    model_key: str,
    body: MultiFeaturePredictRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.predict")),
):
    return await _predict(model_key, None, body, db, principal)


@router.post("/{model_key}/versions/{version}/predict")
async def predict_version(
    model_key: str,
    version: int,
    body: MultiFeaturePredictRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.predict")),
):
    return await _predict(model_key, version, body, db, principal)


async def _predict(model_key, version, body, db, principal):
    try:
        row = await _resolve(db, model_key, version)
        model = serialize_model(row)
        if model["algorithm"] not in {"multivariate_linear_regression", "multivariate_logistic_regression"}:
            raise ValueError("model is not a multi-feature model")
        result = predict_multifeature(model["artifact"], [body.features])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    output = result["outputs"][0]
    classification = result["classifications"][0] if result["classifications"] is not None else None
    audit = await record_audit(
        db,
        AuditEventIn(
            actor_id=principal.subject,
            action="ml.multifeature_prediction",
            resource_type="ml_model",
            resource_id=f"{model_key}:v{row.version}",
            payload={
                "model_key": model_key,
                "model_version": row.version,
                "algorithm": row.algorithm,
                "input": {"features": body.features},
                "output": {"value": output, "classification": classification},
                "context": body.context,
            },
        ),
    )
    return {
        "model_key": model_key,
        "model_version": row.version,
        "algorithm": row.algorithm,
        "features": body.features,
        "output": output,
        "classification": classification,
        "audit_event_id": audit.event_id,
        "occurred_at": audit.occurred_at,
    }
