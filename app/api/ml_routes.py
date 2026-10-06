import logging
import os

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.api.security import SESSION_COOKIE, bearer, current_principal
from app.core.config import settings

from app.services.ml.linear_regression import predict_linear, train_linear_regression
from app.services.ml.logistic_regression import predict_logistic, train_logistic_regression
from app.services.ml.anomaly_detection import AnomalyBaseline, detect_anomalies, fit_anomaly_baseline, score_anomalies
from app.services.ml.time_series import forecast_time_series
from app.services.ml.clustering import fit_kmeans, predict_clusters

_log = logging.getLogger("ung_core.ml_compute")
ML_COMPUTE_PERMISSIONS = {"ung.core.ml.predict", "ung.core.ml.train", "ung.core.admin"}


def _is_production() -> bool:
    return any(str(v or "").strip().lower() in {"production", "prod"} for v in (settings.environment, os.getenv("ENV"), os.getenv("RAILWAY_ENVIRONMENT"), os.getenv("RAILWAY_ENVIRONMENT_NAME")))


def _public_compute_allowed() -> bool:
    raw = os.getenv("CORE_ML_PUBLIC_COMPUTE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return not _is_production()


async def ml_compute_guard(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> None:
    """Protect CPU-bound ML endpoints with IAM permissions in production."""
    if _public_compute_allowed():
        if credentials is None and not session_token:
            _log.warning("anonymous /v1/ml compute request allowed (non-production or CORE_ML_PUBLIC_COMPUTE=true)")
        return None
    principal = await current_principal(credentials, session_token)
    if not ML_COMPUTE_PERMISSIONS.intersection(principal.permissions):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: ung.core.ml.predict")
    return None


# These pure-Python loops are synchronous so FastAPI executes them in its threadpool rather than
# blocking the event loop while training or scoring large inputs.
router = APIRouter(prefix="/v1/ml", tags=["machine-learning"], dependencies=[Depends(ml_compute_guard)])


class LinearRegressionTrainRequest(BaseModel):
    x: list[float] = Field(min_length=2, max_length=10000)
    y: list[float] = Field(min_length=2, max_length=10000)
    learning_rate: float = Field(default=0.01, gt=0)
    epochs: int = Field(default=1000, ge=1, le=100000)


class LinearRegressionTrainResponse(BaseModel):
    weight: float
    bias: float
    learning_rate: float
    epochs: int
    mse: float
    r2: float | None
    predictions: list[float]


class LinearRegressionPredictRequest(BaseModel):
    x: list[float] = Field(min_length=1, max_length=10000)
    weight: float
    bias: float


@router.post("/linear-regression/train", response_model=LinearRegressionTrainResponse)
def train_linear(request: LinearRegressionTrainRequest):
    try:
        result = train_linear_regression(request.x, request.y, learning_rate=request.learning_rate, epochs=request.epochs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LinearRegressionTrainResponse(**result.__dict__)


@router.post("/linear-regression/predict")
def predict(request: LinearRegressionPredictRequest):
    try:
        predictions = predict_linear(request.x, weight=request.weight, bias=request.bias)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"predictions": predictions}


class LogisticRegressionTrainRequest(BaseModel):
    x: list[float] = Field(min_length=2, max_length=10000)
    y: list[int] = Field(min_length=2, max_length=10000)
    learning_rate: float = Field(default=0.01, gt=0)
    epochs: int = Field(default=1000, ge=1, le=100000)
    threshold: float = Field(default=0.5, gt=0, lt=1)


class LogisticRegressionPredictRequest(BaseModel):
    x: list[float] = Field(min_length=1, max_length=10000)
    weight: float
    bias: float
    threshold: float = Field(default=0.5, gt=0, lt=1)


@router.post("/logistic-regression/train")
def train_logistic(request: LogisticRegressionTrainRequest):
    try:
        result = train_logistic_regression(request.x, request.y, learning_rate=request.learning_rate, epochs=request.epochs, threshold=request.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.__dict__


@router.post("/logistic-regression/predict")
def predict_logistic_route(request: LogisticRegressionPredictRequest):
    try:
        probabilities, predictions = predict_logistic(request.x, weight=request.weight, bias=request.bias, threshold=request.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"probabilities": probabilities, "predictions": predictions}


class AnomalyFitRequest(BaseModel):
    values: list[float] = Field(min_length=3, max_length=100000)
    method: str = "zscore"
    threshold: float | None = Field(default=None, gt=0)


class AnomalyScoreRequest(BaseModel):
    values: list[float] = Field(min_length=1, max_length=100000)
    method: str = "zscore"
    center: float
    scale: float = Field(gt=0)
    threshold: float = Field(default=3.0, gt=0)


class AnomalyDetectRequest(BaseModel):
    values: list[float] = Field(min_length=3, max_length=100000)
    method: str = "zscore"
    threshold: float | None = Field(default=None, gt=0)


@router.post("/anomaly-detection/fit")
def fit_anomaly(request: AnomalyFitRequest):
    try:
        baseline = fit_anomaly_baseline(request.values, method=request.method, threshold=request.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return baseline.__dict__


@router.post("/anomaly-detection/score")
def score_anomaly(request: AnomalyScoreRequest):
    try:
        baseline = AnomalyBaseline(method=request.method, center=request.center, scale=request.scale, threshold=request.threshold)
        result = score_anomalies(request.values, baseline)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"baseline": result.baseline.__dict__, "scores": result.scores, "anomalies": result.anomalies, "anomaly_indices": result.anomaly_indices}


@router.post("/anomaly-detection/detect")
def detect_anomaly(request: AnomalyDetectRequest):
    try:
        result = detect_anomalies(request.values, method=request.method, threshold=request.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"baseline": result.baseline.__dict__, "scores": result.scores, "anomalies": result.anomalies, "anomaly_indices": result.anomaly_indices}


class TimeSeriesForecastRequest(BaseModel):
    values: list[float] = Field(min_length=3, max_length=100000)
    method: str = "linear_trend"
    horizon: int = Field(default=1, ge=1, le=10000)
    alpha: float = Field(default=0.3, gt=0, le=1)


@router.post("/time-series/forecast")
def forecast_series(request: TimeSeriesForecastRequest):
    try:
        result = forecast_time_series(request.values, method=request.method, horizon=request.horizon, alpha=request.alpha)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.__dict__


class KMeansFitRequest(BaseModel):
    points: list[list[float]] = Field(min_length=2, max_length=100000)
    k: int = Field(ge=1)
    max_iterations: int = Field(default=100, ge=1, le=10000)
    tolerance: float = Field(default=1e-6, ge=0)


class KMeansPredictRequest(BaseModel):
    points: list[list[float]] = Field(min_length=1, max_length=100000)
    centroids: list[list[float]] = Field(min_length=1, max_length=10000)


@router.post("/clustering/kmeans/fit")
def fit_kmeans_route(request: KMeansFitRequest):
    try:
        result = fit_kmeans(request.points, k=request.k, max_iterations=request.max_iterations, tolerance=request.tolerance)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.__dict__


@router.post("/clustering/kmeans/predict")
def predict_kmeans_route(request: KMeansPredictRequest):
    try:
        labels = predict_clusters(request.points, centroids=request.centroids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"labels": labels}
