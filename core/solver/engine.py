# core/solver/engine.py
import time
import sys
from ortools.sat.python import cp_model
from utils.config_loader import Config
from .solution import OrToolsSolutionModel

sys.setrecursionlimit(2000)

class SolutionCallback(cp_model.CpSolverSolutionCallback):
    def __init__(self, problem, variable_map, forest_vars, peer_vars, objective_var, objective_mode):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.problem = problem
        self.variable_map = variable_map
        self.forest_vars = forest_vars # [NEW]
        self.peer_vars = peer_vars     # [NEW]
        self.objective_var = objective_var
        self.objective_mode = objective_mode
        self.best_model = None
        self.best_value = float('inf')
        self.best_analysis = None
        self.start_time = time.time()

    def OnSolutionCallback(self):
        current_value = self.Value(self.objective_var)
        if current_value < self.best_value:
            elapsed = time.time() - self.start_time
            print(f"Found a new, better solution with {self.objective_mode}: {int(current_value)} (Time: {elapsed:.2f}s)")
            self.best_value = current_value
            
            # [MODIFIED] forest_vars, peer_vars を渡す
            self.best_model = OrToolsSolutionModel(
                self.problem, self, self.variable_map, 
                self.forest_vars, self.peer_vars, current_value
            )
            self.best_analysis = self.best_model.analyze()

