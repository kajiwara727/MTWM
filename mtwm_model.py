# mtwm_model.py
import math
import z3
# configファイルからMAX_LEVEL_DIFFをインポート
from config import MAX_LEVEL_DIFF

class MTWMProblem:
    """
    MTWM (Multi-Target Waste Minimization) 問題の構造を定義するクラス。
    """
    # クラス変数としての定義を削除

    def __init__(self, targets_config):
        """
        コンストラクタ

        Args:
            targets_config (list): 目標混合液の設定データ。
        """
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]['ratios'])
        self.p_values = self._calculate_p_values()
        self.forest = self._define_mtwm_variables()

    def _calculate_p_values(self):
        """各ターゲットの P 値を計算"""
        p_forest = []
        for target in self.targets_config:
            factors = target['factors']
            num_levels = len(factors)
            p_tree = {}
            for l in range(num_levels - 1, -1, -1):
                p_tree[l] = factors[l] if l == num_levels - 1 else p_tree[l + 1] * factors[l]
            p_forest.append(p_tree)
        return p_forest

    def _define_mtwm_variables(self):
        """MTWM 変数を定義"""
        forest = self._define_base_variables()
        self._define_intra_sharing_variables(forest)
        self._define_inter_sharing_variables(forest)
        return forest

    def _calculate_dfmm_tree_params(self, ratios, factors):
        """DFMM 木構造のパラメータを計算"""
        results = {}
        num_levels = len(factors)
        values_to_process = list(ratios)
        nodes_from_below = 0

        for l in range(num_levels - 1, -1, -1):
            factor = factors[l]
            level_remainders = [v % factor for v in values_to_process]
            level_quotients = [v // factor for v in values_to_process]
            sum_remainders = sum(level_remainders)
            total_inputs = sum_remainders + nodes_from_below
            num_nodes = math.ceil(total_inputs / factor)

            results[l] = {'mixing_nodes': num_nodes}
            nodes_from_below = num_nodes
            values_to_process = level_quotients
        return results

    def _define_base_variables(self):
        """基本ノード変数の定義"""
        forest = []
        for m, target in enumerate(self.targets_config):
            dfmm = self._calculate_dfmm_tree_params(target['ratios'], target['factors'])
            tree_data = {}
            for l in sorted(dfmm.keys()):
                num_nodes = dfmm[l]['mixing_nodes']
                level_nodes = []
                for k in range(num_nodes):
                    node = {
                        'node_var': z3.Int(f"v_m{m}_l{l}_k{k}"),
                        'ratio_vars': [z3.Int(f"R_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)],
                        'reagent_vars': [z3.Int(f"r_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)]
                    }
                    level_nodes.append(node)
                tree_data[l] = level_nodes
            forest.append(tree_data)
        return forest

    def _define_intra_sharing_variables(self, forest):
        """同一ターゲット内の共有変数を定義"""
        for m, tree in enumerate(forest):
            for l_dst in sorted(tree.keys()):
                p_dst = self.p_values[m][l_dst]
                f_dst = self.targets_config[m]['factors'][l_dst]
                for k_dst in range(len(tree[l_dst])):
                    incoming = {}
                    for l_src in sorted(tree.keys()):
                        # 供給元(src)は供給先(dst)より深い階層でなければならない
                        if l_src <= l_dst:
                            continue
                        # MAX_LEVEL_DIFFが設定されている場合、階層差がそれを超えるものは除外
                        if MAX_LEVEL_DIFF is not None and l_src > l_dst + MAX_LEVEL_DIFF:
                            continue
                        
                        p_src = self.p_values[m][l_src]
                        if (p_dst // f_dst) % p_src == 0:
                            for k_src in range(len(tree[l_src])):
                                var_name = f"w_intra_m{m}_from_l{l_src}k{k_src}_to_l{l_dst}k{k_dst}"
                                incoming[f"from_l{l_src}k{k_src}"] = z3.Int(var_name)
                    tree[l_dst][k_dst]['intra_sharing_vars'] = incoming

    def _define_inter_sharing_variables(self, forest):
        """異なるターゲット間の共有変数を定義"""
        for m_dst, tree_dst in enumerate(forest):
            for l_dst in tree_dst:
                p_dst = self.p_values[m_dst][l_dst]
                f_dst = self.targets_config[m_dst]['factors'][l_dst]
                for k_dst in range(len(tree_dst[l_dst])):
                    incoming = {}
                    for m_src, tree_src in enumerate(forest):
                        if m_src == m_dst:
                            continue
                        for l_src in sorted(tree_src.keys()):
                            # 供給元(src)は供給先(dst)より深い階層でなければならない
                            if l_src <= l_dst:
                                continue
                            # MAX_LEVEL_DIFFが設定されている場合、階層差がそれを超えるものは除外
                            if MAX_LEVEL_DIFF is not None and l_src > l_dst + MAX_LEVEL_DIFF:
                                continue

                            p_src = self.p_values[m_src][l_src]
                            if (p_dst // f_dst) % p_src == 0:
                                for k_src in range(len(tree_src[l_src])):
                                    var_name = f"w_inter_from_m{m_src}l{l_src}k{k_src}_to_m{m_dst}l{l_dst}k{k_dst}"
                                    incoming[f"from_m{m_src}_l{l_src}k{k_src}"] = z3.Int(var_name)
                    tree_dst[l_dst][k_dst]['inter_sharing_vars'] = incoming