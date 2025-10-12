# main.py
import z3
from config import get_targets_config
from mtwm_model import MTWMProblem
from z3_solver import Z3Solver
from reporting import SolutionReporter
from checkpoint_handler import CheckpointHandler

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

    # 2. 各コンポーネント（問題定義、ソルバー、チェックポイントハンドラ）を初期化
    problem = MTWMProblem(targets_config)
    solver = Z3Solver(problem)
    checkpoint_handler = CheckpointHandler(targets_config)

    # 3. Z3ソルバーで最適化を実行し、最良解を見つける
    best_model, final_waste, last_analysis, elapsed_time = solver.solve(checkpoint_handler)

    # 4. 最適化結果をレポートとして出力
    reporter = SolutionReporter(problem, best_model)
    if best_model:
        # 新しい解が見つかった場合
        reporter.generate_full_report(final_waste, elapsed_time)
    elif last_analysis:
        # 新しい解は見つからず、チェックポイントの解が最良の場合
        print("\n--- No new solution found. Reporting from the last checkpoint ---")
        reporter.report_from_checkpoint(last_analysis, final_waste)
    else:
        # 解が見つからなかった場合
        print("\n--- No solution found ---")
        if solver.last_check_result == z3.unknown:
            print(f"Solver timed out or was interrupted ({elapsed_time:.2f} sec)")
        else: # z3.unsat
            print(f"No solution found (unsat) ({elapsed_time:.2f} sec)")
        checkpoint_handler.delete_checkpoint()

if __name__ == "__main__":
    main()