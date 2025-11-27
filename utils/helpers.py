# utils/helpers.py
import json
import hashlib
import re

def generate_config_hash(targets_config, mode, run_name):
    """
    実行設定から一意のMD5ハッシュ値を計算します。
    """
    config_str = json.dumps(targets_config, sort_keys=True)
    full_string = f"{run_name}-{config_str}-{mode}"
    hasher = hashlib.md5()
    hasher.update(full_string.encode('utf-8'))
    return hasher.hexdigest()

def create_dfmm_node_name(target_idx, level, node_idx):
    """
    MTWMのノード命名規則 (v_m{}_l{}_k{}) に従ってノード名を生成します。
    """
    return f"v_m{target_idx}_l{level}_k{node_idx}"

def parse_sharing_key(key_str_no_prefix):
    """
    共有キー文字列 ('from_' を除いた部分) を解析し、
    共有タイプ (INTRA/DFMM) とインデックス情報を返します。
    
    MTWMのキー形式:
      - Intra: l{level}k{node_idx}
      - Inter: m{target}_l{level}k{node_idx}
    """
    # Inter-sharing (starts with 'm') -> DFMM
    if key_str_no_prefix.startswith('m'):
        match = re.match(r"m(\d+)_l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            return {
                "type": "DFMM",
                "target_idx": int(match.group(1)),
                "level": int(match.group(2)),
                "node_idx": int(match.group(3)),
            }
            
    # Intra-sharing (starts with 'l') -> INTRA
    elif key_str_no_prefix.startswith('l'):
        match = re.match(r"l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            return {
                "type": "INTRA",
                "level": int(match.group(1)),
                "node_idx": int(match.group(2)),
            }

    raise ValueError(f"Unknown sharing key format: {key_str_no_prefix}")