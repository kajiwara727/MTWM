# core/execution.py
import os
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.model.problem import MTWMProblem
from core.solver.engine import OrToolsSolver
from reporting.analyzer import PreRunAnalyzer
from reporting.reporter import SolutionReporter
from utils.config_loader import Config

class ExecutionEngine:
    """
    単一のターゲット設定に対する最適化プロセス（構築→計算→レポート）
    を実行・管理するクラス。
    """

    def __init__(self, config):
        self.config = config

    def run_single_optimization(self, targets_config, output_dir, run_name):
        """
        最適化ワークフローを実行します。
        """
        # --- 実行設定をコンソールに出力 ---
        print("\n--- Configuration for this run ---")
        print(f"Run Name: {run_name}")
        for target in targets_config:
            print(f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}")
        print(f"Optimization Mode: {self.config.OPTIMIZATION_MODE.upper()}")
        print("-" * 35 + "\n")

        # 1. DFMMアルゴリズムでツリー構造とP値を計算
        tree_structures = build_dfmm_forest(targets_config)
        p_values = calculate_p_values_from_structure(tree_structures, targets_config)
        
        # 2. 最適化問題オブジェクトを生成
        problem = MTWMProblem(targets_config, tree_structures, p_values)

        # 3. 出力ディレクトリ作成と事前分析レポート
        os.makedirs(output_dir, exist_ok=True)
        print(f"All outputs for this run will be saved to: '{output_dir}/'")
        
        analyzer = PreRunAnalyzer(problem, tree_structures)
        analyzer.generate_report(output_dir)

        # 4. ソルバー初期化と実行
        solver = OrToolsSolver(problem, objective_mode=self.config.OPTIMIZATION_MODE)
        best_model, final_val, analysis, elapsed_time = solver.solve()

        # 5. レポート生成
        # [MODIFIED] レポート設定を作成して __init__ に渡すように修正
        report_settings = {
            "max_sharing_volume": self.config.MAX_SHARING_VOLUME or "No limit",
            "max_level_diff": self.config.MAX_LEVEL_DIFF or "No limit",
            "max_mixer_size": self.config.MAX_MIXER_SIZE,
        }
        
        reporter = SolutionReporter(
            problem,
            best_model,
            objective_mode=self.config.OPTIMIZATION_MODE,
            enable_visualization=self.config.ENABLE_VISUALIZATION, # ここで渡す
            optimization_settings=report_settings                # ここで渡す
        )
        
        ops, reagents, total_waste = 'N/A', 'N/A', 'N/A'
        
        if best_model:
            # [MODIFIED] 引数を削除 (初期化時に渡しているため不要)
            reporter.generate_full_report(final_val, elapsed_time, output_dir)
            
            if analysis:
                ops = analysis.get('total_operations', 'N/A')
                reagents = analysis.get('total_reagent_units', 'N/A')
                total_waste = analysis.get('total_waste', 'N/A')
        else:
            print("\n--- No solution found for this configuration ---")

        return final_val, elapsed_time, ops, reagents, total_waste