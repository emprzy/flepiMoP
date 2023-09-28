import numpy as np
import os
import pytest
import warnings
import shutil

import pathlib
import pyarrow as pa
import pyarrow.parquet as pq

from gempyor import setup, seir, NPI, file_paths, subpopulation_structure

from gempyor.utils import config

DATA_DIR = os.path.dirname(__file__) + "/data"
os.chdir(os.path.dirname(__file__))


def test_check_values():
    os.chdir(os.path.dirname(__file__))
    config.set_file(f"{DATA_DIR}/config.yml")

    ss = subpopulation_structure.SubpopulationStructure(
        setup_name="test_values",
        geodata_file=f"{DATA_DIR}/geodata.csv",
        mobility_file=f"{DATA_DIR}/mobility.txt",
        subpop_pop_key="population",
        subpop_names_key="subpop",
    )

    s = setup.Setup(
        setup_name="test_values",
        subpop_setup=ss,
        nslots=1,
        npi_scenario="None",
        npi_config_seir=config["interventions"]["settings"]["None"],
        parameters_config=config["seir"]["parameters"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=True,
        write_csv=False,
        dt=0.25,
    )

    with warnings.catch_warnings(record=True) as w:
        seeding = np.zeros((s.n_days, s.nsubpops))

        if np.all(seeding == 0):
            warnings.warn("provided seeding has only value 0", UserWarning)

        seeding[0, 0] = 1

        if np.all(seeding == 0):
            warnings.warn("provided seeding has only value 0", UserWarning)

        if np.all(s.mobility.data < 1):
            warnings.warn("highest mobility value is less than 1", UserWarning)

        s.mobility.data[0] = 0.8
        s.mobility.data[1] = 0.5

        if np.all(s.mobility.data < 1):
            warnings.warn("highest mobility value is less than 1", UserWarning)

        assert len(w) == 2
        assert issubclass(w[0].category, UserWarning)
        assert issubclass(w[1].category, UserWarning)
        assert "seeding" in str(w[0].message)
        assert "mobility" in str(w[1].message)


def test_constant_population_legacy_integration():
    config.set_file(f"{DATA_DIR}/config.yml")

    ss = subpopulation_structure.SubpopulationStructure(
        setup_name="test_seir",
        geodata_file=f"{DATA_DIR}/geodata.csv",
        mobility_file=f"{DATA_DIR}/mobility.txt",
        subpop_pop_key="population",
        subpop_names_key="subpop",
    )

    first_sim_index = 1
    run_id = "test"
    prefix = ""
    s = setup.Setup(
        setup_name="test_seir",
        subpop_setup=ss,
        nslots=1,
        npi_scenario="None",
        npi_config_seir=config["interventions"]["settings"]["None"],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=True,
        write_csv=False,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
        dt=0.25,
    )
    s.integration_method = "legacy"

    seeding_data, seeding_amounts = s.seedingAndIC.load_seeding(sim_id=100, setup=s)
    initial_conditions = s.seedingAndIC.draw_ic(sim_id=100, setup=s)

    npi = NPI.NPIBase.execute(npi_config=s.npi_config_seir, global_config=config, subpops=s.subpop_struct.subpop_names)

    params = s.parameters.parameters_quick_draw(s.n_days, s.nsubpops)
    params = s.parameters.parameters_reduce(params, npi)

    (
        unique_strings,
        transition_array,
        proportion_array,
        proportion_info,
    ) = s.compartments.get_transition_array()
    parsed_parameters = s.compartments.parse_parameters(params, s.parameters.pnames, unique_strings)

    states = seir.steps_SEIR(
        s,
        parsed_parameters,
        transition_array,
        proportion_array,
        proportion_info,
        initial_conditions,
        seeding_data,
        seeding_amounts,
    )

    completepop = s.subpop_pop.sum()
    origpop = s.subpop_pop
    for it in range(s.n_days):
        totalpop = 0
        for i in range(s.nsubpops):
            totalpop += states[0].sum(axis=1)[it, i]
            assert states[0].sum(axis=1)[it, i] - 1e-3 < origpop[i] < states[0].sum(axis=1)[it, i] + 1e-3
        assert completepop - 1e-3 < totalpop < completepop + 1e-3


def test_steps_SEIR_nb_simple_spread_with_txt_matrices():
    os.chdir(os.path.dirname(__file__))
    config.clear()
    config.read(user=False)
    print("test mobility with txt matrices")
    config.set_file(f"{DATA_DIR}/config.yml")

    ss = subpopulation_structure.SubpopulationStructure(
        setup_name="test_seir",
        geodata_file=f"{DATA_DIR}/geodata.csv",
        mobility_file=f"{DATA_DIR}/mobility.txt",
        subpop_pop_key="population",
        subpop_names_key="subpop",
    )

    first_sim_index = 1
    run_id = "test_SeedOneNode"
    prefix = ""
    s = setup.Setup(
        setup_name="test_seir",
        subpop_setup=ss,
        nslots=1,
        npi_scenario="None",
        npi_config_seir=config["interventions"]["settings"]["None"],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=True,
        write_csv=False,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
        dt=1,
    )

    seeding_data, seeding_amounts = s.seedingAndIC.load_seeding(sim_id=100, setup=s)
    initial_conditions = s.seedingAndIC.draw_ic(sim_id=100, setup=s)

    npi = NPI.NPIBase.execute(npi_config=s.npi_config_seir, global_config=config, subpops=s.subpop_struct.subpop_names)

    params = s.parameters.parameters_quick_draw(s.n_days, s.nsubpops)
    params = s.parameters.parameters_reduce(params, npi)

    (
        unique_strings,
        transition_array,
        proportion_array,
        proportion_info,
    ) = s.compartments.get_transition_array()
    parsed_parameters = s.compartments.parse_parameters(params, s.parameters.pnames, unique_strings)

    for i in range(5):
        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert df[(df["mc_value_type"] == "prevalence") & (df["mc_infection_stage"] == "R")].loc[str(s.tf), "10001"] > 1
        assert df[(df["mc_value_type"] == "prevalence") & (df["mc_infection_stage"] == "R")].loc[str(s.tf), "20002"] > 1

        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert df[(df["mc_value_type"] == "prevalence") & (df["mc_infection_stage"] == "R")].loc[str(s.tf), "20002"] > 1
        assert df[(df["mc_value_type"] == "incidence") & (df["mc_infection_stage"] == "I1")].max()["20002"] > 0
        assert df[(df["mc_value_type"] == "incidence") & (df["mc_infection_stage"] == "I1")].max()["10001"] > 0


def test_steps_SEIR_nb_simple_spread_with_csv_matrices():
    os.chdir(os.path.dirname(__file__))
    config.clear()
    config.read(user=False)
    config.set_file(f"{DATA_DIR}/config.yml")
    print("test mobility with csv matrices")

    ss = subpopulation_structure.SubpopulationStructure(
        setup_name="test_seir",
        geodata_file=f"{DATA_DIR}/geodata.csv",
        mobility_file=f"{DATA_DIR}/mobility.csv",
        subpop_pop_key="population",
        subpop_names_key="subpop",
    )

    first_sim_index = 1
    run_id = "test_SeedOneNode"
    prefix = ""

    s = setup.Setup(
        setup_name="test_seir",
        subpop_setup=ss,
        nslots=1,
        npi_scenario="None",
        npi_config_seir=config["interventions"]["settings"]["None"],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=True,
        write_csv=False,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
        dt=1,
    )

    seeding_data, seeding_amounts = s.seedingAndIC.load_seeding(sim_id=100, setup=s)
    initial_conditions = s.seedingAndIC.draw_ic(sim_id=100, setup=s)

    npi = NPI.NPIBase.execute(npi_config=s.npi_config_seir, global_config=config, subpops=s.subpop_struct.subpop_names)

    params = s.parameters.parameters_quick_draw(s.n_days, s.nsubpops)
    params = s.parameters.parameters_reduce(params, npi)

    (
        unique_strings,
        transition_array,
        proportion_array,
        proportion_info,
    ) = s.compartments.get_transition_array()
    parsed_parameters = s.compartments.parse_parameters(params, s.parameters.pnames, unique_strings)

    for i in range(5):
        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)

        assert df[(df["mc_value_type"] == "incidence") & (df["mc_infection_stage"] == "I1")].max()["20002"] > 0
        assert df[(df["mc_value_type"] == "incidence") & (df["mc_infection_stage"] == "I1")].max()["10001"] > 0


