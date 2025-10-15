# mtwm_model.py (修正版)
import math
import z3
import itertools
from config import MAX_LEVEL_DIFF

class MTWMProblem:
    """
    MTWM (Multi-Target Waste Minimization) 問題の構造を定義、管理するクラス。
    変数の定義と、それらの関係性をカプセル化する。
    """
    def __init__(self, targets_config):
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]['ratios']) if targets_config else 0
        self.tree_structures = self._build_full_tree_structures()
        self.p_values = self._calculate_p_values_per_node()
        self.forest = self._define_base_variables()
        self.potential_sources_map = self._precompute_potential_sources()
        self._define_sharing_variables()

    def _build_full_tree_structures(self):
        """DFMMに基づき、親子関係を含む詳細なツリー構造のフォレストを構築する。"""
        forest_structure = []
        for target in self.targets_config:
            ratios = target['ratios']
            factors = target['factors']
            num_levels = len(factors)
            
            tree_nodes = {}
            values_to_process = list(ratios)
            nodes_from_below_ids = []

            for l in range(num_levels - 1, -1, -1):
                factor = factors[l]
                level_remainders = [v % factor for v in values_to_process]
                level_quotients = [v // factor for v in values_to_process]
                
                total_reagent_inputs = sum(level_remainders)
                num_nodes_from_below = len(nodes_from_below_ids)
                total_inputs = total_reagent_inputs + num_nodes_from_below
                num_nodes_at_this_level = math.ceil(total_inputs / factor) if total_inputs > 0 else 0

                current_level_node_ids = [(l, k) for k in range(num_nodes_at_this_level)]
                tree_nodes.update({node_id: {'children': []} for node_id in current_level_node_ids})
                
                # 子ノードを親ノードに割り当てる (シンプルなロジック)
                if num_nodes_at_this_level > 0:
                    parent_idx = 0
                    for child_id in nodes_from_below_ids:
                        tree_nodes[current_level_node_ids[parent_idx]]['children'].append(child_id)
                        parent_idx = (parent_idx + 1) % num_nodes_at_this_level
                
                nodes_from_below_ids = current_level_node_ids
                values_to_process = level_quotients
            
            forest_structure.append(tree_nodes)
        return forest_structure

    def _calculate_p_values_per_node(self):
        """構築されたツリー構造に基づき、ノードごとにPの値を再帰的に計算する。"""
        p_forest = []
        for m, tree_structure in enumerate(self.tree_structures):
            factors = self.targets_config[m]['factors']
            memo = {}
            p_tree = {}

            def get_p_for_node(node_id):
                if node_id in memo:
                    return memo[node_id]

                level, k = node_id
                children = tree_structure.get(node_id, {}).get('children', [])

                if not children:
                    p = factors[level]
                else:
                    max_child_p = max(get_p_for_node(child_id) for child_id in children) if children else 1
                    p = max_child_p * factors[level]
                
                memo[node_id] = p
                return p

            for node_id in tree_structure:
                p_tree[node_id] = get_p_for_node(node_id)
            
            p_forest.append(p_tree)
        return p_forest

    def _define_base_variables(self):
        """混合ノード、濃度、試薬に関する基本変数を定義する。"""
        forest = []
        for m, tree_structure in enumerate(self.tree_structures):
            tree_data = {}
            levels = sorted({l for l, k in tree_structure.keys()})
            for l in levels:
                nodes_at_level = sorted([k for l_node, k in tree_structure.keys() if l_node == l])
                level_nodes = [
                    {
                        'node_var': z3.Int(f"v_m{m}_l{l}_k{k}"),
                        'ratio_vars': [z3.Int(f"R_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)],
                        'reagent_vars': [z3.Int(f"r_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)]
                    }
                    for k in nodes_at_level
                ]
                tree_data[l] = level_nodes
            forest.append(tree_data)
        return forest
    
    def _precompute_potential_sources(self):
        """全てのノード間の接続可能性を事前に判定し、供給元候補のマップを作成する。"""
        source_map = {}
        all_nodes = [(m, l, k) for m, tree in enumerate(self.forest) for l, nodes in tree.items() for k in range(len(nodes))]
        
        for (m_dst, l_dst, k_dst), (m_src, l_src, k_src) in itertools.product(all_nodes, repeat=2):
            if l_src <= l_dst: continue
            if MAX_LEVEL_DIFF is not None and l_src > l_dst + MAX_LEVEL_DIFF: continue
            
            # Pの値をノードごとに取得
            p_dst = self.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.targets_config[m_dst]['factors'][l_dst]
            p_src = self.p_values[m_src][(l_src, k_src)]
            if (p_dst // f_dst) % p_src != 0: continue

            key = (m_dst, l_dst, k_dst)
            if key not in source_map: source_map[key] = []
            source_map[key].append((m_src, l_src, k_src))
            
        return source_map

    def _create_sharing_vars_for_node(self, m_dst, l_dst, k_dst):
        """単一の供給先ノードに対する共有変数の辞書を作成する。"""
        potential_sources = self.potential_sources_map.get((m_dst, l_dst, k_dst), [])
        intra_vars, inter_vars = {}, {}

        for m_src, l_src, k_src in potential_sources:
            if m_src == m_dst:
                key = f"from_l{l_src}k{k_src}"
                name = f"w_intra_m{m_dst}_from_l{l_src}k{k_src}_to_l{l_dst}k{k_dst}"
                intra_vars[key] = z3.Int(name)
            else:
                key = f"from_m{m_src}_l{l_src}k{k_src}"
                name = f"w_inter_from_m{m_src}l{l_src}k{k_src}_to_m{m_dst}l{l_dst}k{k_dst}"
                inter_vars[key] = z3.Int(name)
        return intra_vars, inter_vars

    def _define_sharing_variables(self):
        """全てのノードに対して共有変数を定義・割り当てる。"""
        for m_dst, tree_dst in enumerate(self.forest):
            for l_dst, nodes_dst in tree_dst.items():
                for k_dst, node in enumerate(nodes_dst):
                    intra, inter = self._create_sharing_vars_for_node(m_dst, l_dst, k_dst)
                    node['intra_sharing_vars'] = intra
                    node['inter_sharing_vars'] = inter