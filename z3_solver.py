# z3_solver.py
import z3
import time
from reporting import SolutionReporter
from config import MAX_SHARING_VOLUME  # configからインポート

class Z3Solver:
    # クラス変数としての定義を削除
    
    def __init__(self, problem):
        self.problem = problem
        self.opt = z3.Optimize()
        self.last_check_result = None
        self._set_all_constraints()
        self.total_waste_var = self._set_objective_function()

    def solve(self, checkpoint_handler):
        """
        最適化問題をインクリメンタルに解き、最良のモデルを返す。
        """
        last_best_waste, last_analysis = checkpoint_handler.load_checkpoint()
        if last_best_waste is not None:
            self.opt.add(self.total_waste_var < last_best_waste)

        print("\n--- 4. Solving the optimization problem (press Ctrl+C to interrupt and save) ---")
        best_model = None
        min_waste_val = last_best_waste
        start_time = time.time()
        
        # Z3の詳細ログを有効にする
        z3.set_param('verbose', 1)
        
        try:
            while self.check() == z3.sat:
                current_model = self.get_model()
                current_waste = current_model.eval(self.total_waste_var).as_long()
                print(f"Found a new, better solution with waste: {current_waste}")
                
                min_waste_val = current_waste
                best_model = current_model
                
                reporter = SolutionReporter(self.problem, best_model)
                analysis = reporter.analyze_solution()
                checkpoint_handler.save_checkpoint(analysis, min_waste_val, time.time() - start_time)
                
                if min_waste_val == 0:
                    print("Found optimal solution with zero waste.")
                    break
                self.opt.add(self.total_waste_var < min_waste_val)

        except KeyboardInterrupt:
            print("\nOptimization interrupted by user. Reporting the best solution found so far.")
        
        finally:
            # 処理の終了後（中断含む）にZ3の詳細ログを無効にする
            z3.set_param('verbose', 0)

        elapsed_time = time.time() - start_time
        print("--- Z3 Solver Finished ---")
        
        return best_model, min_waste_val, last_analysis, elapsed_time

    def check(self):
        self.last_check_result = self.opt.check()
        return self.last_check_result

    def get_model(self):
        return self.opt.model()

    # --- 以下、制約設定メソッド ---

    def _set_all_constraints(self):
        """モデルに必要なすべての制約を追加する。"""
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_range_constraints()
        self._set_symmetry_breaking_constraints()
        self._set_activity_constraints()

    def _set_initial_constraints(self):
        """制約: 最終生成物（ルートノード）の濃度はターゲットの比率と一致しなければならない。"""
        for m, target in enumerate(self.problem.targets_config):
            root = self.problem.forest[m][0][0]
            for t in range(self.problem.num_reagents):
                self.opt.add(root['ratio_vars'][t] == target['ratios'][t])

    def _set_conservation_constraints(self):
        """制約: 各ノードで生成された混合液の総量は、そこから出ていく量の合計以上でなければならない（物質量保存）。"""
        for m_src, tree_src in enumerate(self.problem.forest):
            for l_src, level_src in tree_src.items():
                for k_src, node in enumerate(level_src):
                    inputs = (node.get('reagent_vars', []) +
                              list(node.get('intra_sharing_vars', {}).values()) +
                              list(node.get('inter_sharing_vars', {}).values()))
                    total_produced = z3.Sum(inputs)
                    
                    outgoing = self._get_outgoing_vars(m_src, l_src, k_src)
                    total_used = z3.Sum(outgoing)
                    self.opt.add(total_used <= total_produced)

    def _set_concentration_constraints(self):
        """制約: 混合後の濃度は、投入された材料の濃度の加重平均と一致しなければならない（濃度保存）。"""
        for m_dst, tree_dst in enumerate(self.problem.forest):
            for l_dst in sorted(tree_dst.keys()):
                for k_dst, node in enumerate(tree_dst[l_dst]):
                    f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
                    p_dst = self.problem.p_values[m_dst][l_dst]
                    for t in range(self.problem.num_reagents):
                        lhs = f_dst * node['ratio_vars'][t]
                        rhs_terms = [p_dst * node['reagent_vars'][t]]
                        
                        # Intra share
                        for key, w_var in node.get('intra_sharing_vars', {}).items():
                            l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                            r_src = self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t]
                            p_src = self.problem.p_values[m_dst][l_src]
                            rhs_terms.append(r_src * w_var * (p_dst // p_src))
                            
                        # Inter share
                        for key, w_var in node.get('inter_sharing_vars', {}).items():
                            m_src = int(key.split("_l")[0].replace("from_m", ""))
                            l_src, k_src = map(int, key.split("_l")[1].split("k"))
                            r_src = self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t]
                            p_src = self.problem.p_values[m_src][l_src]
                            rhs_terms.append(r_src * w_var * (p_dst // p_src))
                            
                        self.opt.add(lhs == z3.Sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """比率変数の和 = p 値"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                p_val = self.problem.p_values[m][l]
                for node in nodes:
                    self.opt.add(z3.Sum(node['ratio_vars']) == p_val)

    def _set_leaf_node_constraints(self):
        """リーフノードでは ratio = reagent"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                if self.problem.p_values[m][l] == self.problem.targets_config[m]['factors'][l]:
                    for node in nodes:
                        for t in range(self.problem.num_reagents):
                            self.opt.add(node['ratio_vars'][t] == node['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        """Mixer Capacity (root=F, others=F or 0)"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                f_value = self.problem.targets_config[m]['factors'][l]
                for node in nodes:
                    inputs = (node.get('reagent_vars', []) +
                              list(node.get('intra_sharing_vars', {}).values()) +
                              list(node.get('inter_sharing_vars', {}).values()))
                    total_sum = z3.Sum(inputs)
                    
                    if l == 0:
                        self.opt.add(total_sum == f_value)
                    else:
                        self.opt.add(z3.Or(total_sum == f_value, total_sum == 0))

    def _set_range_constraints(self):
        """各変数の範囲制約"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                f_value = self.problem.targets_config[m]['factors'][l]
                original_upper = f_value - 1
                for node in nodes:
                    for var in node.get('reagent_vars', []):
                        self.opt.add(var >= 0, var <= original_upper)
                    
                    sharing_vars = (list(node.get('intra_sharing_vars', {}).values()) +
                                    list(node.get('inter_sharing_vars', {}).values()))
                    for var in sharing_vars:
                        self.opt.add(var >= 0)
                        # インポートした定数を使用
                        upper_bound = min(original_upper, MAX_SHARING_VOLUME) if MAX_SHARING_VOLUME is not None else original_upper
                        self.opt.add(var <= upper_bound)

    def _set_symmetry_breaking_constraints(self):
        """同じレベルにあるノード間で順序を強制し、冗長な探索を削減する。"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                if len(nodes) > 1:
                    for k in range(len(nodes) - 1):
                        inputs_k = (nodes[k].get('reagent_vars', []) +
                                    list(nodes[k].get('intra_sharing_vars', {}).values()) +
                                    list(nodes[k].get('inter_sharing_vars', {}).values()))
                        total_input_k = z3.Sum(inputs_k)
                        
                        inputs_k1 = (nodes[k+1].get('reagent_vars', []) +
                                     list(nodes[k+1].get('intra_sharing_vars', {}).values()) +
                                     list(nodes[k+1].get('inter_sharing_vars', {}).values()))
                        total_input_k1 = z3.Sum(inputs_k1)
                        
                        self.opt.add(total_input_k >= total_input_k1)

    def _set_activity_constraints(self):
        """アクティブノード制約: 生成された液体は使われるか、さもなければ生成されない"""
        for m_src, tree_src in enumerate(self.problem.forest):
            for l_src, nodes in tree_src.items():
                if l_src == 0: continue
                for k_src, node in enumerate(nodes):
                    inputs = (node.get('reagent_vars', []) +
                              list(node.get('intra_sharing_vars', {}).values()) +
                              list(node.get('inter_sharing_vars', {}).values()))
                    total_prod = z3.Sum(inputs)
                    
                    outgoing_vars = self._get_outgoing_vars(m_src, l_src, k_src)
                    total_used = z3.Sum(outgoing_vars)
                    self.opt.add(z3.Or(total_prod == 0, total_used > 0))

    def _set_objective_function(self):
        """目的関数: すべてのノードで発生する廃棄（余剰生成）量の合計を最小化する。"""
        all_waste_vars = []
        for m_src, tree_src in enumerate(self.problem.forest):
            for l_src, nodes in tree_src.items():
                if l_src == 0: continue
                for k_src, node in enumerate(nodes):
                    inputs = (node.get('reagent_vars', []) +
                              list(node.get('intra_sharing_vars', {}).values()) +
                              list(node.get('inter_sharing_vars', {}).values()))
                    total_prod = z3.Sum(inputs)
                    
                    outgoing = self._get_outgoing_vars(m_src, l_src, k_src)
                    total_used = z3.Sum(outgoing)
                    
                    waste_var = z3.Int(f"waste_m{m_src}_l{l_src}_k{k_src}")
                    self.opt.add(waste_var == total_prod - total_used)
                    # この waste 変数をノード辞書に追加して、後でレポーティングで参照できるようにする
                    node['waste_var'] = waste_var
                    all_waste_vars.append(waste_var)
                    
        total_waste_var = z3.Int("total_waste")
        self.opt.add(total_waste_var == z3.Sum(all_waste_vars))
        self.opt.minimize(total_waste_var)
        return total_waste_var

    def _get_outgoing_vars(self, m_src, l_src, k_src):
        """指定されたノードからのすべての出力変数をリストで返すヘルパー関数。"""
        outgoing = []
        for m_dst, tree_dst in enumerate(self.problem.forest):
            for l_dst, level_dst in tree_dst.items():
                for k_dst, node_dst in enumerate(level_dst):
                    key_intra = f"from_l{l_src}k{k_src}"
                    key_inter = f"from_m{m_src}_l{l_src}k{k_src}"
                    if m_src == m_dst and key_intra in node_dst.get('intra_sharing_vars', {}):
                        outgoing.append(node_dst['intra_sharing_vars'][key_intra])
                    elif m_src != m_dst and key_inter in node_dst.get('inter_sharing_vars', {}):
                        outgoing.append(node_dst['inter_sharing_vars'][key_inter])
        return outgoing