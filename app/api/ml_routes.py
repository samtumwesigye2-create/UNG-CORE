from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.ml.linear_regression import predict_linear, train_linear_regression

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
