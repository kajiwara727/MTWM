# z3_solver.py
import z3
import time
from reporting import SolutionReporter
from config import MAX_SHARING_VOLUME

# --- ヘルパー関数: ループ処理をカプセル化 ---

def _iterate_all_nodes(problem):
    """forest内の全てのノードを巡回するジェネレータ"""
    for m, tree in enumerate(problem.forest):
        for l, nodes in tree.items():
            for k, node in enumerate(nodes):
                yield m, l, k, node

def _get_node_inputs(node):
    """ノードへの全入力（試薬＋共有液）変数のリストを返す"""
    return (node.get('reagent_vars', []) +
            list(node.get('intra_sharing_vars', {}).values()) +
            list(node.get('inter_sharing_vars', {}).values()))

def _get_outgoing_vars(problem, m_src, l_src, k_src):
    """指定されたノードから出ていく全ての共有変数を取得する"""
    outgoing = []
    key_intra = f"from_l{l_src}k{k_src}"
    key_inter = f"from_m{m_src}_l{l_src}k{k_src}"

    for m_dst, tree_dst in enumerate(problem.forest):
        for l_dst, level_dst in tree_dst.items():
            for k_dst, node_dst in enumerate(level_dst):
                if m_src == m_dst and key_intra in node_dst.get('intra_sharing_vars', {}):
                    outgoing.append(node_dst['intra_sharing_vars'][key_intra])
                elif m_src != m_dst and key_inter in node_dst.get('inter_sharing_vars', {}):
                    outgoing.append(node_dst['inter_sharing_vars'][key_inter])
    return outgoing

# --- メインクラス ---

class Z3Solver:
    def __init__(self, problem):
        self.problem = problem
        self.opt = z3.Optimize()
        self.last_check_result = None
        self._set_all_constraints()
        self.total_waste_var = self._set_objective_function()

    def solve(self, checkpoint_handler):
        """最適化問題をインクリメンタルに解き、最良のモデルを返す"""
        last_best_waste, last_analysis = checkpoint_handler.load_checkpoint()
        if last_best_waste is not None:
            self.opt.add(self.total_waste_var < last_best_waste)

        print("\n--- 4. Solving the optimization problem (press Ctrl+C to interrupt and save) ---")
        best_model = None
        min_waste_val = last_best_waste
        start_time = time.time()
        
        # z3.set_param('verbose', 1)
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
            # z3.set_param('verbose', 0)
            pass

        elapsed_time = time.time() - start_time
        print("--- Z3 Solver Finished ---")
        return best_model, min_waste_val, last_analysis, elapsed_time

    def check(self):
        self.last_check_result = self.opt.check()
        return self.last_check_result

    def get_model(self):
        return self.opt.model()

    # --- 制約設定メソッド ---

    def _set_all_constraints(self):
        """モデルに必要なすべての制約を追加する"""
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
        for m, target in enumerate(self.problem.targets_config):
            root = self.problem.forest[m][0][0]
            for t in range(self.problem.num_reagents):
                self.opt.add(root['ratio_vars'][t] == target['ratios'][t])

    def _set_conservation_constraints(self):
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            total_produced = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            self.opt.add(total_used <= total_produced)

    def _set_concentration_constraints(self):
        for m_dst, l_dst, k_dst, node in _iterate_all_nodes(self.problem):
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            p_dst = self.problem.p_values[m_dst][l_dst]
            for t in range(self.problem.num_reagents):
                lhs = f_dst * node['ratio_vars'][t]
                rhs_terms = [p_dst * node['reagent_vars'][t]]
                
                for key, w_var in node.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src = self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_dst][l_src]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                    
                for key, w_var in node.get('inter_sharing_vars', {}).items():
                    m_src = int(key.split("_l")[0].replace("from_m", ""))
                    l_src, k_src = map(int, key.split("_l")[1].split("k"))
                    r_src = self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_src][l_src]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                    
                self.opt.add(lhs == z3.Sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        for m, l, k, node in _iterate_all_nodes(self.problem):
            self.opt.add(z3.Sum(node['ratio_vars']) == self.problem.p_values[m][l])

    def _set_leaf_node_constraints(self):
        for m, l, k, node in _iterate_all_nodes(self.problem):
            if self.problem.p_values[m][l] == self.problem.targets_config[m]['factors'][l]:
                for t in range(self.problem.num_reagents):
                    self.opt.add(node['ratio_vars'][t] == node['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        for m, l, k, node in _iterate_all_nodes(self.problem):
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum = z3.Sum(_get_node_inputs(node))
            if l == 0:
                self.opt.add(total_sum == f_value)
            else:
                self.opt.add(z3.Or(total_sum == f_value, total_sum == 0))

    def _set_range_constraints(self):
        for m, l, k, node in _iterate_all_nodes(self.problem):
            upper_bound = self.problem.targets_config[m]['factors'][l] - 1
            for var in _get_node_inputs(node):
                self.opt.add(var >= 0)
                effective_upper = upper_bound
                if "w_" in str(var) and MAX_SHARING_VOLUME is not None:
                    effective_upper = min(upper_bound, MAX_SHARING_VOLUME)
                self.opt.add(var <= effective_upper)

    def _set_symmetry_breaking_constraints(self):
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                if len(nodes) > 1:
                    for k in range(len(nodes) - 1):
                        total_input_k = z3.Sum(_get_node_inputs(nodes[k]))
                        total_input_k1 = z3.Sum(_get_node_inputs(nodes[k+1]))
                        self.opt.add(total_input_k >= total_input_k1)

    def _set_activity_constraints(self):
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            if l_src == 0: continue
            total_prod = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            self.opt.add(z3.Or(total_prod == 0, total_used > 0))

    def _set_objective_function(self):
        """目的関数：総廃棄量の最小化"""
        all_waste_vars = []
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            if l_src == 0: continue
            
            total_prod = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            
            waste_var = z3.Int(f"waste_m{m_src}_l{l_src}_k{k_src}")
            node['waste_var'] = waste_var
            
            self.opt.add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            
        total_waste = z3.Int("total_waste")
        self.opt.add(total_waste == z3.Sum(all_waste_vars))
        self.opt.minimize(total_waste)
        return total_waste