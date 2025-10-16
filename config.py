# --- 基本設定 ---
RUN_NAME = "Random_Experiment_1"
FACTOR_EXECUTION_MODE = "random"  # 'manual', 'auto', 'auto_permutations', 'random'
OPTIMIZATION_MODE = "waste"     # "waste" or "operations"
ENABLE_CHECKPOINTING = False

# --- 制約条件 ---
MAX_SHARING_VOLUME = 5
MAX_LEVEL_DIFF = None
MAX_MIXER_SIZE = 5

# --- 'random' モード用設定 ---
RANDOM_SETTINGS = {
    't_reagents': 3,
    'n_targets': 2,
    'S_ratio_sum': 18,
    'k_runs': 3,
}
# --- 'auto' / 'auto_permutations' モード用設定 ---
TARGETS_FOR_AUTO_MODE = [
    {'name': 'Target 1', 'ratios': [2, 11, 5]},
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

# --- 'manual' モード用設定 ---
TARGETS_FOR_MANUAL_MODE = [
    # {'name': 'Target 1', 'ratios': [45, 26, 64], 'factors': [3, 3, 3, 5]},
    # {'name': 'Target 2', 'ratios': [80, 26, 29], 'factors': [3, 3, 3, 5]},
    # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [3, 5, 3, 2]},
    {'name': 'Target 1', 'ratios': [2, 11, 5], 'factors': [3, 2, 3]},
    {'name': 'Target 2', 'ratios': [12, 5, 1], 'factors': [3, 2, 3]},
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