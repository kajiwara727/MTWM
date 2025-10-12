# reporting.py (Corrected)
import os
import z3
# configからMAX_LEVEL_DIFFもインポート
from config import MAX_SHARING_VOLUME, MAX_LEVEL_DIFF
from visualization import SolutionVisualizer

class SolutionReporter:
    """
    Analyzes the optimization results from the Z3 solver and generates text-based reports.
    """
    def __init__(self, problem, model):
        self.problem = problem
        self.model = model

    def generate_full_report(self, min_waste, elapsed_time):
        """
        Executes the full reporting pipeline: analysis, console summary, file summary, and visualization.
        """
        analysis_results = self.analyze_solution()
        self._print_console_summary(analysis_results, min_waste, elapsed_time)
        output_dir = self._save_summary_to_file(analysis_results, min_waste, elapsed_time)
        if output_dir and self.model:
            visualizer = SolutionVisualizer(self.problem, self.model)
            visualizer.visualize_solution(output_dir)
        return output_dir

    def report_from_checkpoint(self, analysis, waste):
        """
        Generates a report from analysis results loaded from a checkpoint.
        """
        self._print_console_summary(analysis, waste, 0)
        output_dir = self._save_summary_to_file(analysis, waste, 0)
        if output_dir:
            print("\nVisualization was not generated because the solution is from a previous run.")
            print(f"   Summary files saved in: {output_dir}")

    def analyze_solution(self):
        """
        Parses the solver model to extract structured data about the solution.
        """
        if self.model is None: return None
        results = {"total_operations": 0, "total_reagent_units": 0, "reagent_usage": {}, "nodes_details": []}
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
                    
                    results["nodes_details"].append({
                        "target_id": tree_idx, "level": level, "name": f"v_m{tree_idx}_l{level}_k{node_idx}",
                        "total_input": total_input,
                        "ratio_composition": [self.model.eval(r).as_long() for r in node['ratio_vars']],
                        "mixing_str": ' + '.join(self._generate_mixing_description(node, tree_idx))
                    })
        return results

    def _get_input_vars(self, node):
        return (node.get('reagent_vars', []) +
                list(node.get('intra_sharing_vars', {}).values()) +
                list(node.get('inter_sharing_vars', {}).values()))

    def _generate_mixing_description(self, node, tree_idx):
        mix_desc = []
        for r_idx, r_var in enumerate(node['reagent_vars']):
            if (val := self.model.eval(r_var).as_long()) > 0: mix_desc.append(f"{val} x Reagent{r_idx+1}")
        for key, w_var in node.get('intra_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0: mix_desc.append(f"{val} x v_m{tree_idx}_{key.replace('from_', '')}")
        for key, w_var in node.get('inter_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                m_src, lk_src = key.split('_l')
                mix_desc.append(f"{val} x v_{m_src.replace('from_m', 'm')}_l{lk_src}")
        return mix_desc

    def _print_console_summary(self, results, min_waste, elapsed_time):
        time_str = f"(in {elapsed_time:.2f} sec)" if elapsed_time > 0 else "(from checkpoint)"
        print(f"\nOptimal Solution Found {time_str}")
        print(f"Minimum Total Waste: {min_waste}")
        print("="*18 + " SUMMARY " + "="*18)
        print(f"Total mixing operations: {results['total_operations']}")
        print(f"Total reagent units used: {results['total_reagent_units']}")
        print("\nReagent usage breakdown:")
        for r_idx in sorted(results['reagent_usage'].keys()):
            print(f"  Reagent {r_idx+1}: {results['reagent_usage'][r_idx]} unit(s)")
        print("="*45)

    def _save_summary_to_file(self, results, min_waste, elapsed_time):
        base_name = f"({')-('.join(['_'.join(map(str, t['ratios'])) for t in self.problem.targets_config])})"
        # ディレクトリ名にパラメータ設定を含むように修正
        vol_suffix = f"_vol{MAX_SHARING_VOLUME}" if MAX_SHARING_VOLUME is not None else "_volNone"
        lvl_suffix = f"_lvl{MAX_LEVEL_DIFF}" if MAX_LEVEL_DIFF is not None else "_lvlNone"
        output_dir = self._get_unique_directory_name(base_name + vol_suffix + lvl_suffix)
        
        os.makedirs(output_dir, exist_ok=True)
        
        filepath = os.path.join(output_dir, 'summary.txt')
        content = self._build_summary_file_content(results, min_waste, elapsed_time, output_dir)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content))
            print(f"\nResults successfully saved to: {filepath}")
            return output_dir
        except IOError as e:
            print(f"\nError saving results to file: {e}")
            return None

    def _get_unique_directory_name(self, base_dir):
        counter = 1
        output_dir = base_dir
        while os.path.isdir(output_dir):
            output_dir = f"{base_dir}_{counter}"
            counter += 1
        return output_dir

    def _build_summary_file_content(self, results, min_waste, elapsed_time, dir_name):
        content = [
            "="*40, f"Optimization Results for: {os.path.basename(dir_name)}", "="*40,
            f"\nSolved in {elapsed_time:.2f} seconds." if elapsed_time > 0 else "\nLoaded from checkpoint.",
            "\n--- Target Configuration ---"
        ]
        for i, target in enumerate(self.problem.targets_config):
            content.extend([
                f"Target {i+1}:",
                f"  Ratios: {' : '.join(map(str, target['ratios']))}",
                f"  Factors: {target['factors']}"
            ])
        content.extend([
            "\n--- Optimization Settings ---",
            f"Max Sharing Volume: {MAX_SHARING_VOLUME or 'No limit'}",
            # レポートにMAX_LEVEL_DIFFの設定値を出力
            f"Max Level Difference: {MAX_LEVEL_DIFF or 'No limit'}",
            "-"*28,
            f"\nMinimum Total Waste: {min_waste}",
            f"Total mixing operations: {results['total_operations']}",
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