import random

import pytest
from gauntlet_core.eval.cluster import EMBED_DIM, cluster_vectors, embed_texts, group_failures

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")


def planted(seed=0, per=8, dim=32, noise=0.03, outliers=2):
    """Three tight groups around orthogonal centres, plus scattered outliers."""
    rng = random.Random(seed)
    rows, truth = [], []
    for g in range(3):
        centre = [0.0] * dim
        centre[g * 5] = 1.0
        for _ in range(per):
            rows.append([c + rng.gauss(0, noise) for c in centre])
            truth.append(g)
    for k in range(outliers):
        v = [0.0] * dim
        v[20 + k * 3] = 1.0
        rows.append([x + rng.gauss(0, noise) for x in v])
        truth.append(-1)
    return np.array(rows), truth


def test_three_planted_groups_are_recovered_and_outliers_are_noise():
    x, truth = planted()
    labels = cluster_vectors(x)
    assert len(labels) == len(truth)
    groups = {g: {labels[i] for i, t in enumerate(truth) if t == g} for g in range(3)}
    for g, got in groups.items():
        assert len(got) == 1 and -1 not in got, (g, got)  # one label, not noise
    assert len({next(iter(s)) for s in groups.values()}) == 3  # three distinct labels
    outliers = [labels[i] for i, t in enumerate(truth) if t == -1]
    assert -1 in outliers  # scattered points are noise, not a cluster of their own
    assert len({v for v in outliers if v != -1}) <= 1


def test_deterministic_for_fixed_vectors():
    x, _ = planted(seed=3)
    assert cluster_vectors(x) == cluster_vectors(x.copy())


def test_scale_of_the_rows_does_not_matter():
    x, _ = planted(seed=1)
    scaled = x * np.arange(1, len(x) + 1)[:, None]
    assert cluster_vectors(scaled) == cluster_vectors(x)


def test_empty_input():
    assert cluster_vectors(np.zeros((0, 4))) == []


def test_fewer_than_six_failures_group_by_failed_check_ids():
    x = np.zeros((5, 4))
    ids = [("b", "a"), ("a", "b"), ("c",), ("a",), ("c",)]
    assert group_failures(x, ids) == [0, 0, 1, 2, 1]


def test_six_or_more_use_the_vectors():
    x, _ = planted(per=2, outliers=0)
    labels = group_failures(x, [("a",)] * 6, min_cluster_size=2)
    assert len(labels) == 6 and len(set(labels) - {-1}) >= 1


async def test_embedding_is_offline_normalised_and_fixed_width():
    vs = await embed_texts(["refund the order | tools: refund", "reset the password"])
    assert len(vs) == 2 and all(len(v) == EMBED_DIM for v in vs)
    assert all(abs(sum(x * x for x in v) - 1.0) < 1e-9 for v in vs)
    again = await embed_texts(["refund the order | tools: refund"])
    assert again[0] == vs[0]  # deterministic
