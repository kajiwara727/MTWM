# mtwm_model.py (再修正版)
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
        """
        コンストラクタ

        Args:
            targets_config (list): 目標混合液の設定データ。
        """
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]['ratios']) if targets_config else 0
        
        self.p_values = self._calculate_p_values()
        self.forest = self._define_base_variables()
        self.potential_sources_map = self._precompute_potential_sources()
        self._define_sharing_variables()

    def _calculate_p_values(self):
        """各ターゲットの各レベルにおけるp値を計算する。"""
        p_forest = []
        for target in self.targets_config:
            factors = target['factors']
            num_levels = len(factors)
            p_tree = {}
            for l in range(num_levels - 1, -1, -1):
                is_leaf_level = (l == num_levels - 1)
                p_tree[l] = factors[l] if is_leaf_level else p_tree[l + 1] * factors[l]
            p_forest.append(p_tree)
        return p_forest

    def _calculate_dfmm_tree_params(self, ratios, factors):
        """DFMMアルゴリズムに基づき、各レベルに必要な混合ノード数を計算する。"""
        results = {}
        num_levels = len(factors)
        values_to_process = list(ratios)
        nodes_from_below = 0

        for l in range(num_levels - 1, -1, -1):
            factor = factors[l]
            level_remainders = [v % factor for v in values_to_process]
            level_quotients = [v // factor for v in values_to_process]
            
            total_inputs = sum(level_remainders) + nodes_from_below
            num_nodes = math.ceil(total_inputs / factor)

            results[l] = {'mixing_nodes': num_nodes}
            nodes_from_below = num_nodes
            values_to_process = level_quotients
        return results

    def _define_base_variables(self):
        """混合ノード、濃度、試薬に関する基本変数を定義する。"""
        forest = []
        for m, target in enumerate(self.targets_config):
            dfmm_params = self._calculate_dfmm_tree_params(target['ratios'], target['factors'])
            tree_data = {}
            for l in sorted(dfmm_params.keys()):
                num_nodes = dfmm_params[l]['mixing_nodes']
                level_nodes = [
                    {
                        'node_var': z3.Int(f"v_m{m}_l{l}_k{k}"),
                        'ratio_vars': [z3.Int(f"R_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)],
                        'reagent_vars': [z3.Int(f"r_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)]
                    }
                    for k in range(num_nodes)
                ]
                tree_data[l] = level_nodes
            forest.append(tree_data)
        return forest

    def _precompute_potential_sources(self):
        """
        全てのノード間の接続可能性を事前に判定し、供給元候補のマップを作成する。
        itertools.productでループのネストを削減。
        """
        source_map = {}
        all_nodes_ml = [(m, l) for m, tree in enumerate(self.forest) for l in tree]
        
        # すべての(供給先, 供給元)の組み合わせを生成
        for (m_dst, l_dst), (m_src, l_src) in itertools.product(all_nodes_ml, repeat=2):
            # --- 接続条件によるフィルタリング ---
            # 1. 供給元は供給先より深い階層か？
            if l_src <= l_dst:
                continue
            # 2. 階層差が制約を超えていないか？
            if MAX_LEVEL_DIFF is not None and l_src > l_dst + MAX_LEVEL_DIFF:
                continue
            # 3. p値の制約を満たすか？
            p_dst = self.p_values[m_dst][l_dst]
            f_dst = self.targets_config[m_dst]['factors'][l_dst]
            p_src = self.p_values[m_src][l_src]
            if (p_dst // f_dst) % p_src != 0:
                continue

            # 条件をすべて満たした場合、供給元候補として追加
            key = (m_dst, l_dst)
            if key not in source_map:
                source_map[key] = []
            source_map[key].append((m_src, l_src))
            
        return source_map

    def _create_sharing_vars_for_node(self, m_dst, l_dst, k_dst):
        """【ヘルパー】単一の供給先ノードに対する共有変数の辞書を作成する。"""
        potential_sources = self.potential_sources_map.get((m_dst, l_dst), [])
        intra_vars, inter_vars = {}, {}

        for m_src, l_src in potential_sources:
            for k_src in range(len(self.forest[m_src][l_src])):
                if m_src == m_dst:  # Intra-sharing
                    key = f"from_l{l_src}k{k_src}"
                    name = f"w_intra_m{m_dst}_from_l{l_src}k{k_src}_to_l{l_dst}k{k_dst}"
                    intra_vars[key] = z3.Int(name)
                else:  # Inter-sharing
                    key = f"from_m{m_src}_l{l_src}k{k_src}"
                    name = f"w_inter_from_m{m_src}l{l_src}k{k_src}_to_m{m_dst}l{l_dst}k{k_dst}"
                    inter_vars[key] = z3.Int(name)
        return intra_vars, inter_vars

    def _define_sharing_variables(self):
        """
        ヘルパー関数を使い、全てのノードに対して共有変数を定義・割り当てる。
        ループのネストが浅くなり、見通しが改善。
        """
        for m_dst, tree_dst in enumerate(self.forest):
            for l_dst, nodes_dst in tree_dst.items():
                for k_dst, node in enumerate(nodes_dst):
                    intra, inter = self._create_sharing_vars_for_node(m_dst, l_dst, k_dst)
                    node['intra_sharing_vars'] = intra
                    node['inter_sharing_vars'] = inter