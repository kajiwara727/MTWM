# z3_solver.py (修正版)
import z3
import time
from reporting import SolutionReporter
from config import MAX_SHARING_VOLUME

# --- ヘルパー関数 (変更なし) ---
def _iterate_all_nodes(problem):
    for m, tree in enumerate(problem.forest):
        for l, nodes in tree.items():
            for k, node in enumerate(nodes):
                yield m, l, k, node

def _get_node_inputs(node):
    return (node.get('reagent_vars', []) +
            list(node.get('intra_sharing_vars', {}).values()) +
            list(node.get('inter_sharing_vars', {}).values()))

def _get_outgoing_vars(problem, m_src, l_src, k_src):
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
    def __init__(self, problem, objective_mode="waste"):
        self.problem = problem
        self.objective_mode = objective_mode
        self.opt = z3.Optimize()
        z3.set_param('memory_max_size', 8192)
        self.last_check_result = None
        self._set_all_constraints()
        self.objective_variable = self._set_objective_function()

    # --- ▼▼▼ ここからが修正点です ▼▼▼ ---
    def solve(self, checkpoint_handler):
        """
        最適化問題を解く。
        checkpoint_handlerがNoneの場合は、チェックポイント機能を使用しない。
        """
        last_best_value = None
        last_analysis = None
        # チェックポイントハンドラが存在する場合のみ、読み込みを試みる
        if checkpoint_handler:
            last_best_value, last_analysis = checkpoint_handler.load_checkpoint()

        if last_best_value is not None:
            self.opt.add(self.objective_variable < last_best_value)

        print(f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) ---")
        print("(press Ctrl+C to interrupt and save)")
        
        best_model = None
        best_value = last_best_value
        best_analysis = last_analysis
        start_time = time.time()
        
        try:
            while self.check() == z3.sat:
                current_model = self.get_model()
                current_value = current_model.eval(self.objective_variable).as_long()
                print(f"Found a new, better solution with {self.objective_mode}: {current_value}")
                
                best_value = current_value
                best_model = current_model
                
                # チェックポイントハンドラが存在する場合のみ、分析と保存を行う
                if checkpoint_handler:
                    reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
                    analysis = reporter.analyze_solution()
                    best_analysis = analysis
                    checkpoint_handler.save_checkpoint(analysis, best_value, time.time() - start_time)
                
                if best_value == 0:
                    print(f"Found optimal solution with zero {self.objective_mode}.")
                    break
                
                self.opt.add(self.objective_variable < best_value)

        except KeyboardInterrupt:
            print("\nOptimization interrupted by user. Reporting the best solution found so far.")

        elapsed_time = time.time() - start_time
        print("--- Z3 Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time
    # --- ▲▲▲ ここまでが修正点です ▲▲▲ ---

    def check(self):
        self.last_check_result = self.opt.check()
        return self.last_check_result

    def get_model(self):
        return self.opt.model()

    # --- 制約設定メソッド (変更なし) ---
    def _set_all_constraints(self):
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
            p_dst = self.problem.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            for t in range(self.problem.num_reagents):
                lhs = f_dst * node['ratio_vars'][t]
                rhs_terms = [p_dst * node['reagent_vars'][t]]
                for key, w_var in node.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src = self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_dst][(l_src, k_src)]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                for key, w_var in node.get('inter_sharing_vars', {}).items():
                    m_src_str, lk_src_str = key.replace("from_m", "").split("_l")
                    m_src = int(m_src_str)
                    l_src, k_src = map(int, lk_src_str.split("k"))
                    r_src = self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_src][(l_src, k_src)]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                self.opt.add(lhs == z3.Sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        for m, target in enumerate(self.problem.targets_config):
            p_root = self.problem.p_values[m][(0, 0)]
            if sum(target['ratios']) != p_root:
                raise ValueError(
                    f"Target '{target['name']}' ratios sum ({sum(target['ratios'])}) "
                    f"does not match the root p-value ({p_root}). "
                    f"The sum of ratios must equal the product of all factors based on the generated tree."
                )
        for m, l, k, node in _iterate_all_nodes(self.problem):
            p_node = self.problem.p_values[m][(l, k)]
            self.opt.add(z3.Sum(node['ratio_vars']) == p_node)

    def _set_leaf_node_constraints(self):
        for m, l, k, node in _iterate_all_nodes(self.problem):
            p_node = self.problem.p_values[m][(l, k)]
            f_node = self.problem.targets_config[m]['factors'][l]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.opt.add(node['ratio_vars'][t] == node['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        for m, l, k, node in _iterate_all_nodes(self.problem):
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum = z3.Sum(_get_node_inputs(node))
            if l == 0:
                self.opt.add(total_sum == f_value)
            else:
                self.opt.add(z3.Implies(total_sum > 0, total_sum == f_value))
                self.opt.add(z3.Or(total_sum == 0, total_sum == f_value))

    def _set_range_constraints(self):
        for m, l, k, node in _iterate_all_nodes(self.problem):
            upper_bound = self.problem.targets_config[m]['factors'][l] - 1
            for var in node.get('reagent_vars', []):
                self.opt.add(var >= 0, var <= upper_bound)
            sharing_vars = (list(node.get('intra_sharing_vars', {}).values()) +
                            list(node.get('inter_sharing_vars', {}).values()))
            for var in sharing_vars:
                effective_upper = upper_bound
                if MAX_SHARING_VOLUME is not None:
                    effective_upper = min(upper_bound, MAX_SHARING_VOLUME)
                self.opt.add(var >= 0, var <= effective_upper)

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
            self.opt.add(z3.Implies(total_prod > 0, total_used > 0))

    def _set_objective_function(self):
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
        all_activity_vars = []
        for m, l, k, node in _iterate_all_nodes(self.problem):
            is_active = z3.Bool(f"active_m{m}_l{l}_k{k}")
            total_input = z3.Sum(_get_node_inputs(node))
            self.opt.add(is_active == (total_input > 0))
            all_activity_vars.append(z3.If(is_active, 1, 0))
        total_operations = z3.Int("total_operations")
        self.opt.add(total_operations == z3.Sum(all_activity_vars))
        if self.objective_mode == 'waste':
            self.opt.minimize(total_waste)
            return total_waste
        elif self.objective_mode == 'operations':
            self.opt.minimize(total_operations)
            return total_operations
        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'. Must be 'waste' or 'operations'.")