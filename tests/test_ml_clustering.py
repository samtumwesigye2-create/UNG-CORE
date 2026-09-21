import pytest

from app.services.ml.clustering import fit_kmeans, predict_clusters


def test_kmeans_finds_two_clear_groups():
    points = [[0, 0], [0.2, 0.1], [0.1, 0.3], [10, 10], [10.2, 9.9], [9.8, 10.1]]
    result = fit_kmeans(points, k=2)

    assert result.converged is True
    assert len(result.centroids) == 2
    assert len(set(result.labels[:3])) == 1
    assert len(set(result.labels[3:])) == 1
    assert result.labels[0] != result.labels[3]
    assert result.inertia < 1.0


def test_predict_clusters_uses_nearest_centroid():
    labels = predict_clusters(
        [[0.1, 0.2], [9.9, 10.1]],
        centroids=[[0, 0], [10, 10]],
    )
    assert labels == [0, 1]


def test_kmeans_supports_one_dimensional_data():
    result = fit_kmeans([[1], [1.1], [9], [9.1]], k=2)
    assert len(set(result.labels)) == 2


def test_rejects_inconsistent_dimensions():
    with pytest.raises(ValueError, match="same number of features"):
        fit_kmeans([[1, 2], [3]], k=2)


def test_rejects_invalid_k():
    with pytest.raises(ValueError, match="k must be"):
        fit_kmeans([[1], [2]], k=3)
