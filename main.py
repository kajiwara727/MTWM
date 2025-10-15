# main.py
import os
import z3
import itertools
import copy
from config import (get_targets_config, OPTIMIZATION_MODE, MAX_SHARING_VOLUME, 
                    MAX_LEVEL_DIFF, ENABLE_CHECKPOINTING, MAX_MIXER_SIZE, 
                    FACTORS_MODE, RUN_NAME)
from dfmm_utils import (find_factors_for_sum, build_dfmm_forest, 
                        calculate_p_values_from_structure, generate_unique_permutations)
from utils import generate_config_hash
from mtwm_model import MTWMProblem
from z3_solver import Z3Solver
from reporting import SolutionReporter
from checkpoint_handler import CheckpointHandler
from pre_run_analyzer import PreRunAnalyzer

def get_unique_output_directory_name(config_hash, base_name_prefix):
    """設定のハッシュに基づき、一意の出力ディレクトリ名を生成する"""
    base_name = f"{base_name_prefix}_{config_hash[:8]}"
    output_dir = base_name
    counter = 1
    while os.path.isdir(output_dir):
        output_dir = f"{base_name}_{counter}"
        counter += 1
    return output_dir

def run_single_optimization(targets_config_for_run, output_dir, run_name_for_report):
    """
    単一のターゲット設定セットに対して、最適化からレポート生成までの一連の処理を実行する。
    """
    # 1. 最終的な設定内容を表示
    print("\n--- Configuration for this run ---")
    print(f"Run Name: {run_name_for_report}")
    for target in targets_config_for_run:
        print(f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}")
    print(f"Optimization Mode: {OPTIMIZATION_MODE.upper()}")
    print("-" * 35 + "\n")

    # 2. DFMMに基づき、ツリー構造とP値を事前計算
    tree_structures = build_dfmm_forest(targets_config_for_run)
    p_values = calculate_p_values_from_structure(tree_structures, targets_config_for_run)

    # 3. MTWM問題の構造を定義
    problem = MTWMProblem(targets_config_for_run, tree_structures, p_values)

    # 4. 事前チェックを実行
    os.makedirs(output_dir, exist_ok=True)
    print(f"All outputs for this run will be saved to: '{output_dir}/'")
    analyzer = PreRunAnalyzer(problem, tree_structures)
    analyzer.generate_report(output_dir)

    # 5. 各コンポーネントを初期化
    solver = Z3Solver(problem, objective_mode=OPTIMIZATION_MODE)
    checkpoint_handler = None
    if ENABLE_CHECKPOINTING and FACTORS_MODE != 'auto_permutations':
        config_hash = generate_config_hash(targets_config_for_run, OPTIMIZATION_MODE, run_name_for_report)
        checkpoint_handler = CheckpointHandler(targets_config_for_run, OPTIMIZATION_MODE, run_name_for_report, config_hash)
    
    # 6. Z3ソルバーで最適化を実行
    best_model, final_value, last_analysis, elapsed_time = solver.solve(checkpoint_handler)

    # 7. 最適化結果をレポートとして出力
    reporter = SolutionReporter(problem, best_model, objective_mode=OPTIMIZATION_MODE)
    if best_model:
        reporter.generate_full_report(final_value, elapsed_time, output_dir)
    elif last_analysis and checkpoint_handler:
        reporter.report_from_checkpoint(last_analysis, final_value, output_dir)
    else:
        print("\n--- No solution found for this configuration ---")

def main():
    """プログラムのメイン実行フロー"""
    targets_config_base = get_targets_config()
    print(f"--- Factor Determination Mode: {FACTORS_MODE.upper()} ---")

    if FACTORS_MODE == 'auto':
        print("Calculating factors automatically...")
        for target in targets_config_base:
            ratio_sum = sum(target['ratios'])
            factors = find_factors_for_sum(ratio_sum, MAX_MIXER_SIZE)
            if factors is None: raise ValueError(f"Could not determine factors for {target['name']}.")
            target['factors'] = factors
        
        config_hash = generate_config_hash(targets_config_base, OPTIMIZATION_MODE, RUN_NAME)
        output_dir = get_unique_output_directory_name(config_hash, RUN_NAME)
        run_single_optimization(targets_config_base, output_dir, RUN_NAME)

    elif FACTORS_MODE == 'manual':
        print("Using manually specified factors...")
        # (検証ロジックは省略)
        config_hash = generate_config_hash(targets_config_base, OPTIMIZATION_MODE, RUN_NAME)
        output_dir = get_unique_output_directory_name(config_hash, RUN_NAME)
        run_single_optimization(targets_config_base, output_dir, RUN_NAME)

    elif FACTORS_MODE == 'auto_permutations':
        print("Preparing to test all factor permutations...")
        
        base_run_name = f"{RUN_NAME}_permutations"
        config_hash = generate_config_hash(targets_config_base, OPTIMIZATION_MODE, base_run_name)
        base_output_dir = get_unique_output_directory_name(config_hash, base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All permutation results will be saved under: '{base_output_dir}/'")

        target_perms_options = []
        for target in targets_config_base:
            ratio_sum = sum(target['ratios'])
            base_factors = find_factors_for_sum(ratio_sum, MAX_MIXER_SIZE)
            if base_factors is None: raise ValueError(f"Could not determine factors for {target['name']}.")
            perms = generate_unique_permutations(base_factors)
            target_perms_options.append(perms)
        
        all_config_combinations = list(itertools.product(*target_perms_options))
        total_runs = len(all_config_combinations)
        print(f"Found {total_runs} unique factor permutation combinations to test.")

        for i, combo in enumerate(all_config_combinations):
            print(f"\n{'='*20} Running Combination {i+1}/{total_runs} {'='*20}")
            temp_config = copy.deepcopy(targets_config_base)
            perm_name_parts = []
            for j, target in enumerate(temp_config):
                current_factors = list(combo[j])
                target['factors'] = current_factors
                perm_name_parts.append("_".join(map(str, current_factors)))
            
            perm_name = "-".join(perm_name_parts)
            run_name = f"run_{i+1}_{perm_name}"
            output_dir = os.path.join(base_output_dir, run_name)
            
            run_single_optimization(temp_config, output_dir, run_name)

    else:
        raise ValueError(f"Unknown FACTORS_MODE: '{FACTORS_MODE}'.")

if __name__ == "__main__":
    main()

