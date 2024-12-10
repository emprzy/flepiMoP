import os
from gempyor import seeding, model_info
from gempyor.utils import config

DATA_DIR = os.path.dirname(__file__) + "/data"
os.chdir(os.path.dirname(__file__))


class TestSeeding:
    def test_Seeding_success(self):
        config.clear()
        config.read(user=False)
        config.set_file(f"{DATA_DIR}/config.yml")

        s = model_info.ModelInfo(
            config=config,
            setup_name="test_seeding",
            nslots=1,
            seir_modifiers_scenario=None,
            outcome_modifiers_scenario=None,
            write_csv=False,
        )
        sic = seeding.SeedingFactory(config=s.seeding_config)
        assert sic.seeding_config == s.seeding_config

    def test_Seeding_draw_success(self):
        config.clear()
        config.read(user=False)
        config.set_file(f"{DATA_DIR}/config.yml")

        s = model_info.ModelInfo(
            config=config,
            setup_name="test_seeding",
            nslots=1,
            seir_modifiers_scenario=None,
            outcome_modifiers_scenario=None,
            write_csv=False,
        )
        sic = seeding.SeedingFactory(config=s.seeding_config)
        s.seeding_config["method"] = "NoSeeding"

        seeding_result = sic.get_from_config(
            s.compartments,
            s.subpop_struct,
            s.n_days,
            s.ti,
            s.tf,
            s.get_input_filename(
                ftype=s.seeding_config["seeding_file_type"].get(),
                sim_id=0,
                extension_override="csv",
            ),
        )
        print(seeding_result)
