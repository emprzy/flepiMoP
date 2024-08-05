from datetime import date
from functools import partial
import pathlib
from typing import Any, Callable

import confuse
import numpy as np
import pandas as pd
import pytest
from tempfile import NamedTemporaryFile

from gempyor.parameters import Parameters
from gempyor.testing import create_confuse_subview_from_dict, partials_are_similar
from gempyor.utils import random_distribution_sampler


class MockData:
    simple_timeseries_param_df = pd.DataFrame(
        data={
            "date": pd.date_range(date(2024, 1, 1), date(2024, 1, 5)),
            "1": [1.2, 2.3, 3.4, 4.5, 5.6],
            "2": [2.3, 3.4, 4.5, 5.6, 6.7],
        }
    )

    simple_inputs = {
        "parameter_config": create_confuse_subview_from_dict(
            "parameters", {"sigma": {"value": 0.1}}
        ),
        "ti": date(2024, 1, 1),
        "tf": date(2024, 1, 10),
        "subpop_names": ["1", "2", "3"],
    }

    small_inputs = {
        "parameter_config": create_confuse_subview_from_dict(
            "parameters",
            {"sigma": {"value": 0.1}, "gamma": {"value": 0.2}, "eta": {"value": 0.3}},
        ),
        "ti": date(2024, 1, 1),
        "tf": date(2024, 1, 31),
        "subpop_names": ["1", "2"],
    }


def valid_parameters_factory(
    tmp_path: pathlib.Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, Any]]]:
    """
    Factory for creating small and valid set of parameters.

    Creates the configuration for three parameters:
    - 'sigma': A time series,
    - 'gamma': A fixed value of 0.1234 with a sum stacked modifier,
    - 'Ro': A uniform distribution between 1 and 2.

    Args:
        tmp_path: A temporary file path, typically provided by pytest's `tmp_path`
            fixture.

    Returns:
        A tuple of a dictionary of pandas DataFrames where the keys are the parameter
        names and the values are time series values and a dictionary of configuration
        values that can be converted to a confuse subview.
    """
    tmp_file = tmp_path / "valid_parameters_factory_df.csv"
    df = MockData.simple_timeseries_param_df.copy()
    df.to_csv(tmp_file, index=False)
    params = {
        "sigma": {"timeseries": str(tmp_file.absolute())},
        "gamma": {"value": 0.1234, "stacked_modifier_method": "sum"},
        "Ro": {"value": {"distribution": "uniform", "low": 1.0, "high": 2.0}},
    }
    return [{"sigma": df}, params]


