import time
from ortools.sat.python import cp_model
from reporting.reporter import SolutionReporter
from utils.config_loader import Config
import sys

# 再帰制限の引き上げ（必要に応じて）
sys.setrecursionlimit(2000)

# R * W * C 項の最大値。変数の最大値 (p_node, f_value) から安全マージンをとる。
# (後述の最適化により、この定数はデフォルト値としてのみ使用)
MAX_PRODUCT_BOUND = 50000 


# --- Or-Toolsへのデータアクセスアダプタ ---
class OrToolsModelAdapter:
    # ... (このクラスは変更なし) ...
    def __init__(self, solver, variable_map, objective_value):
        self.solver = solver
        self.variable_map = variable_map 
        self.objective_value = objective_value

    def eval(self, var_name):
        if var_name == "objective_variable":
             return self._get_value_wrapper(self.objective_value)
        if var_name in self.variable_map:
            or_tools_var = self.variable_map[var_name]
            if isinstance(self.solver, cp_model.CpSolver):
                return self._get_value_wrapper(self.solver.Value(or_tools_var))
            else:
                return self._get_value_wrapper(self.solver.Value(or_tools_var))
        return self._get_value_wrapper(0)

    def _get_value_wrapper(self, value):
        class OrToolsValue:
            def __init__(self, val): self.value = val
            def as_long(self): return int(self.value)
        return OrToolsValue(value if value is not None else 0)
        
    def get_model(self):
        return self
        

# --- ソリューションコールバック ---
class SolutionCallback(cp_model.CpSolverSolutionCallback):
    # ... (このクラスは変更なし) ...
    def __init__(self, problem, variable_map, objective_var, objective_mode):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.problem = problem
        self.variable_map = variable_map
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
            self.best_model = OrToolsModelAdapter(self, self.variable_map, current_value)
            reporter = SolutionReporter(self.problem, self.best_model, self.objective_mode)
            self.best_analysis = reporter.analyze_solution()

