from .base_runner import BaseRunner
from utils.helpers import generate_config_hash
from core.algorithm.dfmm import apply_auto_factors

class StandardRunner(BaseRunner):
    def run(self):
        targets_config = self.config.get_targets_config()
        
        if self.config.MODE == 'auto':
            print("Calculating factors automatically...")
            apply_auto_factors(targets_config, self.config.MAX_MIXER_SIZE)
        else:
            print("Using manually specified factors...")

        config_hash = generate_config_hash(targets_config, self.config.OPTIMIZATION_MODE, self.config.RUN_NAME)
        output_dir = self._get_unique_output_directory_name(config_hash, self.config.RUN_NAME)
        
        self.engine.run_single_optimization(targets_config, output_dir, self.config.RUN_NAME)