from datetime import date
from typing import Any, Callable

import confuse
import numpy as np
import pandas as pd
import pytest
import scipy
import xarray as xr

from gempyor.statistics import Statistic
from gempyor.testing import create_confuse_configview_from_dict


class MockStatisticInput:
    def __init__(
        self,
        name: str,
        config: dict[str, Any],
        model_data: xr.DataArray | None = None,
        gt_data: xr.DataArray | None = None,
    ) -> None:
        self.name = name
        self.config = config
        self.model_data = model_data
        self.gt_data = gt_data
        self._confuse_subview = None

    def create_confuse_subview(self) -> confuse.Subview:
        if self._confuse_subview is None:
            self._confuse_subview = create_confuse_configview_from_dict(
                self.config, name=self.name
            )
        return self._confuse_subview

    def create_statistic_instance(self) -> Statistic:
        return Statistic(self.name, self.create_confuse_subview())


def invalid_regularization_factory() -> MockStatisticInput:
    return MockStatisticInput(
        "total_hospitalizations",
        {
            "name": "sum_hospitalizations",
            "aggregator": "sum",
            "period": "1 months",
            "sim_var": "incidH",
            "data_var": "incidH",
            "remove_na": True,
            "add_one": True,
            "likelihood": {"dist": "rmse"},
            "regularize": [{"name": "forecast"}, {"name": "invalid"}],
        },
    )


def simple_valid_factory() -> MockStatisticInput:
    model_data = xr.DataArray(
        data=np.random.randn(10, 3),
        dims=("date", "subpop"),
        coords={
            "date": pd.date_range(date(2024, 1, 1), date(2024, 1, 10)),
            "subpop": ["01", "02", "03"],
        },
    )
    gt_data = xr.DataArray(
        data=np.random.randn(10, 3),
        dims=("date", "subpop"),
        coords={
            "date": pd.date_range(date(2024, 1, 1), date(2024, 1, 10)),
            "subpop": ["01", "02", "03"],
        },
    )
    return MockStatisticInput(
        "total_hospitalizations",
        {
            "name": "sum_hospitalizations",
            "aggregator": "sum",
            "period": "1 months",
            "sim_var": "incidH",
            "data_var": "incidH",
            "remove_na": True,
            "add_one": True,
            "likelihood": {"dist": "norm", "params": {"scale": 2.0}},
        },
        model_data=model_data,
        gt_data=gt_data,
    )


def simple_valid_resample_factory() -> MockStatisticInput:
    date_coords = pd.date_range(date(2024, 1, 1), date(2024, 12, 31))
    subpop_coords = ["01", "02", "03", "04"]
    dim = (len(date_coords), len(subpop_coords))
    model_data = xr.DataArray(
        data=np.random.randn(*dim),
        dims=("date", "subpop"),
        coords={
            "date": date_coords,
            "subpop": subpop_coords,
        },
    )
    gt_data = xr.DataArray(
        data=np.random.randn(*dim),
        dims=("date", "subpop"),
        coords={
            "date": date_coords,
            "subpop": subpop_coords,
        },
    )
    return MockStatisticInput(
        "total_hospitalizations",
        {
            "name": "sum_hospitalizations",
            "aggregator": "sum",
            "period": "1 months",
            "sim_var": "incidH",
            "data_var": "incidH",
            "remove_na": True,
            "add_one": True,
            "likelihood": {"dist": "rmse"},
            "resample": {"freq": "MS", "aggregator": "sum"},
        },
        model_data=model_data,
        gt_data=gt_data,
    )


def simple_valid_scale_factory() -> MockStatisticInput:
    date_coords = pd.date_range(date(2024, 1, 1), date(2024, 12, 31))
    subpop_coords = ["01", "02", "03", "04"]
    dim = (len(date_coords), len(subpop_coords))
    model_data = xr.DataArray(
        data=np.random.randn(*dim),
        dims=("date", "subpop"),
        coords={
            "date": date_coords,
            "subpop": subpop_coords,
        },
    )
    gt_data = xr.DataArray(
        data=np.random.randn(*dim),
        dims=("date", "subpop"),
        coords={
            "date": date_coords,
            "subpop": subpop_coords,
        },
    )
    return MockStatisticInput(
        "total_hospitalizations",
        {
            "name": "sum_hospitalizations",
            "aggregator": "sum",
            "period": "1 months",
            "sim_var": "incidH",
            "data_var": "incidH",
            "remove_na": True,
            "add_one": True,
            "likelihood": {"dist": "rmse"},
            "scale": "exp",
        },
        model_data=model_data,
        gt_data=gt_data,
    )


