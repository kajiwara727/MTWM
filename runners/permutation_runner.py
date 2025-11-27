# runners/permutation_runner.py
import os
from .base_runner import BaseRunner
from utils.helpers import generate_config_hash
from core.generator import PermutationScenarioGenerator
from reporting import save_permutation_summary, save_run_results_to_json, save_run_results_to_text

class PermutationRunner(BaseRunner):
    def run(self):
        targets_config_base = self.config.get_targets_config()
        print("Preparing to test all factor permutations...")

        base_run_name = f"{self.config.RUN_NAME}_permutations"
        config_hash = generate_config_hash(targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name)
        base_output_dir = self._get_unique_output_directory_name(config_hash, base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"Results will be saved under: '{base_output_dir}/'")

        generator = PermutationScenarioGenerator(self.config)
        scenarios = generator.generate_permutations(targets_config_base)
        print(f"Found {len(scenarios)} unique factor permutation combinations.")

        all_run_results = []

        for i, scenario in enumerate(scenarios):
            run_name = scenario['run_name']
            targets = scenario['targets']
            print(f"\n{'='*20} Running Permutation {i+1}/{len(scenarios)} {'='*20}")
            
            output_dir = os.path.join(base_output_dir, run_name)
            final_val, exec_time, ops, reagents, total_waste = self.engine.run_single_optimization(targets, output_dir, run_name)
            
            all_run_results.append({
                'run_name': run_name, 'targets': targets,
                'final_value': final_val, 'elapsed_time': exec_time,
                'total_operations': ops, 'total_reagents': reagents,
                'total_waste': total_waste, 'objective_mode': self.config.OPTIMIZATION_MODE
            })

        save_permutation_summary(all_run_results, base_output_dir, self.config.OPTIMIZATION_MODE)
        save_run_results_to_json(all_run_results, base_output_dir)
        save_run_results_to_text(all_run_results, base_output_dir)