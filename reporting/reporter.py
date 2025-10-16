# reporting/reporter.py
import os
import z3
from config import MAX_SHARING_VOLUME, MAX_LEVEL_DIFF, MAX_MIXER_SIZE
from .visualizer import SolutionVisualizer

class SolutionReporter:
    """Z3ソルバーの結果を解析し、テキストベースのレポートを生成するクラス"""

    def __init__(self, problem, model, objective_mode="waste"):
        self.problem = problem
        self.model = model
        self.objective_mode = objective_mode
        
    def generate_full_report(self, min_value, elapsed_time, output_dir):
        """解析、コンソール出力、ファイル保存、可視化の全プロセスを実行"""
        analysis_results = self.analyze_solution()
        self._print_console_summary(analysis_results, min_value, elapsed_time)
        self._save_summary_to_file(analysis_results, min_value, elapsed_time, output_dir)
        if self.model:
            visualizer = SolutionVisualizer(self.problem, self.model)
            visualizer.visualize_solution(output_dir)

    def report_from_checkpoint(self, analysis, value, output_dir):
        """チェックポイントから読み込んだ結果をレポートし、可視化を試みる"""
        from z3_solver import Z3Solver

        self._print_console_summary(analysis, value, 0)
        self._save_summary_to_file(analysis, value, 0, output_dir)
        
        print("\nAttempting to generate visualization from checkpoint data...")
        temp_solver = Z3Solver(self.problem, objective_mode=self.objective_mode)
        temp_solver.opt.add(temp_solver.objective_variable == value)
        
        if temp_solver.check() == z3.sat:
            checkpoint_model = temp_solver.get_model()
            visualizer = SolutionVisualizer(self.problem, checkpoint_model)
            visualizer.visualize_solution(output_dir)
            print(f"   Visualization successfully generated from checkpoint.")
        else:
            print("\nVisualization could not be generated because the model could not be recreated.")
                
    def analyze_solution(self):
        if not self.model: return None
        results = {"total_operations": 0, "total_reagent_units": 0, "total_waste": 0, "reagent_usage": {}, "nodes_details": []}
        for tree_idx, tree in enumerate(self.problem.forest):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    total_input = self.model.eval(z3.Sum(self._get_input_vars(node))).as_long()
                    if total_input == 0: continue
                    results["total_operations"] += 1
                    reagent_vals = [self.model.eval(r).as_long() for r in node['reagent_vars']]
                    for r_idx, val in enumerate(reagent_vals):
                        if val > 0:
                            results["total_reagent_units"] += val
                            results["reagent_usage"][r_idx] = results["reagent_usage"].get(r_idx, 0) + val
                    if 'waste_var' in node:
                         results["total_waste"] += self.model.eval(node['waste_var']).as_long()
                    results["nodes_details"].append({
                        "target_id": tree_idx, "level": level, "name": f"v_m{tree_idx}_l{level}_k{node_idx}",
                        "total_input": total_input,
                        "ratio_composition": [self.model.eval(r).as_long() for r in node['ratio_vars']],
                        "mixing_str": self._generate_mixing_description(node, tree_idx)
                    })
        return results

    def _get_input_vars(self, node):
        return (node.get('reagent_vars', []) +
                list(node.get('intra_sharing_vars', {}).values()) +
                list(node.get('inter_sharing_vars', {}).values()))

    def _generate_mixing_description(self, node, tree_idx):
        desc = []
        for r_idx, r_var in enumerate(node.get('reagent_vars', [])):
            if (val := self.model.eval(r_var).as_long()) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
        for key, w_var in node.get('intra_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                desc.append(f"{val} x v_m{tree_idx}_{key.replace('from_', '')}")
        for key, w_var in node.get('inter_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                m_src, lk_src = key.split('_l')
                desc.append(f"{val} x v_{m_src.replace('from_m', 'm')}_l{lk_src}")
        return ' + '.join(desc)

    def _print_console_summary(self, results, min_value, elapsed_time):
        time_str = f"(in {elapsed_time:.2f} sec)" if elapsed_time > 0 else "(from checkpoint)"
        print(f"\nOptimal Solution Found {time_str}")
        objective_str = "Minimum Total Waste" if self.objective_mode == "waste" else "Minimum Operations"
        print(f"{objective_str}: {min_value}")
        print("="*18 + " SUMMARY " + "="*18)
        if results:
            print(f"Total mixing operations: {results['total_operations']}")
            print(f"Total waste generated: {results['total_waste']}")
            print(f"Total reagent units used: {results['total_reagent_units']}")
            print("\nReagent usage breakdown:")
            for r_idx in sorted(results['reagent_usage'].keys()):
                print(f"  Reagent {r_idx+1}: {results['reagent_usage'][r_idx]} unit(s)")
        print("="*45)

    def _save_summary_to_file(self, results, min_value, elapsed_time, output_dir):
        filepath = os.path.join(output_dir, 'summary.txt')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                content = self._build_summary_file_content(results, min_value, elapsed_time, output_dir)
                f.write('\n'.join(content))
            print(f"\nResults summary saved to: {filepath}")
        except IOError as e:
            print(f"\nError saving results to file: {e}")

    def _build_summary_file_content(self, results, min_value, elapsed_time, dir_name):
        objective_str = "Minimum Total Waste" if self.objective_mode == "waste" else "Minimum Operations"
        content = [
            "="*40, f"Optimization Results for: {os.path.basename(dir_name)}", "="*40,
            f"\nSolved in {elapsed_time:.2f} seconds." if elapsed_time > 0 else "\nLoaded from checkpoint.",
            "\n--- Target Configuration ---"
        ]
        for i, target in enumerate(self.problem.targets_config):
            content.extend([f"Target {i+1}:", f"  Ratios: {' : '.join(map(str, target['ratios']))}", f"  Factors: {target['factors']}"])
        content.extend([
            "\n--- Optimization Settings ---",
            f"Optimization Mode: {self.objective_mode.upper()}",
            f"Max Sharing Volume: {MAX_SHARING_VOLUME or 'No limit'}",
            f"Max Level Difference: {MAX_LEVEL_DIFF or 'No limit'}",
            f"Max Mixer Size: {MAX_MIXER_SIZE}",
            "-"*28,
            f"\n{objective_str}: {min_value}"
        ])
        if results:
            content.extend([
                f"Total mixing operations: {results['total_operations']}",
                f"Total waste generated: {results['total_waste']}",
                f"Total reagent units used: {results['total_reagent_units']}",
                "\n--- Reagent Usage Breakdown ---"
            ])
            for t in sorted(results['reagent_usage'].keys()):
                content.append(f"  Reagent {t+1}: {results['reagent_usage'][t]} unit(s)")
            content.append("\n\n--- Mixing Process Details ---")
            current_target = -1
            for detail in results["nodes_details"]:
                if detail["target_id"] != current_target:
                    current_target = detail["target_id"]
                    content.append(f"\n[Target {current_target + 1}]")
                content.extend([
                    f" Level {detail['level']}:",
                    f"   Node {detail['name']}: total_input = {detail['total_input']}",
                    f"     Ratio composition: {detail['ratio_composition']}",
                    f"     Mixing: {detail['mixing_str']}" if detail['mixing_str'] else ""
                ])
        return content