def test_steps_SEIR_no_spread():
    os.chdir(os.path.dirname(__file__))
    print("test mobility with no spread")
    config.set_file(f"{DATA_DIR}/config.yml")

    ss = subpopulation_structure.SubpopulationStructure(
        setup_name="test_seir",
        geodata_file=f"{DATA_DIR}/geodata.csv",
        mobility_file=f"{DATA_DIR}/mobility.txt",
        subpop_pop_key="population",
        subpop_names_key="subpop",
    )

    first_sim_index = 1
    run_id = "test_SeedOneNode"
    prefix = ""
    s = setup.Setup(
        setup_name="test_seir",
        subpop_setup=ss,
        nslots=1,
        npi_scenario="None",
        npi_config_seir=config["interventions"]["settings"]["None"],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=True,
        write_csv=False,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
        dt=0.25,
    )

    seeding_data, seeding_amounts = s.seedingAndIC.load_seeding(sim_id=100, setup=s)
    initial_conditions = s.seedingAndIC.draw_ic(sim_id=100, setup=s)

    s.mobility.data = s.mobility.data * 0

    npi = NPI.NPIBase.execute(npi_config=s.npi_config_seir, global_config=config, subpops=s.subpop_struct.subpop_names)

    params = s.parameters.parameters_quick_draw(s.n_days, s.nsubpops)
    params = s.parameters.parameters_reduce(params, npi)

    (
        unique_strings,
        transition_array,
        proportion_array,
        proportion_info,
    ) = s.compartments.get_transition_array()
    parsed_parameters = s.compartments.parse_parameters(params, s.parameters.pnames, unique_strings)

    for i in range(10):
        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert (
            df[(df["mc_value_type"] == "prevalence") & (df["mc_infection_stage"] == "R")].loc[str(s.tf), "20002"] == 0.0
        )

        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert (
            df[(df["mc_value_type"] == "prevalence") & (df["mc_infection_stage"] == "R")].loc[str(s.tf), "20002"] == 0.0
        )


