# runners/file_load_runner.py
import json
import os
from .base_runner import BaseRunner
from utils.helpers import generate_config_hash
from reporting import save_comparison_summary, save_run_results_to_json, save_run_results_to_text

class FileLoadRunner(BaseRunner):
    def run(self):
        config_path = self.config.CONFIG_LOAD_FILE
        if not config_path: raise ValueError("CONFIG_LOAD_FILE not set.")

        try:
            print(f"Loading configuration from file: {config_path}...")
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not data: raise ValueError("Config file is empty.")
            
            targets_configs = data if isinstance(data, list) and 'targets' in data[0] else [{'run_name': self.config.RUN_NAME, 'targets': data}] if isinstance(data, list) and 'ratios' in data[0] else []
            if not targets_configs: raise ValueError("Invalid config file structure.")
        except Exception as e:
            raise RuntimeError(f"Error loading config: {e}")

        print(f"Loaded {len(targets_configs)} patterns.")
        base_output_dir = self._get_unique_output_directory_name(self.config.RUN_NAME, self.config.RUN_NAME + "_comparison")
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"Results will be saved under: '{base_output_dir}/'")

        all_results = []
        for i, run_data in enumerate(targets_configs):
            run_name = run_data.get('run_name', f"Run_{i+1}")
            targets = run_data['targets']
            print(f"\n{'='*20} Running Loaded Pattern {i+1}/{len(targets_configs)} ({run_name}) {'='*20}")

            base_run_name = f"{run_name}_loaded"
            config_hash = generate_config_hash(targets, self.config.OPTIMIZATION_MODE, base_run_name)
            output_dir = os.path.join(base_output_dir, self._get_unique_output_directory_name(config_hash, base_run_name))

            final_val, exec_time, ops, reagents, total_waste = self.engine.run_single_optimization(targets, output_dir, self.config.RUN_NAME)
            
            # 目的モード以外の値も記録するためにtotal_waste等を使用
            all_results.append({
                'run_name': run_name, 'final_value': final_val, 'elapsed_time': exec_time,
                'total_operations': ops, 'total_reagents': reagents, 'total_waste': total_waste,
                'config': targets, 'objective_mode': self.config.OPTIMIZATION_MODE
            })

        save_comparison_summary(all_results, base_output_dir, self.config.OPTIMIZATION_MODE)
        save_run_results_to_json(all_results, base_output_dir)
        save_run_results_to_text(all_results, base_output_dir)
        print("\nAll comparison runs finished successfully.")