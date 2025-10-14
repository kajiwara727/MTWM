# main.py (修正版)
import z3
from config import get_targets_config
from mtwm_model import MTWMProblem
from z3_solver import Z3Solver
from reporting import SolutionReporter
from checkpoint_handler import CheckpointHandler
from p_checker import PValueChecker # <-- 新しくインポート

def main():
    """
    プログラムのメイン実行フロー
    """
    # 1. 設定ファイルからターゲット混合液の情報を読み込む
    targets_config = get_targets_config()
    print("--- Configuration for this run ---")
    for target in targets_config:
        print(f"  - {target['name']}: Ratios = {target['ratios']}")
    print("-" * 35 + "\n")

    # 2. MTWM問題の構造を定義
    problem = MTWMProblem(targets_config)

    # --- ここからが追加部分 ---
    # Pの値を確認するためのチェッカーを初期化し、結果を表示
    p_checker = PValueChecker(problem)
    p_checker.display_p_values()
    # --- ここまでが追加部分 ---

    # 3. 各コンポーネント（ソルバー、チェックポイントハンドラ）を初期化
    solver = Z3Solver(problem)
    checkpoint_handler = CheckpointHandler(targets_config)

    # 4. Z3ソルバーで最適化を実行し、最良解を見つける
    best_model, final_waste, last_analysis, elapsed_time = solver.solve(checkpoint_handler)

    # 5. 最適化結果をレポートとして出力
    reporter = SolutionReporter(problem, best_model)
    if best_model:
        reporter.generate_full_report(final_waste, elapsed_time)
    elif last_analysis:
        print("\n--- No new solution found. Reporting from the last checkpoint ---")
        reporter.report_from_checkpoint(last_analysis, final_waste)
    else:
        print("\n--- No solution found ---")
        if solver.last_check_result == z3.unknown:
            print(f"Solver timed out or was interrupted ({elapsed_time:.2f} sec)")
        else: # z3.unsat
            print(f"No solution found (unsat) ({elapsed_time:.2f} sec)")
        checkpoint_handler.delete_checkpoint()

if __name__ == "__main__":
    main()