def test_continuation_resume():
    os.chdir(os.path.dirname(__file__))
    config.clear()
    config.read(user=False)
    config.set_file("data/config.yml")
    npi_scenario = "Scenario1"
    sim_id2write = 100
    nslots = 1
    interactive = False
    write_csv = False
    write_parquet = True
    first_sim_index = 1
    run_id = "test"
    prefix = ""
    stoch_traj_flag = True

    spatial_config = config["subpop_setup"]
    spatial_base_path = pathlib.Path(config["data_path"].get())
    s = setup.Setup(
        setup_name=config["name"].get() + "_" + str(npi_scenario),
        subpop_setup=subpopulation_structure.SubpopulationStructure(
            setup_name=config["setup_name"].get(),
            geodata_file=spatial_base_path / spatial_config["geodata"].get(),
            mobility_file=spatial_base_path / spatial_config["mobility"].get(),
            subpop_pop_key="population",
            subpop_names_key="subpop",
        ),
        nslots=nslots,
        npi_scenario=npi_scenario,
        npi_config_seir=config["interventions"]["settings"][npi_scenario],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        seir_config=config["seir"],
        initial_conditions_config=config["initial_conditions"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=interactive,
        write_csv=write_csv,
        write_parquet=write_parquet,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
    )
    seir.onerun_SEIR(sim_id2write=int(sim_id2write), s=s, config=config)

    states_old = pq.read_table(
        file_paths.create_file_name(s.in_run_id, s.in_prefix, 100, "seir", "parquet"),
    ).to_pandas()
    states_old = states_old[states_old["date"] == "2020-03-15"].reset_index(drop=True)

    config.clear()
    config.read(user=False)
    config.set_file("data/config_continuation_resume.yml")
    npi_scenario = "Scenario1"
    sim_id2write = 100
    nslots = 1
    interactive = False
    write_csv = False
    write_parquet = True
    first_sim_index = 1
    run_id = "test"
    prefix = ""
    stoch_traj_flag = True

    spatial_config = config["subpop_setup"]
    spatial_base_path = pathlib.Path(config["data_path"].get())
    s = setup.Setup(
        setup_name=config["name"].get() + "_" + str(npi_scenario),
        subpop_setup=subpopulation_structure.SubpopulationStructure(
            setup_name=config["setup_name"].get(),
            geodata_file=spatial_base_path / spatial_config["geodata"].get(),
            mobility_file=spatial_base_path / spatial_config["mobility"].get(),
            subpop_pop_key="population",
            subpop_names_key="subpop",
        ),
        nslots=nslots,
        npi_scenario=npi_scenario,
        npi_config_seir=config["interventions"]["settings"][npi_scenario],
        seeding_config=config["seeding"],
        initial_conditions_config=config["initial_conditions"],
        parameters_config=config["seir"]["parameters"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=interactive,
        write_csv=write_csv,
        write_parquet=write_parquet,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
    )
    seir.onerun_SEIR(sim_id2write=sim_id2write, s=s, config=config)

    states_new = pq.read_table(
        file_paths.create_file_name(s.in_run_id, s.in_prefix, sim_id2write, "seir", "parquet"),
    ).to_pandas()
    states_new = states_new[states_new["date"] == "2020-03-15"].reset_index(drop=True)
    assert (
        (
            states_old[states_old["mc_value_type"] == "prevalence"]
            == states_new[states_new["mc_value_type"] == "prevalence"]
        )
        .all()
        .all()
    )

    seir.onerun_SEIR(sim_id2write=sim_id2write + 1, s=s, sim_id2load=sim_id2write, load_ID=True, config=config)
    states_new = pq.read_table(
        file_paths.create_file_name(s.in_run_id, s.in_prefix, sim_id2write + 1, "seir", "parquet"),
    ).to_pandas()
    states_new = states_new[states_new["date"] == "2020-03-15"].reset_index(drop=True)
    for path in ["model_output/seir", "model_output/snpi", "model_output/spar"]:
        shutil.rmtree(path)


def test_inference_resume():
    os.chdir(os.path.dirname(__file__))
    config.clear()
    config.read(user=False)
    config.set_file("data/config.yml")
    npi_scenario = "Scenario1"
    sim_id2write = 100
    nslots = 1
    interactive = False
    write_csv = False
    write_parquet = True
    first_sim_index = 1
    run_id = "test"
    prefix = ""
    stoch_traj_flag = True

    spatial_config = config["subpop_setup"]
    spatial_base_path = pathlib.Path(config["data_path"].get())
    s = setup.Setup(
        setup_name=config["name"].get() + "_" + str(npi_scenario),
        subpop_setup=subpopulation_structure.SubpopulationStructure(
            setup_name=config["setup_name"].get(),
            geodata_file=spatial_base_path / spatial_config["geodata"].get(),
            mobility_file=spatial_base_path / spatial_config["mobility"].get(),
            subpop_pop_key="population",
            subpop_names_key="subpop",
        ),
        nslots=nslots,
        npi_scenario=npi_scenario,
        npi_config_seir=config["interventions"]["settings"][npi_scenario],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=interactive,
        write_csv=write_csv,
        write_parquet=write_parquet,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
    )
    seir.onerun_SEIR(sim_id2write=int(sim_id2write), s=s, config=config)
    npis_old = pq.read_table(
        file_paths.create_file_name(s.in_run_id, s.in_prefix, sim_id2write, "snpi", "parquet")
    ).to_pandas()

    config.clear()
    config.read(user=False)
    config.set_file("data/config_inference_resume.yml")
    npi_scenario = "Scenario1"
    nslots = 1
    interactive = False
    write_csv = False
    write_parquet = True
    first_sim_index = 1
    run_id = "test"
    prefix = ""
    stoch_traj_flag = True

    spatial_config = config["subpop_setup"]
    spatial_base_path = pathlib.Path(config["data_path"].get())
    s = setup.Setup(
        setup_name=config["name"].get() + "_" + str(npi_scenario),
        subpop_setup=subpopulation_structure.SubpopulationStructure(
            setup_name=config["setup_name"].get(),
            geodata_file=spatial_base_path / spatial_config["geodata"].get(),
            mobility_file=spatial_base_path / spatial_config["mobility"].get(),
            subpop_pop_key="population",
            subpop_names_key="subpop",
        ),
        nslots=nslots,
        npi_scenario=npi_scenario,
        npi_config_seir=config["interventions"]["settings"][npi_scenario],
        seeding_config=config["seeding"],
        initial_conditions_config=config["initial_conditions"],
        parameters_config=config["seir"]["parameters"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        interactive=interactive,
        write_csv=write_csv,
        write_parquet=write_parquet,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
    )

    seir.onerun_SEIR(sim_id2write=sim_id2write + 1, s=s, sim_id2load=sim_id2write, load_ID=True, config=config)
    npis_new = pq.read_table(
        file_paths.create_file_name(s.in_run_id, s.in_prefix, sim_id2write + 1, "snpi", "parquet")
    ).to_pandas()

    assert npis_old["npi_name"].isin(["None", "Wuhan", "KansasCity"]).all()
    assert npis_new["npi_name"].isin(["None", "Wuhan", "KansasCity", "BrandNew"]).all()
    # assert((['None', 'Wuhan', 'KansasCity']).isin(npis_old["npi_name"]).all())
    # assert((['None', 'Wuhan', 'KansasCity', 'BrandNew']).isin(npis_new["npi_name"]).all())
    assert (npis_old["start_date"] == "2020-04-01").all()
    assert (npis_old["end_date"] == "2020-05-15").all()
    assert (npis_new["start_date"] == "2020-04-02").all()
    assert (npis_new["end_date"] == "2020-05-16").all()
    for path in ["model_output/seir", "model_output/snpi", "model_output/spar"]:
        shutil.rmtree(path)

    ## Clean up after ourselves


def test_parallel_compartments_with_vacc():
    os.chdir(os.path.dirname(__file__))
    config.set_file(f"{DATA_DIR}/config_parallel.yml")

    ss = subpopulation_structure.SubpopulationStructure(
        setup_name="test_seir",
        geodata_file=f"{DATA_DIR}/geodata.csv",
        mobility_file=f"{DATA_DIR}/mobility.txt",
        subpop_pop_key="population",
        subpop_names_key="subpop",
    )

    first_sim_index = 1
    run_id = "test_parallel"
    prefix = ""
    s = setup.Setup(
        setup_name="test_seir",
        subpop_setup=ss,
        nslots=1,
        npi_scenario="Scenario_vacc",
        npi_config_seir=config["interventions"]["settings"]["Scenario_vacc"],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        seir_config=config["seir"],
        interactive=True,
        write_csv=False,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
        dt=0.25,
    )

    seeding_data, seeding_amounts = s.seedingAndIC.load_seeding(sim_id=100, setup=s)
    initial_conditions = s.seedingAndIC.draw_ic(sim_id=100, setup=s)

    npi = NPI.NPIBase.execute(npi_config=s.npi_config_seir, global_config=config, subpops=s.subpop_struct.subpop_names)

    params = s.parameters.parameters_quick_draw(s.n_days, s.nsubpops)
    params = s.parameters.parameters_reduce(params, npi)

    (
        unique_strings,
        transition_array,
        proportion_array,
        proportion_info,
    ) = s.compartments.get_transition_array()
    parsed_parameters = s.compartments.parse_parameters(params, s.parameters.pnames, unique_strings)

    for i in range(5):
        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert (
            df[
                (df["mc_value_type"] == "prevalence")
                & (df["mc_infection_stage"] == "R")
                & (df["mc_vaccination_stage"] == "first_dose")
            ].max()["10001"]
            > 2
        )

        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert (
            df[
                (df["mc_value_type"] == "prevalence")
                & (df["mc_infection_stage"] == "R")
                & (df["mc_vaccination_stage"] == "first_dose")
            ].max()["10001"]
            > 2
        )


def test_parallel_compartments_no_vacc():
    os.chdir(os.path.dirname(__file__))
    config.set_file(f"{DATA_DIR}/config_parallel.yml")

    ss = subpopulation_structure.SubpopulationStructure(
        setup_name="test_seir",
        geodata_file=f"{DATA_DIR}/geodata.csv",
        mobility_file=f"{DATA_DIR}/mobility.txt",
        subpop_pop_key="population",
        subpop_names_key="subpop",
    )

    first_sim_index = 1
    run_id = "test_parallel"
    prefix = ""

    s = setup.Setup(
        setup_name="test_seir",
        subpop_setup=ss,
        nslots=1,
        npi_scenario="Scenario_novacc",
        npi_config_seir=config["interventions"]["settings"]["Scenario_novacc"],
        parameters_config=config["seir"]["parameters"],
        seeding_config=config["seeding"],
        ti=config["start_date"].as_date(),
        tf=config["end_date"].as_date(),
        seir_config=config["seir"],
        interactive=True,
        write_csv=False,
        first_sim_index=first_sim_index,
        in_run_id=run_id,
        in_prefix=prefix,
        out_run_id=run_id,
        out_prefix=prefix,
        dt=0.25,
    )

    seeding_data, seeding_amounts = s.seedingAndIC.load_seeding(sim_id=100, setup=s)
    initial_conditions = s.seedingAndIC.draw_ic(sim_id=100, setup=s)

    npi = NPI.NPIBase.execute(npi_config=s.npi_config_seir, global_config=config, subpops=s.subpop_struct.subpop_names)

    params = s.parameters.parameters_quick_draw(s.n_days, s.nsubpops)
    params = s.parameters.parameters_reduce(params, npi)

    (
        unique_strings,
        transition_array,
        proportion_array,
        proportion_info,
    ) = s.compartments.get_transition_array()
    parsed_parameters = s.compartments.parse_parameters(params, s.parameters.pnames, unique_strings)

    for i in range(5):
        s.npi_config_seir = config["interventions"]["settings"]["Scenario_vacc"]
        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert (
            df[
                (df["mc_value_type"] == "prevalence")
                & (df["mc_infection_stage"] == "R")
                & (df["mc_vaccination_stage"] == "first_dose")
            ].max()["10001"]
            == 0
        )

        states = seir.steps_SEIR(
            s,
            parsed_parameters,
            transition_array,
            proportion_array,
            proportion_info,
            initial_conditions,
            seeding_data,
            seeding_amounts,
        )
        df = seir.states2Df(s, states)
        assert (
            df[
                (df["mc_value_type"] == "prevalence")
                & (df["mc_infection_stage"] == "R")
                & (df["mc_vaccination_stage"] == "first_dose")
            ].max()["10001"]
            == 0
        )
