import pathlib
from typing import Any, Callable

import confuse
import pytest
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
            "likelihood": {"dist": "pois"},
            "regularize": [{"name": "forecast"}, {"name": "invalid"}],
        },
    )


def simple_valid_factory() -> MockStatisticInput:
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
            "likelihood": {"dist": "pois"},
        },
    )


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

    @pytest.mark.parametrize("factory", [(simple_valid_factory)])
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
        if scale_func := mock_inputs.config.get("scale") is not None:
            assert statistic.scale_func == scale_func

        # `sim_var` attribute
        assert statistic.sim_var == mock_inputs.config["sim_var"]

        # `zero_to_one` attribute
        assert statistic.zero_to_one == mock_inputs.config.get("zero_to_one", False)
