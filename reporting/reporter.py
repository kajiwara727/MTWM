# reporting/reporter.py
import os
from .visualizer import SolutionVisualizer
from utils.config_loader import Config

class SolutionReporter:
    def __init__(self, problem, model, objective_mode="waste", enable_visualization=True, optimization_settings=None):
        self.problem = problem
        self.model = model
        self.objective_mode = objective_mode
        self.enable_visualization = enable_visualization
        self.optimization_settings = optimization_settings or {
            "max_sharing_volume": "No limit",
            "max_level_diff": "No limit",
            "max_mixer_size": "N/A",
        }

    def generate_full_report(self, min_value, elapsed_time, output_dir):
        analysis_results = self.model.analyze() # model.analyze() を呼ぶ形に変更 (Adapterがanalyzeを持つか、Solver側で呼んで渡すか。ExecutionEngineではmodel.analyze()の結果を渡していないため、ここで呼ぶのが自然ですが、Engine側で `best_analysis` を取得済み。ここを調整します。)
        # ※ MTWM_TimeImprovement の Engine では best_model.analyze() を呼んで best_analysis を取得していますが、
        # Reporter内でも analyze() を呼んでいます。
        
        if self.objective_mode == "waste" and analysis_results:
            analysis_results["total_waste"] = int(min_value)

        self._print_console_summary(analysis_results, min_value, elapsed_time)
        self._save_summary_to_file(analysis_results, min_value, elapsed_time, output_dir)
        
        if self.model and self.enable_visualization:
            SolutionVisualizer(self.problem, self.model).visualize_solution(output_dir)
        elif self.model:
            print("Skipping graph visualization.")

    def _print_console_summary(self, results, min_value, elapsed_time):
        print(f"\n<Optimization> Optimal Solution Found (in {elapsed_time:.2f} sec)")
        objective_str = "Minimum Total Waste" if self.objective_mode == "waste" else "Minimum Operations"
        print(f"{objective_str}: {min_value}")
        print("=" * 18 + " SUMMARY " + "=" * 18)
        if results:
            print(f"Total mixing operations: {results['total_operations']}")
            print(f"Total waste generated: {results['total_waste']}")
            print(f"Total reagent units used: {results['total_reagent_units']}")
            print("\nReagent usage breakdown:")
            for r_idx in sorted(results["reagent_usage"].keys()):
                print(f"  Reagent {r_idx+1}: {results['reagent_usage'][r_idx]} unit(s)")
        print("=" * 45)

    def _save_summary_to_file(self, results, min_value, elapsed_time, output_dir):
        filepath = os.path.join(output_dir, "summary.txt")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                content = self._build_summary_file_content(results, min_value, elapsed_time, output_dir)
                f.write("\n".join(content))
            print(f"\nResults summary saved to: {filepath}")
        except IOError as e:
            print(f"\nError saving results: {e}")

    def _build_summary_file_content(self, results, min_value, elapsed_time, dir_name):
        objective_str = "Minimum Total Waste" if self.objective_mode == "waste" else "Minimum Operations"
        content = [
            "=" * 40, f"Optimization Results for: {os.path.basename(dir_name)}", "=" * 40,
            f"\nSolved in {elapsed_time:.2f} seconds.", "\n--- Target Configuration ---"
        ]
        for i, target in enumerate(self.problem.targets_config):
            content.extend([f"Target {i+1}:", f"  Ratios: {' : '.join(map(str, target['ratios']))}", f"  Factors: {target['factors']}"])
            
        settings = self.optimization_settings
        content.extend([
            "\n--- Optimization Settings ---",
            f"Optimization Mode: {self.objective_mode.upper()}",
            f"Max Sharing Volume: {settings['max_sharing_volume']}",
            f"Max Level Difference: {settings['max_level_diff']}",
            f"Max Mixer Size: {settings['max_mixer_size']}",
            "-" * 28, f"\n{objective_str}: {min_value}"
        ])

        if results:
            content.extend([
                f"Total mixing operations: {results['total_operations']}",
                f"Total waste generated: {results['total_waste']}",
                f"Total reagent units used: {results['total_reagent_units']}",
                "\n--- Reagent Usage Breakdown ---"
            ])
            for t in sorted(results["reagent_usage"].keys()):
                content.append(f"  Reagent {t+1}: {results['reagent_usage'][t]} unit(s)")
            content.append("\n\n--- Mixing Process Details ---")
            
            current_target = -2
            for detail in results["nodes_details"]:
                if detail["target_id"] != current_target:
                    current_target = detail["target_id"]
                    header = "[Peer Mixing Nodes]" if current_target == -1 else f"[Target {current_target + 1} ({self.problem.targets_config[current_target]['name']})]"
                    content.append(f"\n{header}")
                
                level_str = f"{detail['level']}" if isinstance(detail['level'], int) else f"{detail['level']:.1f}"
                content.extend([
                    f" Level {level_str}:",
                    f"   Node {detail['name']}: total_input = {detail['total_input']}",
                    f"     Ratio composition: {detail['ratio_composition']}",
                    f"     Mixing: {detail['mixing_str']}" if detail["mixing_str"] else "     (No mixing)"
                ])
        
        # [追加] 最後に合計時間を再出力
        content.append(f"\nTotal Execution Time: {elapsed_time:.2f} seconds")
        return content
