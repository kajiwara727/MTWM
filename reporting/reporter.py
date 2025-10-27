# reporting/reporter.py
import os
from config import MAX_SHARING_VOLUME, MAX_LEVEL_DIFF, MAX_MIXER_SIZE
from .visualizer import SolutionVisualizer

class SolutionReporter:
    """
    ソルバーが見つけた解（モデル）を解析し、人間が読める形式の
    テキストベースのレポートを生成し、可視化モジュールを呼び出すクラス。
    """

    def __init__(self, problem, model, objective_mode="waste"):
        """
        コンストラクタ。

        Args:
            problem (MTWMProblem): 最適化問題の定義オブジェクト。
            model (OrToolsModelAdapter): ソルバーの解にアクセスするためのアダプタ。
            objective_mode (str): 最適化の目的 ('waste' or 'operations')。
        """
        self.problem = problem
        self.model = model
        self.objective_mode = objective_mode

    def generate_full_report(self, min_value, elapsed_time, output_dir, enable_visualization=True): 
        """
        解の分析、コンソールへのサマリー出力、ファイルへの詳細レポート保存、
        そして結果の可視化という一連のレポート生成プロセスを実行します。

        Args:
            min_value (int): 最適化によって得られた目的関数の最小値。
            elapsed_time (float): 最適化にかかった時間（秒）。
            output_dir (str): レポートと画像を保存するディレクトリのパス。
            enable_visualization (bool): グラフ描画を有効にするか。
        """
        analysis_results = self.analyze_solution()
        self._print_console_summary(analysis_results, min_value, elapsed_time)
        self._save_summary_to_file(analysis_results, min_value, elapsed_time, output_dir)
        
        # --- 可視化のON/OFF機能 ---
        if self.model and enable_visualization:
            visualizer = SolutionVisualizer(self.problem, self.model)
            visualizer.visualize_solution(output_dir)
        elif not enable_visualization:
            print("Visualization skipped (disabled in config).")

    def analyze_solution(self):
        """
        モデルアダプタを介して解を解析し、レポートに必要な情報を抽出します。
        """
        if not self.model: return None
        results = {"total_operations": 0, "total_reagent_units": 0, "total_waste": 0, "reagent_usage": {}, "nodes_details": []}
        
        for tree_idx, tree in enumerate(self.problem.forest):
            for level, nodes in tree.items():
                for node_idx, node_def in enumerate(nodes):
                    
                    # z3.Sum(..) の代わりに、事前に定義された総入力変数名を使用
                    total_input_var_name = node_def['total_input_var_name']
                    total_input = self.model.eval(total_input_var_name).as_long()
                    
                    if total_input == 0: continue

                    results["total_operations"] += 1
                    
                    # 試薬使用量を集計
                    reagent_vals = [self.model.eval(var_name).as_long() for var_name in node_def['reagent_vars']]
                    for r_idx, val in enumerate(reagent_vals):
                        if val > 0:
                            results["total_reagent_units"] += val
                            results["reagent_usage"][r_idx] = results["reagent_usage"].get(r_idx, 0) + val
                            
                    # 廃棄物量を集計
                    if node_def['waste_var_name']:
                         results["total_waste"] += self.model.eval(node_def['waste_var_name']).as_long()
                         
                    # 各ノードの詳細情報を記録
                    results["nodes_details"].append({
                        "target_id": tree_idx, "level": level, "name": node_def['node_name'],
                        "total_input": total_input,
                        "ratio_composition": [self.model.eval(var_name).as_long() for var_name in node_def['ratio_vars']],
                        "mixing_str": self._generate_mixing_description(node_def, tree_idx)
                    })
        return results

    def _get_input_vars(self, node_def):
        """ノードへの全入力（試薬、内部共有、外部共有）の「変数名」をリストで返す。"""
        return (node_def.get('reagent_vars', []) +
                list(node_def.get('intra_sharing_vars', {}).values()) +
                list(node_def.get('inter_sharing_vars', {}).values()))

    def _generate_mixing_description(self, node_def, tree_idx):
        """ノードの混合内容を説明する文字列を生成する。"""
        desc = []
        # 試薬の投入
        for r_idx, r_var_name in enumerate(node_def.get('reagent_vars', [])):
            if (val := self.model.eval(r_var_name).as_long()) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
        # 同じツリー内からの共有
        for key, w_var_name in node_def.get('intra_sharing_vars', {}).items():
            if (val := self.model.eval(w_var_name).as_long()) > 0:
                desc.append(f"{val} x v_m{tree_idx}_{key.replace('from_', '')}")
        # 異なるツリーからの共有
        for key, w_var_name in node_def.get('inter_sharing_vars', {}).items():
            if (val := self.model.eval(w_var_name).as_long()) > 0:
                m_src, lk_src = key.split('_l')
                desc.append(f"{val} x v_{m_src.replace('from_m', 'm')}_l{lk_src}")
        return ' + '.join(desc)

    def _print_console_summary(self, results, min_value, elapsed_time):
        """最適化結果のサマリーをコンソールに出力する。"""
        time_str = f"(in {elapsed_time:.2f} sec)"
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
        """詳細な結果レポートをテキストファイルに保存する。"""
        filepath = os.path.join(output_dir, 'summary.txt')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                content = self._build_summary_file_content(results, min_value, elapsed_time, output_dir)
                f.write('\n'.join(content))
            print(f"\nResults summary saved to: {filepath}")
        except IOError as e:
            print(f"\nError saving results to file: {e}")

    def _build_summary_file_content(self, results, min_value, elapsed_time, dir_name):
        """ファイルに書き込むための全コンテンツを文字列リストとして構築する。"""
        objective_str = "Minimum Total Waste" if self.objective_mode == "waste" else "Minimum Operations"
        content = [
            "="*40, f"Optimization Results for: {os.path.basename(dir_name)}", "="*40,
            f"\nSolved in {elapsed_time:.2f} seconds.",
            "\n--- Target Configuration ---"
        ]
        # ターゲット設定の記録
        for i, target in enumerate(self.problem.targets_config):
            content.extend([f"Target {i+1}:", f"  Ratios: {' : '.join(map(str, target['ratios']))}", f"  Factors: {target['factors']}"])
        # 最適化設定の記録
        content.extend([
            "\n--- Optimization Settings ---",
            f"Optimization Mode: {self.objective_mode.upper()}",
            f"Max Sharing Volume: {MAX_SHARING_VOLUME or 'No limit'}",
            f"Max Level Difference: {MAX_LEVEL_DIFF or 'No limit'}",
            f"Max Mixer Size: {MAX_MIXER_SIZE}",
            "-"*28,
            f"\n{objective_str}: {min_value}"
        ])
        # 結果サマリー
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
            # 混合プロセスの詳細
            current_target = -1
            for detail in results["nodes_details"]:
                if detail["target_id"] != current_target:
                    current_target = detail["target_id"]
                    content.append(f"\n[Target {current_target + 1} ({self.problem.targets_config[current_target]['name']})]")
                content.extend([
                    f" Level {detail['level']}:",
                    f"   Node {detail['name']}: total_input = {detail['total_input']}",
                    f"     Ratio composition: {detail['ratio_composition']}",
                    f"     Mixing: {detail['mixing_str']}" if detail['mixing_str'] else "     (No mixing actions for this node)"
                ])
        return content