def simple_valid_resample_and_scale_factory() -> MockStatisticInput:
    date_coords = pd.date_range(date(2024, 1, 1), date(2024, 12, 31))
    subpop_coords = ["01", "02", "03", "04"]
    dim = (len(date_coords), len(subpop_coords))
    model_data = xr.DataArray(
        data=np.random.randn(*dim),
        dims=("date", "subpop"),
        coords={
            "date": date_coords,
            "subpop": subpop_coords,
        },
    )
    gt_data = xr.DataArray(
        data=np.random.randn(*dim),
        dims=("date", "subpop"),
        coords={
            "date": date_coords,
            "subpop": subpop_coords,
        },
    )
    return MockStatisticInput(
        "total_hospitalizations",
        {
            "name": "sum_hospitalizations",
            "aggregator": "sum",
            "period": "1 months",
            "sim_var": "incidH",
            "data_var": "incidH",
            "remove_na": True,
            "add_one": True,
            "likelihood": {"dist": "rmse"},
            "resample": {"freq": "W", "aggregator": "max"},
            "scale": "sin",
        },
        model_data=model_data,
        gt_data=gt_data,
    )


all_valid_factories = [
    (simple_valid_factory),
    (simple_valid_resample_factory),
    (simple_valid_resample_factory),
    (simple_valid_resample_and_scale_factory),
]


