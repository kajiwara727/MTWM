# runners/standard_runner.py
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum
from utils.helpers import generate_config_hash

class StandardRunner(BaseRunner):
    """ 'auto' または 'manual' モードの実行を担当するクラス """
    def run(self):
        targets_config_base = self.config.get_targets_config()
        
        mode_name = "Using manually specified factors..." if self.config.MODE == 'manual' else "Calculating factors automatically..."
        print(mode_name)
        
        if self.config.MODE == 'auto':
            for target in targets_config_base:
                factors = find_factors_for_sum(sum(target['ratios']), self.config.MAX_MIXER_SIZE)
                if factors is None:
                    raise ValueError(f"Could not determine factors for {target['name']}.")
                target['factors'] = factors
        
        config_hash = generate_config_hash(targets_config_base, self.config.OPTIMIZATION_MODE, self.config.RUN_NAME)
        output_dir = self._get_unique_output_directory_name(config_hash, self.config.RUN_NAME)
        self._run_single_optimization(targets_config_base, output_dir, self.config.RUN_NAME)