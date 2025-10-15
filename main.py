# main.py
import os
import z3
from config import (get_targets_config, OPTIMIZATION_MODE, MAX_SHARING_VOLUME, 
                    MAX_LEVEL_DIFF, ENABLE_CHECKPOINTING, MAX_MIXER_SIZE, 
                    FACTORS_MODE, RUN_NAME)
from dfmm_utils import find_factors_for_sum, build_dfmm_forest, calculate_p_values_from_structure
from utils import generate_config_hash
from mtwm_model import MTWMProblem
from z3_solver import Z3Solver
from reporting import SolutionReporter
from checkpoint_handler import CheckpointHandler
from pre_run_analyzer import PreRunAnalyzer

def get_unique_output_directory_name(config_hash):
    """設定のハッシュに基づき、一意の出力ディレクトリ名を生成する"""
    # フォルダ名を RUN_NAME_{ハッシュの先頭8文字} に変更
    base_name = f"{RUN_NAME}_{config_hash[:8]}"
    
    # 既に同名のフォルダが存在する場合は、末尾に番号を付ける
    output_dir = base_name
    counter = 1
    while os.path.isdir(output_dir):
        output_dir = f"{base_name}_{counter}"
        counter += 1
    return output_dir

def main():
    """プログラムのメイン実行フロー"""
    # 1. 基本設定を読み込む
    targets_config = get_targets_config()

    # 2. 'factors' をモードに応じて決定する
    print(f"--- Factor Determination Mode: {FACTORS_MODE.upper()} ---")
    if FACTORS_MODE == 'auto':
        print("Calculating factors automatically using DFMM...")
        for target in targets_config:
            ratio_sum = sum(target['ratios'])
            factors = find_factors_for_sum(ratio_sum, MAX_MIXER_SIZE)
            if factors is None:
                raise ValueError(
                    f"Could not automatically determine factors for target '{target['name']}' "
                    f"with ratios {target['ratios']} (sum={ratio_sum})."
                )
            target['factors'] = factors
    elif FACTORS_MODE == 'manual':
        print("Using manually specified factors from config.py...")
        for target in targets_config:
            if 'factors' not in target or not target['factors']:
                raise ValueError(
                    f"In 'manual' mode, target '{target['name']}' must have a 'factors' list."
                )
            # 比率の合計と因数の積が一致するか検証
            if sum(target['ratios']) != eval('*'.join(map(str, target['factors']))):
                 raise ValueError(
                    f"For target '{target['name']}', sum of ratios ({sum(target['ratios'])}) "
                    f"does not match the product of factors ({eval('*'.join(map(str, target['factors'])))})."
                )
    else:
        raise ValueError(f"Unknown FACTORS_MODE: '{FACTORS_MODE}'. Must be 'auto' or 'manual'.")

    # 3. 最終的な設定内容を表示
    print("\n--- Configuration for this run ---")
    print(f"Run Name: {RUN_NAME}") # 実行名を表示
    for target in targets_config:
        print(f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}")
    print(f"Optimization Mode: {OPTIMIZATION_MODE.upper()}")
    print("-" * 35 + "\n")

    # 4. DFMMに基づき、ツリー構造とP値を事前計算
    tree_structures = build_dfmm_forest(targets_config)
    p_values = calculate_p_values_from_structure(tree_structures, targets_config)

    # 5. MTWM問題の構造を定義
    problem = MTWMProblem(targets_config, tree_structures, p_values)

    # 6. 今回の実行設定から一意のハッシュとディレクトリ名を決定
    config_hash = generate_config_hash(targets_config, OPTIMIZATION_MODE, RUN_NAME)
    output_dir = get_unique_output_directory_name(config_hash)
    os.makedirs(output_dir, exist_ok=True)
    print(f"All outputs will be saved to: '{output_dir}/'")

    # 7. 事前チェックを実行
    analyzer = PreRunAnalyzer(problem, tree_structures)
    analyzer.generate_report(output_dir)

    # 8. 各コンポーネントを初期化
    solver = Z3Solver(problem, objective_mode=OPTIMIZATION_MODE)
    checkpoint_handler = None
    if ENABLE_CHECKPOINTING:
        # CheckpointHandlerにもconfig_hashを渡す
        checkpoint_handler = CheckpointHandler(targets_config, OPTIMIZATION_MODE, RUN_NAME, config_hash)
    
    # 9. Z3ソルバーで最適化を実行
    best_model, final_value, last_analysis, elapsed_time = solver.solve(checkpoint_handler)

    # 10. 最適化結果をレポートとして出力
    reporter = SolutionReporter(problem, best_model, objective_mode=OPTIMIZATION_MODE)
    if best_model:
        reporter.generate_full_report(final_value, elapsed_time, output_dir)
    elif last_analysis and ENABLE_CHECKPOINTING:
        print("\n--- No new solution found. Reporting from the last checkpoint ---")
        reporter.report_from_checkpoint(last_analysis, final_value, output_dir)
    else:
        print("\n--- No solution found ---")
        if solver.last_check_result == z3.unknown:
            print(f"Solver timed out or was interrupted ({elapsed_time:.2f} sec)")
        else: # z3.unsat
            print(f"No solution found (unsat) ({elapsed_time:.2f} sec)")
        
        if checkpoint_handler:
            checkpoint_handler.delete_checkpoint()

if __name__ == "__main__":
    main()

