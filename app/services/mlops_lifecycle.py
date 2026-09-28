from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ModelStage(str, Enum):
    REGISTERED = "registered"
    SHADOW = "shadow"
    CANARY = "canary"
    PRODUCTION = "production"
    ROLLED_BACK = "rolled_back"
    RETIRED = "retired"


@dataclass(frozen=True)
class ModelRelease:
    model_id: str
    version: str
    dataset_version: str
    experiment_id: str
    stage: ModelStage = ModelStage.REGISTERED
    calibration_score: float | None = None
    drift_score: float | None = None


class MLOpsLifecycle:
    """Small governance layer around model lineage, staged promotion and rollback."""

    def __init__(self) -> None:
        self._models: dict[tuple[str, str], ModelRelease] = {}
        self._production: dict[str, tuple[str, str]] = {}

    def register(self, release: ModelRelease) -> ModelRelease:
        key=(release.model_id, release.version)
        if key in self._models:
            raise ValueError("model version already registered")
        self._models[key]=release
        return release

    def set_quality(self, model_id: str, version: str, *, calibration_score: float | None=None, drift_score: float | None=None) -> ModelRelease:
        from dataclasses import replace
        key=(model_id, version)
        current=self._models[key]
        updated=replace(current,
            calibration_score=current.calibration_score if calibration_score is None else float(calibration_score),
            drift_score=current.drift_score if drift_score is None else float(drift_score))
        self._models[key]=updated
        return updated

    def promote(self, model_id: str, version: str, target: ModelStage) -> ModelRelease:
        from dataclasses import replace
        key=(model_id, version)
        current=self._models[key]
        allowed={
            ModelStage.REGISTERED:{ModelStage.SHADOW, ModelStage.RETIRED},
            ModelStage.SHADOW:{ModelStage.CANARY, ModelStage.RETIRED},
            ModelStage.CANARY:{ModelStage.PRODUCTION, ModelStage.ROLLED_BACK},
            ModelStage.PRODUCTION:{ModelStage.ROLLED_BACK, ModelStage.RETIRED},
            ModelStage.ROLLED_BACK:{ModelStage.SHADOW, ModelStage.RETIRED},
            ModelStage.RETIRED:set(),
        }
        if target not in allowed[current.stage]:
            raise ValueError(f"invalid stage transition {current.stage} -> {target}")
        updated=replace(current, stage=target)
        self._models[key]=updated
        if target is ModelStage.PRODUCTION:
            self._production[model_id]=key
        elif self._production.get(model_id)==key and target in {ModelStage.ROLLED_BACK, ModelStage.RETIRED}:
            self._production.pop(model_id, None)
        return updated

    def production(self, model_id: str) -> ModelRelease | None:
        key=self._production.get(model_id)
        return None if key is None else self._models[key]