# --- メインクラス ---
class OrToolsSolver:
    """
    Or-Tools CP-SATソルバーと対話し、最適化問題の制約を設定し、解を求めるクラス。
    """
    def __init__(self, problem, objective_mode="waste", max_workers=None):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        if Config.MAX_CPU_WORKERS is not None and Config.MAX_CPU_WORKERS > 0:
            self.solver.parameters.num_search_workers = Config.MAX_CPU_WORKERS
            print(f"Solver set to use a maximum of {Config.MAX_CPU_WORKERS} CPU workers.")
        
        max_time = Config.MAX_TIME_PER_RUN_SECONDS
        if max_time is not None and max_time > 0:
            print(f"--- Setting max time per run to {max_time} seconds ---")
            self.solver.parameters.max_time_in_seconds = float(max_time)

        gap_limit = Config.ABSOLUTE_GAP_LIMIT
        if gap_limit is not None and gap_limit > 0:
            print(f"--- Setting absolute gap limit to {gap_limit} ---")
            self.solver.parameters.absolute_gap_limit = float(gap_limit)

        # --- テクニック適用 ---
        self.solver.parameters.log_search_progress = True
        # 掛け算が多いモデル向けのチューニング
        self.solver.parameters.linearization_level = 2 
        
        self.variable_map = {}
        self._set_variables_and_constraints()

    def solve(self):
        """最適化問題を解くメインのメソッド（Or-Tools CP-SAT版）。"""
        start_time = time.time()
        print(f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")
        
        # モデルの妥当性確認
        try:
            validation = self.model.Validate()
            if validation:
                print(f"Model validation warning: {validation}")
        except Exception as e:
            print(f"Model validation failed: {e}")
            return None, None, None, 0

        solution_callback = SolutionCallback(
            self.problem, self.variable_map, self.objective_variable, self.objective_mode
        )

        status = self.solver.Solve(self.model, solution_callback)
        elapsed_time = time.time() - start_time
        
        best_model = solution_callback.best_model
        best_value = solution_callback.best_value if solution_callback.best_value != float('inf') else None
        best_analysis = solution_callback.best_analysis
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            final_objective_value = self.solver.ObjectiveValue()
            if best_value is None or abs(final_objective_value - best_value) > 1e-6:
                print(f"Or-Tools found final solution ({self.solver.StatusName(status)}) with {self.objective_mode}: {int(final_objective_value)}")
                best_value = final_objective_value
                best_model = OrToolsModelAdapter(self.solver, self.variable_map, best_value)
                reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
                best_analysis = reporter.analyze_solution()
            else:
                 print(f"Or-Tools final status: {self.solver.StatusName(status)}. Best solution {int(best_value)} confirmed.")
        elif status == cp_model.INFEASIBLE:
            print("No feasible solution found.")
        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")

        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time

    # --- 変数定義と制約設定メソッド群 ---
    
    def _add_var(self, name, lb, ub):
        if name in self.variable_map:
            return self.variable_map[name]
        var = self.model.NewIntVar(lb, ub, name)
        self.variable_map[name] = var
        return var

    def _get_var(self, name):
        return self.variable_map[name]

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
        # ... (IsUsed変数の削除以外は変更なし) ...
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                for k, node_def in enumerate(nodes):
                    p_node = self.problem.p_values[m][(l, k)]
                    f_value = self.problem.targets_config[m]['factors'][l]

                    for var_name in node_def['ratio_vars']:
                        self._add_var(var_name, 0, p_node)
                        
                    reagent_max = max(0, f_value - 1)
                    for var_name in node_def['reagent_vars']:
                        self._add_var(var_name, 0, reagent_max)
                        
                    sharing_max = f_value
                    if Config.MAX_SHARING_VOLUME is not None:
                         sharing_max = min(f_value, Config.MAX_SHARING_VOLUME)
                         
                    for var_name in node_def.get('intra_sharing_vars', {}).values():
                         self._add_var(var_name, 0, sharing_max)
                    for var_name in node_def.get('inter_sharing_vars', {}).values():
                         self._add_var(var_name, 0, sharing_max)
                        
                    self._add_var(node_def['total_input_var_name'], 0, f_value)
                    self._add_var(f"IsActive_m{m}_l{l}_k{k}", 0, 1) 
                    
                    if node_def['waste_var_name']:
                        self._add_var(node_def['waste_var_name'], 0, f_value)

    def _get_input_vars(self, node_def):
        var_names = (node_def.get('reagent_vars', []) +
                     list(node_def.get('intra_sharing_vars', {}).values()) +
                     list(node_def.get('inter_sharing_vars', {}).values()))
        return [self._get_var(name) for name in var_names]

    def _get_outgoing_vars(self, m_src, l_src, k_src):
        outgoing = []
        key_intra = f"from_l{l_src}k{k_src}"
        key_inter = f"from_m{m_src}_l{l_src}k{k_src}"
        for m_dst, tree_dst in enumerate(self.problem.forest):
            for l_dst, level_dst in tree_dst.items():
                for k_dst, node_def in enumerate(level_dst):
                    if m_src == m_dst and key_intra in node_def.get('intra_sharing_vars', {}):
                        var_name = node_def['intra_sharing_vars'][key_intra]
                        outgoing.append(self._get_var(var_name))
                    elif m_src != m_dst and key_inter in node_def.get('inter_sharing_vars', {}):
                        var_name = node_def['inter_sharing_vars'][key_inter]
                        outgoing.append(self._get_var(var_name))
        return outgoing
    
    def _iterate_all_nodes(self):
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                for k, node_def in enumerate(nodes):
                    yield m, l, k, node_def

    # --- 制約設定メソッド ---
    def _set_initial_constraints(self):
        for m, target in enumerate(self.problem.targets_config):
            root_def = self.problem.forest[m][0][0]
            for t in range(self.problem.num_reagents):
                var_name = root_def['ratio_vars'][t]
                self.model.Add(self._get_var(var_name) == target['ratios'][t])

    def _set_conservation_constraints(self):
        for m_src, l_src, k_src, node_def in self._iterate_all_nodes():
            total_produced_var = self._get_var(node_def['total_input_var_name'])
            input_vars = self._get_input_vars(node_def)
            self.model.Add(total_produced_var == sum(input_vars))

    def _set_concentration_constraints(self):
        for m_dst, l_dst, k_dst, node_def in self._iterate_all_nodes():
            p_dst = self.problem.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            
            for t in range(self.problem.num_reagents):
                lhs = f_dst * self._get_var(node_def['ratio_vars'][t])
                reagent_var = self._get_var(node_def['reagent_vars'][t])
                rhs_terms = [p_dst * reagent_var]
                
                # 内部共有 (上限の厳密化を適用)
                for key, w_var_name in node_def.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src_var = self._get_var(self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t])
                    w_var = self._get_var(w_var_name)
                    p_src = self.problem.p_values[m_dst][(l_src, k_src)]
                    
                    # 積の最大値を計算 (p_src * f_dst が安全な上限)
                    product_bound = p_src * f_dst 
                    product_var = self._add_var(f"Prod_intra_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}", 0, product_bound)
                    self.model.AddMultiplicationEquality(product_var, [r_src_var, w_var])
                    
                    rhs_terms.append(product_var * (p_dst // p_src)) 
                    
                # 外部共有 (上限の厳密化を適用)
                for key, w_var_name in node_def.get('inter_sharing_vars', {}).items():
                    m_src_str, lk_src_str = key.replace("from_m", "").split("_l")
                    m_src = int(m_src_str)
                    l_src, k_src = map(int, lk_src_str.split("k"))
                    r_src_var = self._get_var(self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t])
                    w_var = self._get_var(w_var_name)
                    p_src = self.problem.p_values[m_src][(l_src, k_src)]

                    # 積の最大値を計算
                    product_bound = p_src * f_dst
                    product_var = self._add_var(f"Prod_inter_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}", 0, product_bound)
                    self.model.AddMultiplicationEquality(product_var, [r_src_var, w_var])
                    
                    rhs_terms.append(product_var * (p_dst // p_src))
                
                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """
        [修正] 非アクティブなノードの比率を 0 に固定し、過剰な制約を回避します。
        """
        for m, l, k, node_def in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            ratio_vars = [self._get_var(name) for name in node_def['ratio_vars']]
            is_active_var = self._get_var(f"IsActive_m{m}_l{l}_k{k}")

            # アクティブな場合のみ、比率の合計は P値
            self.model.Add(sum(ratio_vars) == p_node).OnlyEnforceIf(is_active_var)
            # 非アクティブな場合は、比率をすべて 0 に固定
            for r_var in ratio_vars:
                self.model.Add(r_var == 0).OnlyEnforceIf(is_active_var.Not())

    def _set_leaf_node_constraints(self):
        for m, l, k, node_def in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            f_node = self.problem.targets_config[m]['factors'][l]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    ratio_var = self._get_var(node_def['ratio_vars'][t])
                    reagent_var = self._get_var(node_def['reagent_vars'][t])
                    self.model.Add(ratio_var == reagent_var)

    def _set_mixer_capacity_constraints(self):
        """
        [最適化] 論理制約を使わず、線形等式で表現します。
        """
        for m, l, k, node_def in self._iterate_all_nodes():
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum_var = self._get_var(node_def['total_input_var_name'])
            is_active_var = self._get_var(f"IsActive_m{m}_l{l}_k{k}")

            if l == 0: 
                self.model.Add(total_sum_var == f_value)
                self.model.Add(is_active_var == 1)
            else: 
                # 単純な掛け算で表現: total_sum == is_active * f_value
                self.model.Add(total_sum_var == is_active_var * f_value)
                
    def _set_activity_constraints(self):
        """
        [最適化] 冗長な変数を削除し、単純な線形不等式で表現します。
        """
        for m_src, l_src, k_src, node_def in self._iterate_all_nodes():
            if l_src == 0: continue 
            
            total_used_vars = self._get_outgoing_vars(m_src, l_src, k_src)
            is_active_var = self._get_var(f"IsActive_m{m_src}_l{l_src}_k{k_src}")
            
            # アクティブ(1)なら使用量の合計は1以上、非アクティブ(0)なら0以上
            self.model.Add(sum(total_used_vars) >= is_active_var)

    def _set_symmetry_breaking_constraints(self):
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                if len(nodes) > 1:
                    node_defs = [self.problem.forest[m][l][k] for k in range(len(nodes))]
                    for k in range(len(node_defs) - 1):
                        # まずアクティブかどうかでソート (Activeなものを左に)
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