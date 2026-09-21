from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class KMeansResult:
    centroids: list[list[float]]
    labels: list[int]
    inertia: float
    iterations: int
    converged: bool


def _validate_points(points: Sequence[Sequence[float]], k: int, max_iterations: int, tolerance: float) -> list[list[float]]:
    if len(points) < 2:
        raise ValueError("at least two points are required")
    data = [[float(v) for v in point] for point in points]
    dimensions = len(data[0])
    if dimensions < 1:
        raise ValueError("points must contain at least one feature")
    if any(len(point) != dimensions for point in data):
        raise ValueError("all points must have the same number of features")
    if not all(isfinite(v) for point in data for v in point):
        raise ValueError("points must contain only finite numbers")
    if k < 1 or k > len(data):
        raise ValueError("k must be between 1 and the number of points")
    if max_iterations < 1 or max_iterations > 10_000:
        raise ValueError("max_iterations must be between 1 and 10000")
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be a finite number greater than or equal to zero")
    return data


def _distance_squared(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _initialize_centroids(points: list[list[float]], k: int) -> list[list[float]]:
    # Deterministic farthest-point initialization gives reproducible runs.
    centroids = [points[0][:]]
    while len(centroids) < k:
        candidate = max(
            points,
            key=lambda point: min(_distance_squared(point, center) for center in centroids),
        )
        centroids.append(candidate[:])
    return centroids


def _assign(points: list[list[float]], centroids: list[list[float]]) -> list[int]:
    return [
        min(range(len(centroids)), key=lambda index: _distance_squared(point, centroids[index]))
        for point in points
    ]


def fit_kmeans(
    points: Sequence[Sequence[float]],
    *,
    k: int,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
) -> KMeansResult:
    data = _validate_points(points, k, max_iterations, tolerance)
    centroids = _initialize_centroids(data, k)
    converged = False
    iterations = 0

    for iteration in range(1, max_iterations + 1):
        labels = _assign(data, centroids)
        new_centroids: list[list[float]] = []
        for cluster in range(k):
            members = [point for point, label in zip(data, labels) if label == cluster]
            if not members:
                new_centroids.append(centroids[cluster][:])
                continue
            new_centroids.append([
                sum(point[dimension] for point in members) / len(members)
                for dimension in range(len(data[0]))
            ])

        movement = max(
            _distance_squared(old, new) ** 0.5
            for old, new in zip(centroids, new_centroids)
        )
        centroids = new_centroids
        iterations = iteration
        if movement <= tolerance:
            converged = True
            break

    labels = _assign(data, centroids)
    inertia = sum(
        _distance_squared(point, centroids[label])
        for point, label in zip(data, labels)
    )
    return KMeansResult(
        centroids=centroids,
        labels=labels,
        inertia=inertia,
        iterations=iterations,
        converged=converged,
    )


def predict_clusters(
    points: Sequence[Sequence[float]],
    *,
    centroids: Sequence[Sequence[float]],
) -> list[int]:
    if not centroids:
        raise ValueError("at least one centroid is required")
    centers = [[float(v) for v in center] for center in centroids]
    dimensions = len(centers[0])
    if dimensions < 1 or any(len(center) != dimensions for center in centers):
        raise ValueError("all centroids must have the same non-zero number of features")
    if not all(isfinite(v) for center in centers for v in center):
        raise ValueError("centroids must contain only finite numbers")

    data = [[float(v) for v in point] for point in points]
    if not data:
        raise ValueError("at least one point is required")
    if any(len(point) != dimensions for point in data):
        raise ValueError("point dimensions must match centroid dimensions")
    if not all(isfinite(v) for point in data for v in point):
        raise ValueError("points must contain only finite numbers")
    return _assign(data, centers)
