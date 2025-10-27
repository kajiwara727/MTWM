# runners/base_runner.py
import os
from abc import ABC, abstractmethod

# 循環参照を避けるため、必要なクラスを直接インポートします。
# これらは、各ランナーが共通して使用するコアコンポーネントです。
from core.problem import MTWMProblem
from core.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from core.or_tools_solver import OrToolsSolver 

from reporting.analyzer import PreRunAnalyzer
from reporting.reporter import SolutionReporter
from utils.helpers import generate_config_hash

class BaseRunner(ABC):
    """
    異なる実行戦略（'manual', 'random'など）の共通ロジックをまとめた抽象基底クラス。
    具体的な実行フローはサブクラスで実装されます。
    """
    def __init__(self, config):
        """
        コンストラクタ。

        Args:
            config (Config): 設定情報を保持するオブジェクト。
        """
        self.config = config

    @abstractmethod
    def run(self):
        """
        このランナーの主処理を実行するための抽象メソッド。
        サブクラス（StandardRunner, RandomRunnerなど）で必ず実装する必要があります。
        """
        raise NotImplementedError

    def _get_unique_output_directory_name(self, config_hash, base_name_prefix):
        """
        設定のハッシュ値に基づき、他の実行結果と重複しない一意の出力ディレクトリ名を生成します。
        同じ名前のディレクトリが存在する場合は、末尾に連番を付与します。
        """
        base_name = f"{base_name_prefix}_{config_hash[:8]}"
        output_dir = base_name
        counter = 1
        # ディレクトリが既に存在する場合の衝突回避
        while os.path.isdir(output_dir):
            output_dir = f"{base_name}_{counter}"
            counter += 1
        return output_dir

    def _run_single_optimization(self, targets_config_for_run, output_dir, run_name_for_report):
        """
        単一のターゲット設定セットに対して、以下の処理を順番に実行する共通メソッドです。
        1. 問題設定の表示
        2. 混合ツリーとP値の計算
        3. 問題オブジェクトの構築
        4. 事前分析レポートの生成
        5. ソルバーの実行
        6. 結果レポートの生成
        """
        print("\n--- Configuration for this run ---")
        print(f"Run Name: {run_name_for_report}")
        for target in targets_config_for_run:
            print(f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}")
        print(f"Optimization Mode: {self.config.OPTIMIZATION_MODE.upper()}")
        print("-" * 35 + "\n")

        # 1. DFMMアルゴリズムでツリー構造とP値を計算
        tree_structures = build_dfmm_forest(targets_config_for_run)
        p_values = calculate_p_values_from_structure(tree_structures, targets_config_for_run)
        # 2. 最適化問題オブジェクトを生成
        problem = MTWMProblem(targets_config_for_run, tree_structures, p_values)

        # 3. 出力ディレクトリを作成し、事前分析レポートを生成
        os.makedirs(output_dir, exist_ok=True)
        print(f"All outputs for this run will be saved to: '{output_dir}/'")
        analyzer = PreRunAnalyzer(problem, tree_structures)
        analyzer.generate_report(output_dir)

        # 4. OrToolsソルバーを初期化
        solver = OrToolsSolver(
            problem, 
            objective_mode=self.config.OPTIMIZATION_MODE,
            max_workers=self.config.MAX_CPU_WORKERS
        ) 
        
        # 5. 最適化を実行
        # best_model, final_value, last_analysis, elapsed_time = solver.solve(checkpoint_handler) # <--- 修正前
        best_model, final_value, analysis_results, elapsed_time = solver.solve() # <--- 修正後

        reporter = SolutionReporter(problem, best_model, objective_mode=self.config.OPTIMIZATION_MODE)

        ops = 'N/A'
        reagents = 'N/A'

        # 6. 結果に応じてレポートを生成
        if best_model:
            # 新しい解が見つかった場合 (ENABLE_VISUALIZATION を渡す)
            reporter.generate_full_report(
                final_value, 
                elapsed_time, 
                output_dir, 
                self.config.ENABLE_VISUALIZATION
            ) 
            
            if analysis_results:
                ops = analysis_results.get('total_operations', 'N/A')
                reagents = analysis_results.get('total_reagent_units', 'N/A')
        
        else:
            # 解が見つからなかった場合
            print("\n--- No solution found for this configuration ---")
        # 'random'モードのサマリー用に結果を返す
        return final_value, elapsed_time, ops, reagents