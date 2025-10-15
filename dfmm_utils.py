# dfmm_utils.py
import math
from collections import defaultdict
import itertools

def find_factors_for_sum(ratio_sum, max_factor):
    """DFMMに基づき、比率の合計値をmax_factor以下の因数に分解する。"""
    if ratio_sum <= 1: return []
    n, factors = ratio_sum, []
    while n > 1:
        found_divisor = False
        for d in range(max_factor, 1, -1):
            if n % d == 0:
                factors.append(d)
                n //= d
                found_divisor = True
                break
        if not found_divisor:
            print(f"Error: Could not find factors for sum {ratio_sum}. Failed at {n}.")
            return None
    return sorted(factors, reverse=True)

# --- ▼▼▼ ここからが修正点です (新しい関数) ▼▼▼ ---
def generate_unique_permutations(factors):
    """
    因数リストから、重複を考慮したユニークな順列をすべて生成する。
    例: [5, 3, 3] -> ([5, 3, 3], [3, 5, 3], [3, 3, 5])
    """
    if not factors:
        return [()]
    # setで重複する順列を除外してからリストに変換
    return list(set(itertools.permutations(factors)))
# --- ▲▲▲ ここまでが修正点です ▲▲▲ ---

def build_dfmm_forest(targets_config):
    """DFMMアルゴリズムに基づき、親子関係を含むツリー構造のフォレストを構築する。"""
    forest_structure = []
    for target in targets_config:
        ratios, factors = target['ratios'], target['factors']
        num_levels = len(factors)
        
        tree_nodes = {}
        values_to_process = list(ratios)
        nodes_from_below_ids = []

        for l in range(num_levels - 1, -1, -1):
            factor = factors[l]
            level_remainders = [v % factor for v in values_to_process]
            level_quotients = [v // factor for v in values_to_process]
            
            total_inputs = sum(level_remainders) + len(nodes_from_below_ids)
            num_nodes_at_level = math.ceil(total_inputs / factor) if total_inputs > 0 else 0
            current_level_node_ids = [(l, k) for k in range(num_nodes_at_level)]
            
            for node_id in current_level_node_ids:
                tree_nodes[node_id] = {'children': []}
            
            # 子ノードを親ノードにラウンドロビンで割り当てる
            if num_nodes_at_level > 0:
                parent_idx = 0
                for child_id in nodes_from_below_ids:
                    parent_node_id = current_level_node_ids[parent_idx]
                    tree_nodes[parent_node_id]['children'].append(child_id)
                    parent_idx = (parent_idx + 1) % num_nodes_at_level
            
            nodes_from_below_ids = current_level_node_ids
            values_to_process = level_quotients
        
        forest_structure.append(tree_nodes)
    return forest_structure

def calculate_p_values_from_structure(forest_structure, targets_config):
    """構築されたツリー構造に基づき、ノードごとにPの値を再帰的に計算する。"""
    p_forest = []
    for m, tree_structure in enumerate(forest_structure):
        factors, memo, p_tree = targets_config[m]['factors'], {}, {}

        def get_p_for_node(node_id):
            if node_id in memo: return memo[node_id]
            level, k = node_id
            children = tree_structure.get(node_id, {}).get('children', [])
            
            if not children:
                p = factors[level]
            else:
                max_child_p = max(get_p_for_node(child_id) for child_id in children)
                p = max_child_p * factors[level]
            
            memo[node_id] = p
            return p

        for node_id in tree_structure:
            p_tree[node_id] = get_p_for_node(node_id)
        p_forest.append(p_tree)
    return p_forest
