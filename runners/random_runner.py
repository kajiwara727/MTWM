# runners/random_runner.py
import os
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum
from utils.helpers import generate_random_ratios
from reporting.summary import save_random_run_summary

class RandomRunner(BaseRunner):
    """ 'random' モードの実行を担当するクラス """
    def run(self):
        settings = self.config.RANDOM_SETTINGS
        print(f"Preparing to run {settings['k_runs']} random simulations...")
        
        base_run_name = f"{self.config.RUN_NAME}_random_runs"
        base_output_dir = self._get_unique_output_directory_name("random", base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All random run results will be saved under: '{base_output_dir}/'")
        
        all_run_results = []
        
        for i in range(settings['k_runs']):
            print(f"\n{'='*20} Running Random Simulation {i+1}/{settings['k_runs']} {'='*20}")
            
            temp_config = []
            for j in range(settings['n_targets']):
                ratios = generate_random_ratios(settings['t_reagents'], settings['S_ratio_sum'])
                factors = find_factors_for_sum(sum(ratios), self.config.MAX_MIXER_SIZE)
                if factors is None:
                    print(f"Warning: Could not determine factors for random ratios {ratios}. Skipping this run.")
                    continue
                temp_config.append({
                    'name': f"RandomTarget_{i+1}_{j+1}",
                    'ratios': ratios,
                    'factors': factors
                })

            if not temp_config: continue

            run_name = f"run_{i+1}"
            output_dir = os.path.join(base_output_dir, run_name)
            
            final_waste, exec_time, total_ops, total_reagents = self._run_single_optimization(temp_config, output_dir, run_name)
            
            all_run_results.append({
                'run_name': run_name, 'config': temp_config,
                'final_value': final_waste, 'elapsed_time': exec_time,
                'total_operations': total_ops, 'total_reagents': total_reagents
            })

        save_random_run_summary(all_run_results, base_output_dir)