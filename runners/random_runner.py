import os
import json
from .base_runner import BaseRunner
from core.generator import RandomScenarioGenerator
from reporting import save_random_run_summary, save_run_results_to_json

class RandomRunner(BaseRunner):
    def run(self):
        num_runs = self.config.RANDOM_K_RUNS
        print(f"Preparing to run {num_runs} random simulations...")
        
        base_run_name = f"{self.config.RUN_NAME}-random-{num_runs}runs"
        base_output_dir = self._get_unique_output_directory_name("random", base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"Results will be saved under: '{base_output_dir}/'")

        generator = RandomScenarioGenerator(self.config)
        scenarios = generator.generate_batch_configs(num_runs)
        print(f"Generated {len(scenarios)} scenarios.")

        all_run_results = []
        saved_configs = []

        for scenario in scenarios:
            run_name = scenario['run_name']
            targets = scenario['targets']
            print(f"\n{'='*20} Running {run_name} {'='*20}")
            
            output_dir = os.path.join(base_output_dir, run_name)
            final_val, exec_time, ops, reagents, total_waste = self.engine.run_single_optimization(targets, output_dir, run_name)
            
            all_run_results.append({
                'run_name': run_name, 'config': targets,
                'final_value': final_val, 'elapsed_time': exec_time,
                'total_operations': ops, 'total_reagents': reagents,
                'total_waste': total_waste, 'objective_mode': self.config.OPTIMIZATION_MODE
            })
            saved_configs.append(scenario)

        save_random_run_summary(all_run_results, base_output_dir)
        save_run_results_to_json(all_run_results, base_output_dir)
        
        with open(os.path.join(base_output_dir, "random_configs.json"), 'w', encoding='utf-8') as f:
            json.dump(saved_configs, f, indent=4)