class TestStatistic:
    @pytest.mark.parametrize("factory", [(invalid_regularization_factory)])
    def test_unsupported_regularizations_value_error(
        self, factory: Callable[[], MockStatisticInput]
    ) -> None:
        mock_inputs = factory()
        unsupported_name = next(
            reg_name
            for reg_name in [
                reg["name"] for reg in mock_inputs.config.get("regularize", [])
            ]
            if reg_name not in ["forecast", "allsubpop"]
        )
        with pytest.raises(
            ValueError, match=rf"^Unsupported regularization\: {unsupported_name}$"
        ):
            mock_inputs.create_statistic_instance()

    @pytest.mark.parametrize("factory", all_valid_factories)
    def test_statistic_instance_attributes(
        self, factory: Callable[[], MockStatisticInput]
    ) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # `data_var` attribute
        assert statistic.data_var == mock_inputs.config["data_var"]

        # `dist` attribute
        assert statistic.dist == mock_inputs.config["likelihood"]["dist"]

        # `name` attribute
        assert statistic.name == mock_inputs.name

        # `params` attribute
        assert statistic.params == mock_inputs.config["likelihood"].get("params", {})

        # `regularizations` attribute
        assert statistic.regularizations == [
            (r["name"], r) for r in mock_inputs.config.get("regularize", [])
        ]

        # `resample` attribute
        resample_config = mock_inputs.config.get("resample", {})
        assert statistic.resample == (resample_config != {})

        if resample_config:
            # `resample_aggregator_name` attribute
            assert statistic.resample_aggregator_name == resample_config.get(
                "aggregator", ""
            )

            # `resample_freq` attribute
            assert statistic.resample_freq == resample_config.get("freq", "")

            # `resample_skipna` attribute
            assert (
                statistic.resample_skipna == resample_config.get("skipna", False)
                if resample_config.get("aggregator") is not None
                else False
            )

        # `scale` attribute
        assert statistic.scale == (mock_inputs.config.get("scale") is not None)

        # `scale_func` attribute
        if (scale_func := mock_inputs.config.get("scale")) is not None:
            assert statistic.scale_func == getattr(np, scale_func)

        # `sim_var` attribute
        assert statistic.sim_var == mock_inputs.config["sim_var"]

        # `zero_to_one` attribute
        assert statistic.zero_to_one == mock_inputs.config.get("zero_to_one", False)

    @pytest.mark.parametrize("factory", all_valid_factories)
    def test_statistic_str_and_repr(
        self, factory: Callable[[], MockStatisticInput]
    ) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # Tests
        statistic_str = (
            f"{mock_inputs.name}: {mock_inputs.config['likelihood']['dist']} between "
            f"{mock_inputs.config['sim_var']} (sim) and "
            f"{mock_inputs.config['data_var']} (data)."
        )
        assert str(statistic) == statistic_str
        assert repr(statistic) == f"A Statistic(): {statistic_str}"

    @pytest.mark.parametrize("factory,last_n,mult", [(simple_valid_factory, 4, 2.0)])
    def test_forecast_regularize(
        self, factory: Callable[[], MockStatisticInput], last_n: int, mult: int | float
    ) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # Tests
        forecast_regularization = statistic._forecast_regularize(
            mock_inputs.model_data, mock_inputs.gt_data, last_n=last_n, mult=mult
        )
        assert isinstance(forecast_regularization, float)

    @pytest.mark.parametrize("factory,mult", [(simple_valid_factory, 2.0)])
    def test_allsubpop_regularize(
        self, factory: Callable[[], MockStatisticInput], mult: int | float
    ) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # Tests
        forecast_regularization = statistic._allsubpop_regularize(
            mock_inputs.model_data, mock_inputs.gt_data, mult=mult
        )
        assert isinstance(forecast_regularization, float)

    @pytest.mark.parametrize("factory", all_valid_factories)
    def test_apply_resample(self, factory: Callable[[], MockStatisticInput]) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # Tests
        resampled_data = statistic.apply_resample(mock_inputs.model_data)
        if resample_config := mock_inputs.config.get("resample", {}):
            # Resample config
            expected_resampled_data = mock_inputs.model_data.resample(
                date=resample_config.get("freq", "")
            )
            aggregation_func = getattr(
                expected_resampled_data, resample_config.get("aggregator", "")
            )
            expected_resampled_data = aggregation_func(
                skipna=(
                    resample_config.get("skipna", False)
                    if resample_config.get("aggregator") is not None
                    else False
                )
            )
            assert resampled_data.identical(expected_resampled_data)
        else:
            # No resample config, `apply_resample` returns our input
            assert resampled_data.identical(mock_inputs.model_data)

    @pytest.mark.parametrize("factory", all_valid_factories)
    def test_apply_scale(self, factory: Callable[[], MockStatisticInput]) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # Tests
        scaled_data = statistic.apply_scale(mock_inputs.model_data)
        if (scale_func := mock_inputs.config.get("scale")) is not None:
            # Scale config
            expected_scaled_data = getattr(np, scale_func)(mock_inputs.model_data)
            assert scaled_data.identical(expected_scaled_data)
        else:
            # No scale config, `apply_scale` is a no-op
            assert scaled_data.identical(mock_inputs.model_data)

    @pytest.mark.parametrize("factory", all_valid_factories)
    def test_apply_transforms(self, factory: Callable[[], MockStatisticInput]) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # Tests
        transformed_data = statistic.apply_transforms(mock_inputs.model_data)
        expected_transformed_data = mock_inputs.model_data.copy()
        if resample_config := mock_inputs.config.get("resample", {}):
            # Resample config
            expected_transformed_data = expected_transformed_data.resample(
                date=resample_config.get("freq", "")
            )
            aggregation_func = getattr(
                expected_transformed_data, resample_config.get("aggregator", "")
            )
            expected_transformed_data = aggregation_func(
                skipna=(
                    resample_config.get("skipna", False)
                    if resample_config.get("aggregator") is not None
                    else False
                )
            )
        if (scale_func := mock_inputs.config.get("scale")) is not None:
            # Scale config
            expected_transformed_data = getattr(np, scale_func)(
                expected_transformed_data
            )
        assert transformed_data.identical(expected_transformed_data)

    @pytest.mark.parametrize("factory", all_valid_factories)
    def test_llik(self, factory: Callable[[], MockStatisticInput]) -> None:
        # Setup
        mock_inputs = factory()
        statistic = mock_inputs.create_statistic_instance()

        # Tests
        log_likelihood = statistic.llik(mock_inputs.model_data, mock_inputs.gt_data)

        assert isinstance(log_likelihood, xr.DataArray)
        assert log_likelihood.dims == mock_inputs.gt_data.dims
        assert log_likelihood.coords.equals(mock_inputs.gt_data.coords)
        dist_name = mock_inputs.config["likelihood"]["dist"]
        if dist_name in {"absolute_error", "rmse"}:
            # MAE produces a single repeated number
            assert np.allclose(
                log_likelihood.values,
                -np.log(
                    np.nansum(np.abs(mock_inputs.model_data - mock_inputs.gt_data))
                ),
            )
        elif dist_name == "pois":
            assert np.allclose(
                log_likelihood.values,
                scipy.stats.poisson.logpmf(
                    mock_inputs.gt_data.values, mock_inputs.model_data.values
                ),
            )
        elif dist_name == {"norm", "norm_cov"}:
            scale = mock_inputs.config["likelihood"]["params"]["scale"]
            if dist_name == "norm_cov":
                scale *= mock_inputs.model_data.where(mock_inputs.model_data > 5, 5)
            assert np.allclose(
                log_likelihood.values,
                scipy.stats.norm.logpdf(
                    mock_inputs.gt_data.values,
                    mock_inputs.model_data.values,
                    scale=scale,
                ),
            )
        elif dist_name == "nbinom":
            assert np.allclose(
                log_likelihood.values,
                scipy.stats.nbinom.logpmf(
                    mock_inputs.gt_data.values,
                    n=mock_inputs.config["likelihood"]["params"]["n"],
                    p=mock_inputs.model_data.values,
                ),
            )
