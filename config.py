# 実行名を定義します。
RUN_NAME = "Test"

# 実行モード: 'manual', 'auto', 'auto_permutations', 'random', 'file_load'
FACTOR_EXECUTION_MODE = "auto"

# 最適化の目的: "waste", "operations"
OPTIMIZATION_MODE = "waste"

# --- 出力設定 ---
ENABLE_VISUALIZATION = True
CONFIG_LOAD_FILE = "random_configs.json"

# --- 制約条件 ---
MAX_CPU_WORKERS = 16
MAX_TIME_PER_RUN_SECONDS = None
ABSOLUTE_GAP_LIMIT = 0.99
MAX_SHARING_VOLUME = None
MAX_LEVEL_DIFF = None
MAX_MIXER_SIZE = 5

# [NEW] 役割ベースのプルーニング設定
ENABLE_ROLE_BASED_PRUNING = True

# [NEW] Inter-Sharing（他ターゲットへの供給）の接続モード
# 'all' : 全ての他ターゲットへ接続（従来・高コスト）
# 'ring': 次のターゲット番号へ一方向のみ接続 (0->1->2->0) [推奨・高速]
INTER_SHARING_MODE = 'ring'

# --- 'random' モード用設定 ---
RANDOM_N_TARGETS = 3
RANDOM_T_REAGENTS = 3
RANDOM_K_RUNS = 10
RANDOM_S_RATIO_SUM_DEFAULT = 18
RANDOM_S_RATIO_SUM_SEQUENCE = []
RANDOM_S_RATIO_SUM_CANDIDATES = []

# --- 混合比和の生成ルール（以下のいずれか1つが使用されます） ---
# 以下の設定は、`runners/random_runner.py` によって上から順に評価され、
# 最初に有効な（空でない）設定が1つだけ採用されます。

# オプション1: 固定シーケンス（RANDOM_N_TARGETSと要素数を一致させる必要あり）
# 18*5' の代わりに {'base_sum': 18, 'multiplier': 5} という辞書形式を使用
# これが空でないリストの場合、この設定が使用されます。
RANDOM_S_RATIO_SUM_SEQUENCE = [
    # 18, 32, 50
]

# オプション2: 候補リストからのランダム選択
# `RANDOM_S_RATIO_SUM_SEQUENCE` が空のリストの場合、こちらが評価されます。
# これが空でないリストの場合、ターゲットごとにこのリストからランダムに値が選ばれます。
RANDOM_S_RATIO_SUM_CANDIDATES = [
    # 18, 24, 30, 36
]
