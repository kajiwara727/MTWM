# runners/base_runner.py
import os
from abc import ABC, abstractmethod

# 修正: 循環参照を避けるため、必要なクラスを直接インポート
from core.problem import MTWMProblem
from core.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from z3_solver import Z3Solver # z3_solver.pyは提供されていると仮定
from reporting.analyzer import PreRunAnalyzer
from reporting.reporter import SolutionReporter
from utils.checkpoint import CheckpointHandler
from utils.helpers import generate_config_hash

class BaseRunner(ABC):
    """実行戦略クラスの基底クラス"""
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def run(self):
        """このランナーの主処理を実行する"""
        raise NotImplementedError

    def _get_unique_output_directory_name(self, config_hash, base_name_prefix):
        """設定のハッシュに基づき、一意の出力ディレクトリ名を生成する"""
        base_name = f"{base_name_prefix}_{config_hash[:8]}"
        output_dir = base_name
        counter = 1
        while os.path.isdir(output_dir):
            output_dir = f"{base_name}_{counter}"
            counter += 1
        return output_dir

    def _run_single_optimization(self, targets_config_for_run, output_dir, run_name_for_report):
        """
        単一のターゲット設定セットに対して最適化を実行し、結果の詳細を返す。
        """
        print("\n--- Configuration for this run ---")
        print(f"Run Name: {run_name_for_report}")
        for target in targets_config_for_run:
            print(f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}")
        print(f"Optimization Mode: {self.config.OPTIMIZATION_MODE.upper()}")
        print("-" * 35 + "\n")

        tree_structures = build_dfmm_forest(targets_config_for_run)
        p_values = calculate_p_values_from_structure(tree_structures, targets_config_for_run)
        problem = MTWMProblem(targets_config_for_run, tree_structures, p_values)

        os.makedirs(output_dir, exist_ok=True)
        print(f"All outputs for this run will be saved to: '{output_dir}/'")
        analyzer = PreRunAnalyzer(problem, tree_structures)
        analyzer.generate_report(output_dir)

        solver = Z3Solver(problem, objective_mode=self.config.OPTIMIZATION_MODE)
        checkpoint_handler = None
        if self.config.ENABLE_CHECKPOINTING and self.config.MODE != 'auto_permutations':
            config_hash = generate_config_hash(targets_config_for_run, self.config.OPTIMIZATION_MODE, run_name_for_report)
            checkpoint_handler = CheckpointHandler(targets_config_for_run, self.config.OPTIMIZATION_MODE, run_name_for_report, config_hash)

        best_model, final_value, last_analysis, elapsed_time = solver.solve(checkpoint_handler)
        reporter = SolutionReporter(problem, best_model, objective_mode=self.config.OPTIMIZATION_MODE)
        
        ops = 'N/A'
        reagents = 'N/A'

        if best_model:
            reporter.generate_full_report(final_value, elapsed_time, output_dir)
            analysis_results = reporter.analyze_solution()
            ops = analysis_results.get('total_operations', 'N/A')
            reagents = analysis_results.get('total_reagent_units', 'N/A')
        elif last_analysis and checkpoint_handler:
            ops = last_analysis.get('total_operations', 'N/A')
            reagents = last_analysis.get('total_reagent_units', 'N/A')
            elapsed_time = last_analysis.get('elapsed_time', 0) if last_analysis else 0
            reporter.report_from_checkpoint(last_analysis, final_value, output_dir)
        else:
            print("\n--- No solution found for this configuration ---")
            
        return final_value, elapsed_time, ops, reagents