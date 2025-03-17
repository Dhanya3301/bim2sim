import re
from pathlib import Path

import bim2sim
from bim2sim.tasks.base import ITask
from OMPython import OMCSessionZMQ

class SimulateModelOM(ITask):
    """Simulate TEASER model using OpenModelica."""
    reads = ('bldg_names',)
    touches = ('sim_results_path',)
    final = True

    def run(self, bldg_names):
        """Simulates the exported TEASER model using OpenModelica.

        Args:
            bldg_names: List of building names in the project.

        Returns:
            sim_results_path: Path where simulation results are stored.
        """
        if not self.playground.sim_settings.dymola_simulation:
            self.logger.warning(f"Skipping task {self.name} as 'dymola_simulation' is set to False.")
            return None,

        if self.playground.sim_settings.path_aixlib:
            dir_aixlib = self.playground.sim_settings.path_aixlib
        else:
            self.logger.warning("The 'path_aixlib' setting is missing, using default path.")
            dir_aixlib = Path(bim2sim.__file__).parent / 'plugins' / f'Plugin{self.playground.project.plugin_cls.name}' / 'test' / 'regression' / 'library' / 'library_AixLib' / 'AixLib' / 'package.mo'

        if not dir_aixlib.exists():
            raise FileNotFoundError(f"AixLib directory not found. Please set 'path_aixlib' or run regression test setup.")

        regex = re.compile("[^a-zA-Z0-9]")
        model_export_name = regex.sub("", self.prj_name)
        dir_model_package = Path(self.paths.export / 'TEASER' / 'Model' / model_export_name / 'package.mo')
        sim_results_path = Path(self.paths.export / 'TEASER' / 'SimResults' / model_export_name)
        packages = [dir_model_package, dir_aixlib]

        omc = OMCSessionZMQ()

        n_success = 0
        for n_sim, bldg_name in enumerate(bldg_names):
            self.logger.info(f"Starting simulation for {bldg_name} ({n_sim+1}/{len(bldg_names)})")
            sim_model = f"{model_export_name}.{bldg_name}.{bldg_name}"
            bldg_result_dir = sim_results_path / bldg_name
            bldg_result_dir.mkdir(parents=True, exist_ok=True)

            omc.sendExpression(f'loadFile("{dir_aixlib}")')
            omc.sendExpression(f'loadFile("{dir_model_package}")')

            if not omc.sendExpression(f'checkModel("{sim_model}")'):
                raise Exception(f"Model {sim_model} has errors and cannot be simulated.")

            simulation_setup = {
                "startTime": 0,
                "stopTime": 3.1536e+07,
                "numberOfIntervals": 8760,
                "method": "cvode",
                "tolerance": 0.001
            }
            setup_str = ",".join(f"{key}={value}" for key, value in simulation_setup.items())
            result_file = str(bldg_result_dir / "teaser_results.mat")

            simulate_cmd = f'simulateModel("{sim_model}", {setup_str}, outputFormat="mat", fileNamePrefix="{result_file}")'
            if omc.sendExpression(simulate_cmd):
                n_success += 1
            else:
                self.logger.error(f"Simulation failed for {bldg_name}.")

        self.playground.sim_settings.simulated = True
        self.logger.info(f"Successfully simulated {n_success}/{len(bldg_names)} buildings.")
        self.logger.info(f"Results stored in: {sim_results_path}")

        return sim_results_path,
