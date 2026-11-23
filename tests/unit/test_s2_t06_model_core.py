import numpy as np
import pytest
import torch
from sklearn.preprocessing import StandardScaler

from src.models.m5a import ResidualGRU
from src.models.kinematics import cv_displacement, project_forecast, residual_target
from src.models.scalers import TrainOnlyScaler
from src.models.pipeline import forecast


@pytest.mark.parametrize('batch', [1, 5])
def test_gru_shape_gradient_and_seed(batch):
    torch.manual_seed(42)
    model = ResidualGRU()
    torch.manual_seed(42)
    other = ResidualGRU()
    assert sum(p.numel() for p in model.parameters()) == 15390
    assert all(torch.equal(a, b) for a, b in zip(model.parameters(), other.parameters()))
    x = torch.randn(batch, 10, 4, requires_grad=True)
    y = model(x)
    assert y.shape == (batch, 15, 2) and y.dtype == x.dtype and y.device == x.device
    assert torch.isfinite(y).all()
    y.square().mean().backward()
    assert x.grad is not None and torch.isfinite(x.grad).all()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


@pytest.mark.parametrize('shape', [(10, 4), (2, 9, 4), (2, 10, 5), (0, 10, 4)])
def test_gru_invalid_shape(shape):
    with pytest.raises(ValueError):
        ResidualGRU()(torch.zeros(shape))


def test_cv_directions_and_time():
    v = torch.tensor([[0., 0.], [0., 60.], [60., 0.], [3., 4.]], dtype=torch.float64)
    out = cv_displacement(v, forecast_minutes=list(range(1, 16)))
    torch.testing.assert_close(out[:, 0], v / 60)
    torch.testing.assert_close(out[:, -1], v / 4)
    assert out.shape == (4, 15, 2)
    with pytest.raises(ValueError):
        cv_displacement(v, forecast_minutes=list(range(15)))
    with pytest.raises(ValueError):
        cv_displacement(torch.tensor([[float('nan'), 1.]]))


def test_residual_reconstruction():
    cv = cv_displacement(torch.tensor([[6., 12.], [-2., 0.]]))
    truth = torch.arange(60, dtype=torch.float32).reshape(2, 15, 2) / 10
    r = residual_target(truth, cv)
    torch.testing.assert_close(r + cv, truth)
    with pytest.raises(ValueError):
        residual_target(truth[:1], cv)


@pytest.mark.parametrize('kind,shape', [('input', (4, 10, 4)), ('residual', (4, 15, 2))])
def test_scaler_train_protocol_and_roundtrip(kind, shape, tmp_path):
    data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    obj = TrainOnlyScaler(kind)
    with pytest.raises(RuntimeError):
        obj.transform(data)
    with pytest.raises(ValueError):
        obj.fit(data, split='validation')
    obj.fit(data, split='train')
    expected = StandardScaler().fit(data.reshape(-1, shape[-1]))
    np.testing.assert_allclose(obj.mean, expected.mean_)
    np.testing.assert_allclose(obj.scale, expected.scale_ + 1e-6)
    mean, scale = obj.mean.copy(), obj.scale.copy()
    transformed = obj.transform(data + 1000)
    assert transformed.shape == data.shape and transformed.dtype == np.float32
    np.testing.assert_allclose(obj.inverse_transform(transformed), data + 1000, rtol=1e-6)
    np.testing.assert_array_equal(obj.mean, mean)
    np.testing.assert_array_equal(obj.scale, scale)
    path = tmp_path / 'scaler.json'
    obj.save(path)
    restored = TrainOnlyScaler.load(path)
    np.testing.assert_array_equal(restored.transform(data), obj.transform(data))
    data.flat[0] = np.nan
    with pytest.raises(ValueError):
        obj.transform(data)
    with pytest.raises(ValueError):
        obj.fit(data, split='train')


def test_projection_straight_stationary_and_near_zero():
    anchor = torch.zeros((3, 2), dtype=torch.float64)
    velocity = torch.tensor([[0., 12.], [0., 0.], [1e-15, 0.]], dtype=torch.float64)
    raw = anchor[:, None] + cv_displacement(velocity)
    actual = project_forecast(raw, anchor, velocity)
    torch.testing.assert_close(actual, raw, rtol=1e-10, atol=1e-12)
    torch.testing.assert_close(project_forecast(actual, anchor, velocity), actual, rtol=1e-10, atol=1e-12)
    assert actual.dtype == raw.dtype and actual.shape == (3, 15, 2)


def test_projection_speed_vector_and_turn_boundaries():
    dtype = torch.float64
    anchor = torch.zeros((3, 2), dtype=dtype)
    v = torch.tensor([[49.999, 0.], [0., 0.], [0., 3.]], dtype=dtype)
    raw = torch.tensor([[[100., 0.]] * 15, [[100., 0.]] * 15, [[100., 0.]] * 15], dtype=dtype)
    out = project_forecast(raw, anchor, v)
    first = out[:, 0] * 60
    assert torch.linalg.vector_norm(first[0]) <= 49.999 + 1e-10
    assert torch.linalg.vector_norm(first[1]) == pytest.approx(2.999)
    angle = abs(torch.atan2(first[2, 0], first[2, 1]).item())
    assert angle <= np.deg2rad(29.9) + 1e-10
    assert torch.isfinite(out).all()
    with pytest.raises(ValueError):
        project_forecast(raw.float(), anchor, v)
    raw[0, 0, 0] = float('inf')
    with pytest.raises(ValueError):
        project_forecast(raw, anchor, v)


def test_pipeline_untrained_shape_and_no_future_input():
    torch.manual_seed(9)
    x = torch.zeros(2, 10, 4)
    x[:, :, 2:] = torch.tensor([3., 4.])
    a = torch.tensor([[1., 2.], [3., 4.]], dtype=torch.float64)
    xs = TrainOnlyScaler('input').fit(x.numpy(), split='train')
    rs = TrainOnlyScaler('residual').fit(np.zeros((2, 15, 2), dtype=np.float32), split='train')
    model = ResidualGRU()
    out = forecast(model, xs, rs, x, a)
    assert out.shape == (2, 15, 2) and out.dtype == a.dtype and torch.isfinite(out).all()
    torch.testing.assert_close(out, forecast(model, xs, rs, x.clone(), a.clone()))
    with pytest.raises(TypeError):
        forecast(model, xs, rs, x, a, future_target=torch.zeros(2, 15, 2))
    bad = x.clone(); bad[:, -1, 0] = 1.
    with pytest.raises(ValueError):
        forecast(model, xs, rs, bad, a)
