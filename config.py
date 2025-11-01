# 実行名を定義します。出力ディレクトリの名前の一部として使用されます。
RUN_NAME = ""
# 混合ツリーの階層構造（factors）を決定するモードを選択します。
# 'manual': TARGETS_FOR_MANUAL_MODE で定義された factors を手動で設定します。
# 'auto': 各ターゲットの ratios の合計値から factors を自動計算します。
# 'auto_permutations': 'auto' で計算された factors の全順列を試し、最適な階層構造を探します。
# 'random': RANDOM_SETTINGS に基づいてランダムなシナリオを複数回実行します。
#  FACTOR_EXECUTION_MODEの選択肢に 'file_load' を追加
FACTOR_EXECUTION_MODE = "file_load"
# 最適化の目的を設定します。
# "waste": 廃棄物量の最小化を目指します。
# "operations": 混合操作の総回数の最小化を目指します。
OPTIMIZATION_MODE = "waste"

# Trueに設定すると、最適化完了後に混合ツリーの可視化グラフ (PNG画像) を生成します。
# Falseに設定すると、グラフ生成をスキップし、処理時間を短縮できます。
ENABLE_VISUALIZATION = False
# ファイルから Target Configuration を読み込む場合に、そのファイル名を設定します。
# ランダム実行で生成したファイル名 (例: "manual-check_eb8386bc_1/random_configs.json") を設定すると、そこから最初のパターンを読み込みます。
CONFIG_LOAD_FILE = "random_configs.json"

# --- 制約条件 ---

# ソルバーが使用するCPUコア（ワーカー）の最大数を設定します。
# 共有マシンの場合は、 2 や 4 などの低い値に設定することを推奨します。
# None に設定すると、Or-Toolsが利用可能な全コアを使用します。
MAX_CPU_WORKERS = None

# 追加: (1回の実行（1パターン）あたりの最大計算時間（秒）)
# ソルバーが最適性の証明などでスタックしても、ここで設定した秒数が経過すると
# 自動的に打ち切られ、次のパターンの計算に進みます。
# None または 0 に設定すると、時間無制限になります。
MAX_TIME_PER_RUN_SECONDS = None

# 追加: (早期停止のための「絶対ギャップ」)
# 目的（廃棄物など）は整数であるため、 0.99 のような「1未満」の値を設定すると、
# (最良解) - (下限値) が 0.99 を下回った瞬間に停止します。
# (例: 最良解 3.0、下限値 2.01 の時点で停止)
# これにより、最適性の証明にかかる時間を短縮できます。
# None または 0 に設定すると、この機能は無効になります。
ABSOLUTE_GAP_LIMIT = 0.99

# ノード間で共有（中間液を融通）できる液量の最大値を設定します。Noneの場合は無制限です。
MAX_SHARING_VOLUME = None
# 中間液を共有する際の、供給元と供給先の階層レベル（level）の差の最大値を設定します。Noneの場合は無制限です。
MAX_LEVEL_DIFF = None
# 1回の混合操作で使用できるミキサーの最大容量（入力の合計値）を設定します。これはDFMMアルゴリズムで混合ツリーの階層を決定する際の因数の最大値にもなります。
MAX_MIXER_SIZE = 5

# --- 'random' モード用設定 ---
# FACTOR_EXECUTION_MODE が 'random' の場合にのみ使用されます。
# ランダムシナリオにおける試薬の種類数 (例: 3種類)
RANDOM_T_REAGENTS = 3
# ランダムシナリオにおけるターゲット（目標混合液）の数 (例: 3ターゲット)
RANDOM_N_TARGETS = 5
# 生成・実行するランダムシナリオの総数 (例: 100回)
RANDOM_K_RUNS = 50

# --- 混合比和の生成ルール（以下のいずれか1つが使用されます） ---
# 以下の設定は、`runners/random_runner.py` によって上から順に評価され、
# 最初に有効な（空でない）設定が1つだけ採用されます。

# オプション1: 固定シーケンス（RANDOM_N_TARGETSと要素数を一致させる必要あり）
# 18*5' の代わりに {'base_sum': 18, 'multiplier': 5} という辞書形式を使用
# これが空でないリストの場合、この設定が使用されます。
RANDOM_S_RATIO_SUM_SEQUENCE = [
    18, 32, 50
]

# オプション2: 候補リストからのランダム選択
# `RANDOM_S_RATIO_SUM_SEQUENCE` が空のリストの場合、こちらが評価されます。
# これが空でないリストの場合、ターゲットごとにこのリストからランダムに値が選ばれます。
RANDOM_S_RATIO_SUM_CANDIDATES = [
    # 18, 24, 30, 36
]

# オプション3: デフォルト値
# 上記の `SEQUENCE` と `CANDIDATES` が両方とも空のリストの場合、
# このデフォルト値が全てのターゲットで使用されます。
RANDOM_S_RATIO_SUM_DEFAULT = 12

# --- 'auto' / 'auto_permutations' モード用設定 ---
# FACTOR_EXECUTION_MODE が 'auto' または 'auto_permutations' の場合に使用されます。
# 'factors' を指定する必要はありません。自動で計算されます。
TARGETS_FOR_AUTO_MODE = [
    {'name': 'Target 1', 'ratios': [2,15,1]},
    # {'name': 'Target 1', 'ratios': [65, 10, 15]},
    # {'name': 'Target 1', 'ratios': [12,3,10]},
    # {'name': 'Target 1', 'ratios': [1,8,9]},
    # {'name': 'Target 1', 'ratios': [14, 10, 1]},
    # {'name': 'Target 2', 'ratios': [7, 8, 10]},
    # {'name': 'Target 3', 'ratios': [5, 12, 8]},
    # {'name': 'Target 1', 'ratios': [2, 11, 5]},
    # {'name': 'Target 2', 'ratios': [12, 5, 1]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14]},
    # {'name': 'Target 1', 'ratios': [45, 26, 64]},
    # {'name': 'Target 1', 'ratios': [2, 11, 5]},
    # {'name': 'Target 2', 'ratios': [80, 26, 29]},
    #
    # {'name': 'Target 3', 'ratios': [3, 5, 10]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36]},
    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122]},
    # {'name': 'Target 1', 'ratios': [15, 18, 42]}
]

# --- 'manual' モード用設定 ---
# FACTOR_EXECUTION_MODE が 'manual' の場合に使用されます。
# 'factors'（混合階層）を各ターゲットに対して手動で指定する必要があります。
# 'ratios'の合計値と'factors'の積は一致している必要があります。
TARGETS_FOR_MANUAL_MODE = [
    # {'name': 'Target 1', 'ratios': [45, 26, 64], 'factors': [3, 3, 3, 5]},
    # {'name': 'Target 2', 'ratios': [80, 26, 29], 'factors': [3, 3, 3, 5]},
    # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [3, 5, 3, 2]},
    # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [3, 5, 3, 2]},
    {'name': 'Target 1', 'ratios': [2, 11, 5], 'factors': [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [25, 60, 5], 'factors': [3, 5, 3, 2]},
    # {'name': 'Target 3', 'ratios': [4, 5, 9], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [3, 5, 10], 'factors': [3, 3, 2]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4], 'factors': [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36], 'factors': [3, 5, 5]},

    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122], 'factors': [4, 4, 4, 4]},
    # {'name': 'Target 1', 'ratios': [2, 11, 5], 'factors': [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [12, 5, 1], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [6, 5, 7], 'factors': [3, 3, 2]},

    # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [5, 3, 3, 2]},
    {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [15, 18, 42], 'factors': [3, 5, 5]}
]