class OrToolsSolver:
    def __init__(self, problem, objective_mode="waste", max_workers=None):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        if Config.MAX_CPU_WORKERS and Config.MAX_CPU_WORKERS > 0:
            self.solver.parameters.num_search_workers = Config.MAX_CPU_WORKERS
        if Config.MAX_TIME_PER_RUN_SECONDS and Config.MAX_TIME_PER_RUN_SECONDS > 0:
            self.solver.parameters.max_time_in_seconds = float(Config.MAX_TIME_PER_RUN_SECONDS)
        if Config.ABSOLUTE_GAP_LIMIT and Config.ABSOLUTE_GAP_LIMIT > 0:
            self.solver.parameters.absolute_gap_limit = float(Config.ABSOLUTE_GAP_LIMIT)

        self.solver.parameters.log_search_progress = True
        self.solver.parameters.linearization_level = 2 
        
        self.variable_map = {}
        self.forest_vars = [] # [NEW]
        self.peer_vars = []   # [NEW] (MTWMでは空だが互換性のため用意)
        
        self._set_variables_and_constraints()

    def solve(self):
        start_time = time.time()
        print(f"\n--- Solving (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")
        
        solution_callback = SolutionCallback(
            self.problem, self.variable_map, self.forest_vars, self.peer_vars, 
            self.objective_variable, self.objective_mode
        )
        status = self.solver.Solve(self.model, solution_callback)
        elapsed_time = time.time() - start_time
        
        best_model = solution_callback.best_model
        best_value = solution_callback.best_value if solution_callback.best_value != float('inf') else None
        best_analysis = solution_callback.best_analysis
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            final_val = self.solver.ObjectiveValue()
            if best_value is None or abs(final_val - best_value) > 1e-6:
                print(f"Or-Tools found final solution ({self.solver.StatusName(status)}): {int(final_val)}")
                best_value = final_val
                # [MODIFIED] forest_vars, peer_vars を渡す
                best_model = OrToolsSolutionModel(
                    self.problem, self.solver, self.variable_map, 
                    self.forest_vars, self.peer_vars, best_value
                )
                best_analysis = best_model.analyze()
        
        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time

    # ... (変数定義メソッドを修正) ...
    
    def _add_var(self, name, lb, ub):
        if name in self.variable_map: return self.variable_map[name]
        var = self.model.NewIntVar(lb, ub, name)
        self.variable_map[name] = var
        return var

    def _get_var(self, name): return self.variable_map[name]

    def _set_variables_and_constraints(self):
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_activity_constraints()
        self._set_symmetry_breaking_constraints()
        self.objective_variable = self._set_objective_function()
        
    def _define_or_tools_variables(self):
        self.forest_vars = [] # 初期化
        self.peer_vars = []   # MTWMにはPeerノードがないため空のまま

        for m, tree in enumerate(self.problem.forest):
            tree_data = {}
            for l, nodes in tree.items():
                level_nodes = []
                for k, node_def in enumerate(nodes):
                    p_node = self.problem.p_values[m][(l, k)]
                    f_value = self.problem.targets_config[m]['factors'][l]
                    
                    # [MODIFIED] 変数オブジェクトをリスト/辞書として保持する
                    ratio_vars = [self._add_var(name, 0, p_node) for name in node_def['ratio_vars']]
                    
                    reagent_max = max(0, f_value - 1)
                    reagent_vars = [self._add_var(name, 0, reagent_max) for name in node_def['reagent_vars']]
                    
                    sharing_max = f_value
                    if Config.MAX_SHARING_VOLUME is not None: sharing_max = min(f_value, Config.MAX_SHARING_VOLUME)
                    
                    intra_sharing_vars = {key: self._add_var(name, 0, sharing_max) for key, name in node_def.get('intra_sharing_vars', {}).items()}
                    inter_sharing_vars = {key: self._add_var(name, 0, sharing_max) for key, name in node_def.get('inter_sharing_vars', {}).items()}
                    
                    total_input_var = self._add_var(node_def['total_input_var_name'], 0, f_value)
                    is_active_var = self._add_var(f"IsActive_m{m}_l{l}_k{k}", 0, 1) 
                    waste_var = self._add_var(node_def['waste_var_name'], 0, f_value) if node_def['waste_var_name'] else None

                    # 構造化データを保存
                    level_nodes.append({
                        "ratio_vars": ratio_vars,
                        "reagent_vars": reagent_vars,
                        "intra_sharing_vars": intra_sharing_vars,
                        "inter_sharing_vars": inter_sharing_vars,
                        "total_input_var": total_input_var,
                        "is_active_var": is_active_var,
                        "waste_var": waste_var
                    })
                tree_data[l] = level_nodes
            self.forest_vars.append(tree_data)

    # ... (以下のメソッドは前回と同じ内容で維持してください) ...
    def _get_input_vars(self, node_def):
        var_names = (node_def.get('reagent_vars', []) + list(node_def.get('intra_sharing_vars', {}).values()) + list(node_def.get('inter_sharing_vars', {}).values()))
        return [self._get_var(name) for name in var_names]

    def _get_outgoing_vars(self, m_src, l_src, k_src):
        outgoing = []
        key_intra = f"from_l{l_src}k{k_src}"
        key_inter = f"from_m{m_src}_l{l_src}k{k_src}"
        for m_dst, tree_dst in enumerate(self.problem.forest):
            for l_dst, level_dst in tree_dst.items():
                for k_dst, node_def in enumerate(level_dst):
                    if m_src == m_dst and key_intra in node_def.get('intra_sharing_vars', {}):
                        outgoing.append(self._get_var(node_def['intra_sharing_vars'][key_intra]))
                    elif m_src != m_dst and key_inter in node_def.get('inter_sharing_vars', {}):
                        outgoing.append(self._get_var(node_def['inter_sharing_vars'][key_inter]))
        return outgoing
    
    def _iterate_all_nodes(self):
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                for k, node_def in enumerate(nodes):
                    yield m, l, k, node_def

    def _set_initial_constraints(self):
        for m, target in enumerate(self.problem.targets_config):
            root_def = self.problem.forest[m][0][0]
            for t in range(self.problem.num_reagents):
                self.model.Add(self._get_var(root_def['ratio_vars'][t]) == target['ratios'][t])

    def _set_conservation_constraints(self):
        for m_src, l_src, k_src, node_def in self._iterate_all_nodes():
            total_produced_var = self._get_var(node_def['total_input_var_name'])
            self.model.Add(total_produced_var == sum(self._get_input_vars(node_def)))

    def _set_concentration_constraints(self):
        for m_dst, l_dst, k_dst, node_def in self._iterate_all_nodes():
            p_dst = self.problem.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            for t in range(self.problem.num_reagents):
                lhs = f_dst * self._get_var(node_def['ratio_vars'][t])
                reagent_var = self._get_var(node_def['reagent_vars'][t])
                rhs_terms = [p_dst * reagent_var]
                
                for key, w_var_name in node_def.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src_var = self._get_var(self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t])
                    w_var = self._get_var(w_var_name)
                    p_src = self.problem.p_values[m_dst][(l_src, k_src)]
                    product_bound = p_src * f_dst 
                    product_var = self._add_var(f"Prod_intra_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}", 0, product_bound)
                    self.model.AddMultiplicationEquality(product_var, [r_src_var, w_var])
                    rhs_terms.append(product_var * (p_dst // p_src)) 
                    
                for key, w_var_name in node_def.get('inter_sharing_vars', {}).items():
                    m_src_str, lk_src_str = key.replace("from_m", "").split("_l")
                    m_src = int(m_src_str)
                    l_src, k_src = map(int, lk_src_str.split("k"))
                    r_src_var = self._get_var(self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t])
                    w_var = self._get_var(w_var_name)
                    p_src = self.problem.p_values[m_src][(l_src, k_src)]
                    product_bound = p_src * f_dst
                    product_var = self._add_var(f"Prod_inter_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}", 0, product_bound)
                    self.model.AddMultiplicationEquality(product_var, [r_src_var, w_var])
                    rhs_terms.append(product_var * (p_dst // p_src))
                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        for m, l, k, node_def in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            ratio_vars = [self._get_var(name) for name in node_def['ratio_vars']]
            is_active_var = self._get_var(f"IsActive_m{m}_l{l}_k{k}")
            self.model.Add(sum(ratio_vars) == p_node).OnlyEnforceIf(is_active_var)
            for r_var in ratio_vars: self.model.Add(r_var == 0).OnlyEnforceIf(is_active_var.Not())

    def _set_leaf_node_constraints(self):
        for m, l, k, node_def in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            f_node = self.problem.targets_config[m]['factors'][l]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.model.Add(self._get_var(node_def['ratio_vars'][t]) == self._get_var(node_def['reagent_vars'][t]))

    def _set_mixer_capacity_constraints(self):
        for m, l, k, node_def in self._iterate_all_nodes():
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum_var = self._get_var(node_def['total_input_var_name'])
            is_active_var = self._get_var(f"IsActive_m{m}_l{l}_k{k}")
            if l == 0: 
                self.model.Add(total_sum_var == f_value)
                self.model.Add(is_active_var == 1)
            else: 
                self.model.Add(total_sum_var == is_active_var * f_value)
                
    def _set_activity_constraints(self):
        for m_src, l_src, k_src, node_def in self._iterate_all_nodes():
            if l_src == 0: continue 
            total_used_vars = self._get_outgoing_vars(m_src, l_src, k_src)
            is_active_var = self._get_var(f"IsActive_m{m_src}_l{l_src}_k{k_src}")
            self.model.Add(sum(total_used_vars) >= is_active_var)

    def _set_symmetry_breaking_constraints(self):
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                if len(nodes) > 1:
                    for k in range(len(nodes) - 1):
                        is_active_k = self._get_var(f"IsActive_m{m}_l{l}_k{k}")
                        is_active_k1 = self._get_var(f"IsActive_m{m}_l{l}_k{k+1}")
                        self.model.Add(is_active_k >= is_active_k1)

    def _set_objective_function(self):
        all_waste_vars = []
        for m_src, l_src, k_src, node_def in self._iterate_all_nodes():
            if l_src == 0: continue 
            total_prod_var = self._get_var(node_def['total_input_var_name'])
            total_used_vars = self._get_outgoing_vars(m_src, l_src, k_src)
            waste_var = self._get_var(node_def['waste_var_name'])
            self.model.Add(waste_var == total_prod_var - sum(total_used_vars))
            all_waste_vars.append(waste_var)
            
        total_waste = sum(all_waste_vars)

        if self.objective_mode == "waste":
            self.model.Add(total_waste >= 1)
            
        all_activity_vars = [self._get_var(f"IsActive_m{m}_l{l}_k{k}") for m, l, k, node_def in self._iterate_all_nodes()]
        total_operations = sum(all_activity_vars)
        
        if self.objective_mode == 'waste':
            self.model.Minimize(total_waste)
            self.variable_map["objective_variable"] = total_waste 
            return total_waste
        elif self.objective_mode == 'operations':
            self.model.Minimize(total_operations)
            self.variable_map["objective_variable"] = total_operations 
            return total_operations
        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'")
