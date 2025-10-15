# utils.py
import json
import hashlib

def generate_config_hash(targets_config, mode, run_name):
    """
    設定データ、モード、実行名から一意のハッシュを計算する。
    フォルダ名とチェックポイントファイル名でハッシュ元を統一するために使用します。

    Args:
        targets_config (list): ターゲット設定のリスト。
        mode (str): 最適化モード ('waste' or 'operations')。
        run_name (str): config.pyで設定された実行名。

    Returns:
        str: 計算されたMD5ハッシュ文字列。
    """
    config_str = json.dumps(targets_config, sort_keys=True)
    # 実行名、設定内容、最適化モードを結合してハッシュ化する
    full_string = f"{run_name}-{config_str}-{mode}"

    hasher = hashlib.md5()
    hasher.update(full_string.encode('utf-8'))
    return hasher.hexdigest()