class TestParameters:
    def test_nonunique_parameter_names_value_error(self) -> None:
        duplicated_parameters = create_confuse_subview_from_dict(
            "parameters",
            {"sigma": {"value": 0.1}, "gamma": {"value": 0.2}, "GAMMA": {"value": 0.3}},
        )
        with pytest.raises(
            ValueError,
            match=(
                r"Parameters of the SEIR model have the same name "
                r"\(remember that case is not sufficient\!\)"
            ),
        ):
            Parameters(
                duplicated_parameters,
                ti=date(2024, 1, 1),
                tf=date(2024, 12, 31),
                subpop_names=["1", "2"],
            )

    def test_timeseries_parameter_has_insufficient_columns_value_error(self) -> None:
        param_df = pd.DataFrame(
            data={
                "date": pd.date_range(date(2024, 1, 1), date(2024, 1, 5)),
                "1": [1.2, 2.3, 3.4, 4.5, 5.6],
                "2": [2.3, 3.4, 4.5, 5.6, 6.7],
            }
        )
        with NamedTemporaryFile(suffix=".csv") as temp_file:
            param_df.to_csv(temp_file.name, index=False)
            invalid_timeseries_parameters = create_confuse_subview_from_dict(
                "parameters", {"sigma": {"timeseries": temp_file.name}}
            )
            with pytest.raises(
                ValueError,
                match=(
                    rf"ERROR loading file {temp_file.name} for parameter sigma\: "
                    rf"the number of non 'date'\s+columns are 2, expected 3 "
                    rf"\(the number of subpops\) or one\."
                ),
            ):
                Parameters(
                    invalid_timeseries_parameters,
                    ti=date(2024, 1, 1),
                    tf=date(2024, 1, 5),
                    subpop_names=["1", "2", "3"],
                )

    @pytest.mark.parametrize(
        "start_date,end_date,timeseries_df",
        [(date(2024, 1, 1), date(2024, 1, 6), MockData.simple_timeseries_param_df)],
    )
    def test_timeseries_parameter_has_insufficient_dates_value_error(
        self, start_date: date, end_date: date, timeseries_df: pd.DataFrame
    ) -> None:
        # First way to get at this error, purely a length difference
        with NamedTemporaryFile(suffix=".csv") as temp_file:
            timeseries_df.to_csv(temp_file.name, index=False)
            invalid_timeseries_parameters = create_confuse_subview_from_dict(
                "parameters", {"sigma": {"timeseries": temp_file.name}}
            )
            timeseries_start_date = timeseries_df["date"].dt.date.min()
            timeseries_end_date = timeseries_df["date"].dt.date.max()
            subpop_names = [c for c in timeseries_df.columns.to_list() if c != "date"]
            with pytest.raises(
                ValueError,
                match=(
                    rf"ERROR loading file {temp_file.name} for parameter sigma\:\s+"
                    rf"the \'date\' entries of the provided file do not include all the"
                    rf" days specified to be modeled by\s+the config\. the provided "
                    rf"file includes 5 days between {timeseries_start_date}"
                    rf"( 00\:00\:00)? to {timeseries_end_date}( 00\:00\:00)?,\s+while "
                    rf"there are 6 days in the config time span of {start_date}->"
                    rf"{end_date}\. The file must contain entries for the\s+the exact "
                    rf"start and end dates from the config\. "
                ),
            ):
                Parameters(
                    invalid_timeseries_parameters,
                    ti=start_date,
                    tf=end_date,
                    subpop_names=subpop_names,
                )

        # TODO: I'm not sure how to get to the second pathway to this error message.
        # 1) We subset the read in dataframe to `ti` to `tf` so if the dataframe goes
        # from 2024-01-01 through 2024-01-05 and the given date range is 2024-01-02
        # through 2024-01-06 the dataframe's date range will be subsetted to 2024-01-02
        # through 2024-01-05 which is a repeat of the above.
        # 2) Because of the subsetting you can't provide anything except a monotonic
        # increasing sequence of dates, pandas only allows subsetting on ordered date
        # indexes so you'll get a different error.
        # 3) If you provide a monotonic increasing sequence of dates but 'reverse' `ti`
        # and `tf` you get no errors (which I think is also bad) because the slice
        # operation returns an empty dataframe with the right columns & index and the
        # `pd.date_range` function only creates monotonic increasing sequences and
        # 0 == 0.

    @pytest.mark.parametrize("factory", [(valid_parameters_factory)])
    def test_parameters_instance_attributes(
        self,
        tmp_path: pathlib.Path,
        factory: Callable[
            [pathlib.Path], tuple[dict[str, pd.DataFrame], dict[str, dict[str, Any]]]
        ],
    ) -> None:
        # Setup
        timeseries_dfs, param_config = factory(tmp_path)
        if timeseries_dfs:
            start_date = None
            end_date = None
            subpop_names = []
            for _, df in timeseries_dfs.items():
                df_start_date = df["date"].dt.date.min()
                if start_date is None or df_start_date < start_date:
                    start_date = df_start_date
                df_end_date = df["date"].dt.date.max()
                if end_date is None or df_end_date > end_date:
                    end_date = df_end_date
                if df.shape[1] > 2:
                    subpop_names += [c for c in df.columns.to_list() if c != "date"]
            if not subpop_names:
                subpop_names = ["1", "2"]  # filler value if all time series are 1 value
        else:
            start_date = date(2024, 1, 1)
            end_date = date(2024, 1, 5)
            subpop_names = ["1", "2"]

        valid_parameters = create_confuse_subview_from_dict("parameters", param_config)
        params = Parameters(
            valid_parameters,
            ti=start_date,
            tf=end_date,
            subpop_names=subpop_names,
        )

        # The `npar` attribute
        assert params.npar == len(param_config)

        # The `pconfig` attribute
        assert params.pconfig == valid_parameters

        # The `pdata` attribute
        assert set(params.pdata.keys()) == set(param_config.keys())
        for param_name, param_conf in param_config.items():
            assert params.pdata[param_name]["idx"] == params.pnames2pindex[param_name]
            assert params.pdata[param_name][
                "stacked_modifier_method"
            ] == param_conf.get("stacked_modifier_method", "product")
            if "timeseries" in param_conf:
                assert params.pdata[param_name]["ts"].equals(
                    timeseries_dfs[param_name].set_index("date")
                )
            elif isinstance(params.pdata[param_name]["dist"], partial):
                if isinstance(param_conf.get("value"), float):
                    expected = random_distribution_sampler(
                        "fixed", value=param_conf.get("value")
                    )
                else:
                    expected = random_distribution_sampler(
                        param_conf.get("value").get("distribution"),
                        **{
                            k: v
                            for k, v in param_conf.get("value").items()
                            if k != "distribution"
                        },
                    )
                assert partials_are_similar(params.pdata[param_name]["dist"], expected)
            else:
                expected = random_distribution_sampler(
                    param_conf.get("value").get("distribution"),
                    **{
                        k: v
                        for k, v in param_conf.get("value").items()
                        if k != "distribution"
                    },
                )
                assert (
                    params.pdata[param_name]["dist"].__self__.kwds
                    == expected.__self__.kwds
                )
                assert (
                    params.pdata[param_name]["dist"].__self__.support()
                    == expected.__self__.support()
                )

        # The `pnames` attribute
        assert params.pnames == list(param_config.keys())

        # The `pnames2pindex` attribute
        assert params.pnames2pindex == {
            key: idx for idx, key in enumerate(param_config.keys())
        }

        # # The `stacked_modifier_method` attribute
        expected_stacked_modifier_method = {
            "sum": [],
            "product": [],
            "reduction_product": [],
        }
        for param_name, param_conf in param_config.items():
            modifier_type = param_conf.get("stacked_modifier_method", "product")
            expected_stacked_modifier_method[modifier_type].append(param_name.lower())
        assert params.stacked_modifier_method == expected_stacked_modifier_method

    @pytest.mark.parametrize(
        "parameters_inputs,alpha_val", [(MockData.simple_inputs, None)]
    )
    def test_picklable_lamda_alpha(
        self, parameters_inputs: dict[str, Any], alpha_val: Any
    ) -> None:
        # Setup
        params = Parameters(**parameters_inputs)

        # Attribute error if `alpha_val` is not set
        with pytest.raises(AttributeError):
            params.picklable_lamda_alpha()

        # We get the expected value when `alpha_val` is set
        params.alpha_val = alpha_val
        assert params.picklable_lamda_alpha() == alpha_val

    @pytest.mark.parametrize(
        "parameters_inputs,sigma_val", [(MockData.simple_inputs, None)]
    )
    def test_picklable_lamda_sigma(
        self, parameters_inputs: dict[str, Any], sigma_val: Any
    ) -> None:
        # Setup
        params = Parameters(**parameters_inputs)

        # Attribute error if `sigma_val` is not set
        with pytest.raises(AttributeError):
            params.picklable_lamda_sigma()

        # We get the expected value when `sigma_val` is set
        params.sigma_val = sigma_val
        assert params.picklable_lamda_sigma() == sigma_val

    @pytest.mark.parametrize(
        "parameters_inputs", [(MockData.simple_inputs), (MockData.small_inputs)]
    )
    def test_get_pnames2pindex(self, parameters_inputs: dict[str, Any]) -> None:
        params = Parameters(**parameters_inputs)
        assert params.get_pnames2pindex() == params.pnames2pindex
        assert params.pnames2pindex == {
            key: idx
            for idx, key in enumerate(parameters_inputs["parameter_config"].keys())
        }

    def test_parameters_quick_draw(self) -> None:
        # First with a time series param, fixed size draws
        param_df = pd.DataFrame(
            data={
                "date": pd.date_range(date(2024, 1, 1), date(2024, 1, 5)),
                "1": [1.2, 2.3, 3.4, 4.5, 5.6],
                "2": [2.3, 3.4, 4.5, 5.6, 6.7],
            }
        )
        with NamedTemporaryFile(suffix=".csv") as temp_file:
            param_df.to_csv(temp_file.name, index=False)
            valid_parameters = create_confuse_subview_from_dict(
                "parameters",
                {
                    "sigma": {"timeseries": temp_file.name},
                    "gamma": {"value": 0.1234, "stacked_modifier_method": "sum"},
                    "Ro": {
                        "value": {"distribution": "uniform", "low": 1.0, "high": 2.0}
                    },
                },
            )
            params = Parameters(
                valid_parameters,
                ti=date(2024, 1, 1),
                tf=date(2024, 1, 5),
                subpop_names=["1", "2"],
            )

            # Test the exception
            with pytest.raises(
                ValueError,
                match=(
                    r"could not broadcast input array from shape "
                    r"\(5\,2\) into shape \(4\,2\)"
                ),
            ):
                params.parameters_quick_draw(4, 2)

            # Test our result
            p_draw = params.parameters_quick_draw(5, 2)
            assert isinstance(p_draw, np.ndarray)
            assert p_draw.dtype == np.float64
            assert p_draw.shape == (3, 5, 2)
            assert np.allclose(
                p_draw[0, :, :],
                np.array([[1.2, 2.3], [2.3, 3.4], [3.4, 4.5], [4.5, 5.6], [5.6, 6.7]]),
            )
            assert np.allclose(p_draw[1, :, :], 0.1234 * np.ones((5, 2)))
            assert np.greater_equal(p_draw[2, :, :], 1.0).all()
            assert np.less(p_draw[2, :, :], 2.0).all()
            assert np.allclose(p_draw[2, :, :], p_draw[2, 0, 0])

        # Second without a time series param, arbitrary sized draws
        valid_parameters = create_confuse_subview_from_dict(
            "parameters",
            {
                "eta": {"value": 2.2},
                "nu": {
                    "value": {
                        "distribution": "truncnorm",
                        "mean": 0.0,
                        "sd": 2.0,
                        "a": -2.0,
                        "b": 2.0,
                    }
                },
            },
        )
        params = Parameters(
            valid_parameters,
            ti=date(2024, 1, 1),
            tf=date(2024, 1, 5),
            subpop_names=["1", "2"],
        )

        p_draw = params.parameters_quick_draw(5, 2)
        assert isinstance(p_draw, np.ndarray)
        assert p_draw.dtype == np.float64
        assert p_draw.shape == (2, 5, 2)
        assert np.allclose(p_draw[0, :, :], 2.2)
        assert np.greater_equal(p_draw[1, :, :], -2.0).all()
        assert np.less_equal(p_draw[1, :, :], 2.0).all()
        assert np.allclose(p_draw[1, :, :], p_draw[1, 0, 0])

        p_draw = params.parameters_quick_draw(4, 3)
        assert isinstance(p_draw, np.ndarray)
        assert p_draw.dtype == np.float64
        assert p_draw.shape == (2, 4, 3)
        assert np.allclose(p_draw[0, :, :], 2.2)
        assert np.greater_equal(p_draw[1, :, :], -2.0).all()
        assert np.less_equal(p_draw[1, :, :], 2.0).all()
        assert np.allclose(p_draw[1, :, :], p_draw[1, 0, 0])

    def test_parameters_load(self) -> None:
        # Setup
        param_overrides_df = pd.DataFrame(
            {"parameter": ["nu", "gamma", "nu"], "value": [0.1, 0.2, 0.3]}
        )
        param_empty_df = pd.DataFrame({"parameter": [], "value": []})

        # With time series
        param_df = pd.DataFrame(
            data={
                "date": pd.date_range(date(2024, 1, 1), date(2024, 1, 5)),
                "1": [1.2, 2.3, 3.4, 4.5, 5.6],
                "2": [2.3, 3.4, 4.5, 5.6, 6.7],
            }
        )
        with NamedTemporaryFile(suffix=".csv") as temp_file:
            param_df.to_csv(temp_file.name, index=False)
            valid_parameters = create_confuse_subview_from_dict(
                "parameters",
                {
                    "sigma": {"timeseries": temp_file.name},
                    "gamma": {"value": 0.1234, "stacked_modifier_method": "sum"},
                    "Ro": {
                        "value": {"distribution": "uniform", "low": 1.0, "high": 2.0}
                    },
                },
            )
            params = Parameters(
                valid_parameters,
                ti=date(2024, 1, 1),
                tf=date(2024, 1, 5),
                subpop_names=["1", "2"],
            )

            # Test the exception
            with pytest.raises(
                ValueError,
                match=(
                    r"could not broadcast input array from shape "
                    r"\(5\,2\) into shape \(4\,2\)"
                ),
            ):
                params.parameters_load(param_empty_df, 4, 2)

            # Empty overrides
            p_draw = params.parameters_load(param_empty_df, 5, 2)
            assert isinstance(p_draw, np.ndarray)
            assert p_draw.dtype == np.float64
            assert p_draw.shape == (3, 5, 2)
            assert np.allclose(
                p_draw[0, :, :],
                np.array([[1.2, 2.3], [2.3, 3.4], [3.4, 4.5], [4.5, 5.6], [5.6, 6.7]]),
            )
            assert np.allclose(p_draw[1, :, :], 0.1234 * np.ones((5, 2)))
            assert np.greater_equal(p_draw[2, :, :], 1.0).all()
            assert np.less(p_draw[2, :, :], 2.0).all()
            assert np.allclose(p_draw[2, :, :], p_draw[2, 0, 0])

            # But if we override time series no exception
            p_draw = params.parameters_load(
                pd.DataFrame({"parameter": ["sigma"], "value": [12.34]}), 4, 2
            )
            assert isinstance(p_draw, np.ndarray)
            assert p_draw.dtype == np.float64
            assert p_draw.shape == (3, 4, 2)
            assert np.allclose(p_draw[0, :, :], 12.34)
            assert np.allclose(p_draw[1, :, :], 0.1234 * np.ones((4, 2)))
            assert np.greater_equal(p_draw[2, :, :], 1.0).all()
            assert np.less(p_draw[2, :, :], 2.0).all()
            assert np.allclose(p_draw[2, :, :], p_draw[2, 0, 0])

            # If not overriding time series then must conform
            p_draw = params.parameters_load(param_overrides_df, 5, 2)
            assert isinstance(p_draw, np.ndarray)
            assert p_draw.dtype == np.float64
            assert p_draw.shape == (3, 5, 2)
            assert np.allclose(
                p_draw[0, :, :],
                np.array([[1.2, 2.3], [2.3, 3.4], [3.4, 4.5], [4.5, 5.6], [5.6, 6.7]]),
            )
            assert np.allclose(p_draw[1, :, :], 0.2 * np.ones((5, 2)))
            assert np.greater_equal(p_draw[2, :, :], 1.0).all()
            assert np.less(p_draw[2, :, :], 2.0).all()
            assert np.allclose(p_draw[2, :, :], p_draw[2, 0, 0])

        # Without time series
        valid_parameters = create_confuse_subview_from_dict(
            "parameters",
            {
                "eta": {"value": 2.2},
                "nu": {
                    "value": {
                        "distribution": "truncnorm",
                        "mean": 0.0,
                        "sd": 2.0,
                        "a": -2.0,
                        "b": 2.0,
                    }
                },
            },
        )
        params = Parameters(
            valid_parameters,
            ti=date(2024, 1, 1),
            tf=date(2024, 1, 5),
            subpop_names=["1", "2"],
        )

        # Takes an 'empty' DataFrame
        p_draw = params.parameters_load(param_empty_df, 5, 2)
        assert isinstance(p_draw, np.ndarray)
        assert p_draw.dtype == np.float64
        assert p_draw.shape == (2, 5, 2)
        assert np.allclose(p_draw[0, :, :], 2.2)
        assert np.greater_equal(p_draw[1, :, :], -2.0).all()
        assert np.less_equal(p_draw[1, :, :], 2.0).all()

        # Takes a DataFrame with values, only takes the first
        p_draw = params.parameters_load(param_overrides_df, 4, 3)
        assert isinstance(p_draw, np.ndarray)
        assert p_draw.dtype == np.float64
        assert p_draw.shape == (2, 4, 3)
        assert np.allclose(p_draw[0, :, :], 2.2)
        assert np.allclose(p_draw[1, :, :], 0.1)

    def test_getParameterDF(self) -> None:
        param_df = pd.DataFrame(
            data={
                "date": pd.date_range(date(2024, 1, 1), date(2024, 1, 5)),
                "1": [1.2, 2.3, 3.4, 4.5, 5.6],
                "2": [2.3, 3.4, 4.5, 5.6, 6.7],
            }
        )
        with NamedTemporaryFile(suffix=".csv") as temp_file:
            param_df.to_csv(temp_file.name, index=False)
            valid_parameters = create_confuse_subview_from_dict(
                "parameters",
                {
                    "sigma": {"timeseries": temp_file.name},
                    "gamma": {"value": 0.1234, "stacked_modifier_method": "sum"},
                    "Ro": {
                        "value": {"distribution": "uniform", "low": 1.0, "high": 2.0}
                    },
                },
            )
            params = Parameters(
                valid_parameters,
                ti=date(2024, 1, 1),
                tf=date(2024, 1, 5),
                subpop_names=["1", "2"],
            )

            # Create a quick sample
            p_draw = params.parameters_quick_draw(5, 2)
            df = params.getParameterDF(p_draw)
            assert isinstance(df, pd.DataFrame)
            assert df.shape == (2, 2)
            assert df.columns.to_list() == ["value", "parameter"]
            assert df["parameter"].to_list() == ["gamma", "Ro"]
            values = df["value"].to_list()
            assert values[0] == 0.1234
            assert values[1] >= 1.0
            assert values[1] < 2.0
            assert (df.index.to_series() == df["parameter"]).all()

            # Make clear that 'sigma' is not present because it's a time series
            assert "sigma" not in df["parameter"].to_list()

    def test_parameters_reduce(self) -> None:
        # TODO: Come back and unit test this method after getting a better handle on
        # these NPI objects.
        pass
