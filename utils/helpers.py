# utils/helpers.py
import json
import hashlib
import random

def generate_config_hash(targets_config, mode, run_name):
    """
    設定データ、モード、実行名から一意のハッシュを計算する。
    """
    config_str = json.dumps(targets_config, sort_keys=True)
    full_string = f"{run_name}-{config_str}-{mode}"

    hasher = hashlib.md5()
    hasher.update(full_string.encode('utf-8'))
    return hasher.hexdigest()

def generate_random_ratios(reagent_count, ratio_sum):
    """
    指定された合計値になる、指定された個数の0を含まない整数のリストを生成する。
    """
    if ratio_sum < reagent_count:
        raise ValueError("Ratio sum (S) cannot be less than the number of reagents (t).")

    dividers = sorted(random.sample(range(1, ratio_sum), reagent_count - 1))
    
    ratios = []
    last_divider = 0
    for d in dividers:
        ratios.append(d - last_divider)
        last_divider = d
    ratios.append(ratio_sum - last_divider)
    
    return ratios