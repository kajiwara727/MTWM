# core/algorithm/dfmm.py
import math
import itertools
from functools import reduce
import operator

def find_factors_for_sum(ratio_sum, max_factor):
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
            return None
    return sorted(factors, reverse=True)

def generate_unique_permutations(factors):
    if not factors: return [()]
    return list(set(itertools.permutations(factors)))

def build_dfmm_forest(targets_config):
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
    p_forest = []
    for m, tree_structure in enumerate(forest_structure):
        factors, memo, p_tree = targets_config[m]['factors'], {}, {}
        def prod(iterable): return reduce(operator.mul, iterable, 1)
        def get_p_for_node(node_id):
            if node_id in memo: return memo[node_id]
            level, k = node_id
            children = tree_structure.get(node_id, {}).get('children', [])
            if not children: p = prod(factors[level:])
            else: p = max(get_p_for_node(child_id) for child_id in children) * factors[level]
            memo[node_id] = p
            return p
        for node_id in tree_structure: p_tree[node_id] = get_p_for_node(node_id)
        p_forest.append(p_tree)
    return p_forest

def apply_auto_factors(targets_config, max_mixer_size):
    """[NEW] StandardRunnerから移動したロジック"""
    for target in targets_config:
        factors = find_factors_for_sum(sum(target['ratios']), max_mixer_size)
        if factors is None:
            raise ValueError(f"Could not determine factors for {target['name']}.")
        target['factors'] = factors
    return targets_config