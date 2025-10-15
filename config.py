RUN_NAME = "Experiment_Default"
# factorsの決定モードを選択
# 'auto': DFMMアルゴリズムで最適な因数を自動計算（推奨）
# 'manual': 下記の 'factors' で指定したリストを直接使用（順番も維持されます）
FACTORS_MODE = "manual"

# チェックポイント機能の有効/無効を切り替える (True: 有効, False: 無効)
ENABLE_CHECKPOINTING = False

# 最適化の目的を設定 ("waste" または "operations")
OPTIMIZATION_MODE = "waste"

# 共有液量の上限を設定 (Noneの場合は無制限)
MAX_SHARING_VOLUME = None

# 中間生成物を共有できる階層の最大差 (Noneの場合は無制限)
MAX_LEVEL_DIFF = None

# ミキサーが物理的に扱える最大容量 (論文におけるM)
MAX_MIXER_SIZE = 5 

def _get_targets_for_auto_mode():
    """
    'auto'モードで使用するターゲット設定。'ratios'のみを指定します。
    """
    return [
        {'name': 'Target 1', 'ratios': [10, 55, 25]},
        {'name': 'Target 2', 'ratios': [12, 5, 1]},
        {'name': 'Target 3', 'ratios': [5, 6, 14]},
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

def _get_targets_for_manual_mode():
    """
    'manual'モードで使用するターゲット設定。
    'ratios'と、その合計値と積が一致する'factors'を指定します。
    """
    return [
        # {'name': 'Target 1', 'ratios': [45, 26, 64], 'factors': [3, 3, 3, 5]},
        # {'name': 'Target 2', 'ratios': [80, 26, 29], 'factors': [3, 3, 3, 5]},
        {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [3, 5, 3, 2]},
        # {'name': 'Target 1', 'ratios': [2, 11, 5], 'factors': [3, 3, 2]},
        {'name': 'Target 2', 'ratios': [12, 5, 1], 'factors': [3, 3, 2]},
        # {'name': 'Target 3', 'ratios': [4, 5, 9], 'factors': [3, 3, 2]},
        # {'name': 'Target 3', 'ratios': [3, 5, 10], 'factors': [3, 3, 2]},
        # {'name': 'Target 4', 'ratios': [7, 7, 4], 'factors': [3, 3, 2]},
        # {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
        {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
        # {'name': 'Target 4', 'ratios': [6, 33, 36], 'factors': [3, 5, 5]},
        
        # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122], 'factors': [4, 4, 4, 4]},
        # {'name': 'Target 1', 'ratios': [2, 11, 5], 'factors': [3, 3, 2]},
        # {'name': 'Target 2', 'ratios': [12, 5, 1], 'factors': [3, 3, 2]},
        # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
        
        # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [5, 3, 3, 2]},
        # {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
        # {'name': 'Target 3', 'ratios': [15, 18, 42], 'factors': [3, 5, 5]}
    ]

def get_targets_config():
    """
    FACTORS_MODEに応じて、適切なターゲット設定リストを返します。
    """
    if FACTORS_MODE == 'auto':
        return _get_targets_for_auto_mode()
    elif FACTORS_MODE == 'manual':
        return _get_targets_for_manual_mode()
    else:
        raise ValueError(f"Unknown FACTORS_MODE in config.py: '{FACTORS_MODE}'")
    
