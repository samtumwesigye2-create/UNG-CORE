from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.ml.linear_regression import predict_linear, train_linear_regression
from app.services.ml.logistic_regression import predict_logistic, train_logistic_regression
from app.services.ml.anomaly_detection import AnomalyBaseline, detect_anomalies, fit_anomaly_baseline, score_anomalies

router = APIRouter(prefix="/v1/ml", tags=["machine-learning"])


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
async def train_linear(request: LinearRegressionTrainRequest):
    try:
        result = train_linear_regression(
            request.x,
            request.y,
            learning_rate=request.learning_rate,
            epochs=request.epochs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LinearRegressionTrainResponse(**result.__dict__)


@router.post("/linear-regression/predict")
async def predict(request: LinearRegressionPredictRequest):
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
async def train_logistic(request: LogisticRegressionTrainRequest):
    try:
        result = train_logistic_regression(
            request.x,
            request.y,
            learning_rate=request.learning_rate,
            epochs=request.epochs,
            threshold=request.threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.__dict__


@router.post("/logistic-regression/predict")
async def predict_logistic_route(request: LogisticRegressionPredictRequest):
    try:
        probabilities, predictions = predict_logistic(
            request.x,
            weight=request.weight,
            bias=request.bias,
            threshold=request.threshold,
        )
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
async def fit_anomaly(request: AnomalyFitRequest):
    try:
        baseline = fit_anomaly_baseline(
            request.values, method=request.method, threshold=request.threshold
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return baseline.__dict__


@router.post("/anomaly-detection/score")
async def score_anomaly(request: AnomalyScoreRequest):
    try:
        baseline = AnomalyBaseline(
            method=request.method,
            center=request.center,
            scale=request.scale,
            threshold=request.threshold,
        )
        result = score_anomalies(request.values, baseline)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "baseline": result.baseline.__dict__,
        "scores": result.scores,
        "anomalies": result.anomalies,
        "anomaly_indices": result.anomaly_indices,
    }


@router.post("/anomaly-detection/detect")
async def detect_anomaly(request: AnomalyDetectRequest):
    try:
        result = detect_anomalies(
            request.values, method=request.method, threshold=request.threshold
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "baseline": result.baseline.__dict__,
        "scores": result.scores,
        "anomalies": result.anomalies,
        "anomaly_indices": result.anomaly_indices,
    }
