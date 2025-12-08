import itertools
from utils.config_loader import Config

class MTWMProblem:
    def __init__(self, targets_config, tree_structures, p_values):
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]['ratios']) if targets_config else 0
        self.tree_structures = tree_structures
        self.p_values = p_values
        self.forest = self._define_base_variables()
        self.potential_sources_map = self._precompute_potential_sources()
        self._define_sharing_variables()

    def _define_base_variables(self):
        forest = []
        for m, tree_structure in enumerate(self.tree_structures):
            tree_data = {}
            levels = sorted({l for l, k in tree_structure.keys()})
            for l in levels:
                nodes_at_level = sorted([k for l_node, k in tree_structure.keys() if l_node == l])
                level_nodes = [
                    {
                        'node_name': f"v_m{m}_l{l}_k{k}",
                        'ratio_vars': [f"R_m{m}_l{l}_k{k}_t{t}" for t in range(self.num_reagents)],
                        'reagent_vars': [f"r_m{m}_l{l}_k{k}_t{t}" for t in range(self.num_reagents)],
                        'total_input_var_name': f"TotalInput_m{m}_l{l}_k{k}",
                        'waste_var_name': f"waste_m{m}_l{l}_k{k}" if l > 0 else None
                    }
                    for k in nodes_at_level
                ]
                tree_data[l] = level_nodes
            forest.append(tree_data)
        return forest

    def _precompute_potential_sources(self):
        source_map = {}
        all_nodes = [(m, l, k) for m, tree in enumerate(self.forest) for l, nodes in tree.items() for k in range(len(nodes))]

        for (m_dst, l_dst, k_dst), (m_src, l_src, k_src) in itertools.product(all_nodes, repeat=2):
            # 1. 物理的制約チェック
            if l_src <= l_dst: continue
            if Config.MAX_LEVEL_DIFF is not None and l_src > l_dst + Config.MAX_LEVEL_DIFF: continue

            # 2. 濃度整合性チェック
            p_dst = self.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.targets_config[m_dst]['factors'][l_dst]
            p_src = self.p_values[m_src][(l_src, k_src)]
            
            if (p_dst // f_dst) % p_src != 0: continue

            # 3. 親子関係（Default Edge）の確認
            # 親子関係にある場合は、設定に関わらず必ず接続を許可する
            is_default_edge = False
            if m_src == m_dst:
                dst_node_data = self.tree_structures[m_dst].get((l_dst, k_dst))
                if dst_node_data and (l_src, k_src) in dst_node_data['children']:
                    is_default_edge = True

            # -----------------------------------------------------------------
            # [NEW] 役割ベースの接続フィルタリング (Role-Based Pruning)
            # -----------------------------------------------------------------
            if Config.ENABLE_ROLE_BASED_PRUNING and not is_default_edge:
                is_allowed = False
                
                # --- A. 同じターゲット内 (Intra) ---
                # ここは従来通り Role (0, 1) で厳しく間引く
                if m_src == m_dst:
                    role_id = (k_src + m_src) % 3
                    
                    # Role 0: 近距離サポーター
                    if role_id == 0:
                        if (l_src - l_dst) == 1: is_allowed = True
                    # Role 1: 遠距離サポーター
                    elif role_id == 1:
                        if (l_src - l_dst) > 1: is_allowed = True
                    # Role 2 は Intra に貢献しない (Export専用)

                # --- B. 異なるターゲット間 (Inter) ---
                else:
                    mode = Config.INTER_SHARING_MODE
                    
                    if mode == 'ring':
                        # 【リングモード】(Role制限なし)
                        # 次のターゲットであれば、どのノードからでも接続を許可する
                        # これにより「最後→最初」の接続漏れを防ぐ
                        num_targets = len(self.targets_config)
                        if m_dst == (m_src + 1) % num_targets:
                            is_allowed = True
                            
                    elif mode == 'linear':
                        # 【リニアモード】(Role制限なし)
                        # 次のターゲットであれば許可
                        if m_dst == m_src + 1:
                            is_allowed = True
                            
                    else:
                        # 【Allモード】(Role制限あり)
                        # 全結合だと多すぎるので、Role 2 (輸出担当) だけに限定する
                        role_id = (k_src + m_src) % 3
                        if role_id == 2:
                            is_allowed = True

                # 許可されなかったエッジはスキップ
                if not is_allowed:
                    continue
            # -----------------------------------------------------------------

            # マップに登録
            key = (m_dst, l_dst, k_dst)
            if key not in source_map: source_map[key] = []
            source_map[key].append((m_src, l_src, k_src))
            
        return source_map

    def _create_sharing_vars_for_node(self, m_dst, l_dst, k_dst):
        potential_sources = self.potential_sources_map.get((m_dst, l_dst, k_dst), [])
        intra_vars, inter_vars = {}, {}
        for m_src, l_src, k_src in potential_sources:
            if m_src == m_dst:
                key = f"from_l{l_src}k{k_src}"
                name = f"w_intra_m{m_dst}_from_l{l_src}k{k_src}_to_l{l_dst}k{k_dst}"
                intra_vars[key] = name
            else:
                key = f"from_m{m_src}_l{l_src}k{k_src}"
                name = f"w_inter_from_m{m_src}l{l_src}k{k_src}_to_m{m_dst}l{l_dst}k{k_dst}"
                inter_vars[key] = name
        return intra_vars, inter_vars

    def _define_sharing_variables(self):
        for m_dst, tree_dst in enumerate(self.forest):
            for l_dst, nodes_dst in tree_dst.items():
                for k_dst, node in enumerate(nodes_dst):
                    intra, inter = self._create_sharing_vars_for_node(m_dst, l_dst, k_dst)
                    node['intra_sharing_vars'] = intra
                    node['inter_sharing_vars'] = inter
