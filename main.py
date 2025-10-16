# main.py
from config import FACTOR_EXECUTION_MODE
from runners import standard_runner, random_runner, permutation_runner
from utils.config_loader import Config

def main():
    """
    アプリケーションのエントリーポイント。
    設定に基づき、適切な実行戦略（ランナー）を選択して処理を開始する。
    """
    print(f"--- Factor Determination Mode: {FACTOR_EXECUTION_MODE.upper()} ---")

    # 設定モードに応じて適切なランナーを選択
    if FACTOR_EXECUTION_MODE in ['auto', 'manual']:
        runner = standard_runner.StandardRunner(Config)
    elif FACTOR_EXECUTION_MODE == 'random':
        runner = random_runner.RandomRunner(Config)
    elif FACTOR_EXECUTION_MODE == 'auto_permutations':
        runner = permutation_runner.PermutationRunner(Config)
    else:
        raise ValueError(f"Unknown FACTOR_EXECUTION_MODE: '{FACTOR_EXECUTION_MODE}'.")

    # 選択されたランナーで処理を実行
    runner.run()

if __name__ == "__main__":
    main()