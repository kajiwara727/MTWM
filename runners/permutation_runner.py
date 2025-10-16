# runners/permutation_runner.py
import os
import itertools
import copy
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum, generate_unique_permutations
from utils.helpers import generate_config_hash

class PermutationRunner(BaseRunner):
    """ 'auto_permutations' モードの実行を担当するクラス """
    def run(self):
        targets_config_base = self.config.get_targets_config()
        print("Preparing to test all factor permutations...")
        
        base_run_name = f"{self.config.RUN_NAME}_permutations"
        config_hash = generate_config_hash(targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name)
        base_output_dir = self._get_unique_output_directory_name(config_hash, base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All permutation results will be saved under: '{base_output_dir}/'")

        target_perms_options = []
        for target in targets_config_base:
            base_factors = find_factors_for_sum(sum(target['ratios']), self.config.MAX_MIXER_SIZE)
            if base_factors is None:
                raise ValueError(f"Could not determine factors for {target['name']}.")
            perms = generate_unique_permutations(base_factors)
            target_perms_options.append(perms)
        
        all_config_combinations = list(itertools.product(*target_perms_options))
        total_runs = len(all_config_combinations)
        print(f"Found {total_runs} unique factor permutation combinations to test.")

        for i, combo in enumerate(all_config_combinations):
            print(f"\n{'='*20} Running Combination {i+1}/{total_runs} {'='*20}")
            temp_config = copy.deepcopy(targets_config_base)
            perm_name_parts = []
            for j, target in enumerate(temp_config):
                current_factors = list(combo[j])
                target['factors'] = current_factors
                perm_name_parts.append("_".join(map(str, current_factors)))
            
            perm_name = "-".join(perm_name_parts)
            run_name = f"run_{i+1}_{perm_name}"
            output_dir = os.path.join(base_output_dir, run_name)
            
            self._run_single_optimization(temp_config, output_dir, run_name)