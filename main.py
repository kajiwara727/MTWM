# main.py
import os
import z3
from config import get_targets_config, OPTIMIZATION_MODE, MAX_SHARING_VOLUME, MAX_LEVEL_DIFF, ENABLE_CHECKPOINTING
from mtwm_model import MTWMProblem
from z3_solver import Z3Solver
from reporting import SolutionReporter
from checkpoint_handler import CheckpointHandler
from pre_run_analyzer import PreRunAnalyzer # 修正: 新しいアナライザをインポート

def get_unique_output_directory_name(targets_config):
    """設定に基づいて一意の出力ディレクトリ名を生成する"""
    base_name = f"({')-('.join(['_'.join(map(str, t['ratios'])) for t in targets_config])})"
    mode_suffix = f"_mode-{OPTIMIZATION_MODE}"
    vol_suffix = f"_vol{MAX_SHARING_VOLUME or 'None'}"
    lvl_suffix = f"_lvl{MAX_LEVEL_DIFF or 'None'}"
    full_base_name = base_name + mode_suffix + vol_suffix + lvl_suffix
    
    counter = 1
    output_dir = full_base_name
    while os.path.isdir(output_dir):
        output_dir = f"{full_base_name}_{counter}"
        counter += 1
    return output_dir

def main():
    """プログラムのメイン実行フロー"""
    # 1. 設定を読み込む
    targets_config = get_targets_config()
    print("--- Configuration for this run ---")
    for target in targets_config:
        print(f"  - {target['name']}: Ratios = {target['ratios']}")
    print(f"Optimization Mode: {OPTIMIZATION_MODE.upper()}")
    print(f"Checkpointing Enabled: {ENABLE_CHECKPOINTING}")
    print("-" * 35 + "\n")

    # 2. MTWM問題の構造を定義
    problem = MTWMProblem(targets_config)

    # 3. 今回の実行結果を保存するディレクトリを先に決定・作成する
    output_dir = get_unique_output_directory_name(targets_config)
    os.makedirs(output_dir, exist_ok=True)
    print(f"All outputs will be saved to: '{output_dir}/'")

    # --- ▼▼▼ ここが修正点です ▼▼▼ ---
    # 4. 事前チェックを実行し、結果を単一のレポートファイルに保存
    analyzer = PreRunAnalyzer(problem)
    analyzer.generate_report(output_dir)
    # --- ▲▲▲ ここまでが修正点です ▲▲▲ ---

    # 5. 各コンポーネントを初期化
    solver = Z3Solver(problem, objective_mode=OPTIMIZATION_MODE)
    checkpoint_handler = None
    if ENABLE_CHECKPOINTING:
        checkpoint_handler = CheckpointHandler(targets_config, mode=OPTIMIZATION_MODE)

    # 6. Z3ソルバーで最適化を実行
    best_model, final_value, last_analysis, elapsed_time = solver.solve(checkpoint_handler)

    # 7. 最適化結果をレポートとして出力
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