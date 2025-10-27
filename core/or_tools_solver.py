# or_tools_solver.py (最終修正版)
import time
from ortools.sat.python import cp_model
from reporting.reporter import SolutionReporter
from config import MAX_SHARING_VOLUME, MAX_MIXER_SIZE, MAX_LEVEL_DIFF
import sys

# 再帰制限の引き上げ（必要に応じて）
sys.setrecursionlimit(2000)

# R * W * C 項の最大値。変数の最大値 (900) * 定数 (例: 5) でも 4500 程度。
# 安全性を考慮して大きめの値を設定します。
MAX_PRODUCT_BOUND = 50000 

# --- Or-Toolsへのデータアクセスアダプタ ---
class OrToolsModelAdapter:
    """
    Or-Toolsの解(Solver)とProblem定義(変数名)を保持し、
    SolutionReporterからの問い合わせ（変数名による値の要求）に応答するアダプタ。
    """
    def __init__(self, solver, variable_map, objective_value):
        self.solver = solver
        self.variable_map = variable_map # { "R_m0_l0_k0_t0": or_tools_var, ... }
        self.objective_value = objective_value

    def eval(self, var_name):
        """
        変数名（文字列）または特別な識別子を受け取り、Or-Toolsの解の値を取得する。
        """
        # 1. 目的変数の評価
        if var_name == "objective_variable":
             return self._get_value_wrapper(self.objective_value)
        
        # 2. それ以外の変数の評価（Mapから検索）
        if var_name in self.variable_map:
            or_tools_var = self.variable_map[var_name]
            return self._get_value_wrapper(self.solver.Value(or_tools_var))

        # デバッグ用：見つからない変数名を警告
        # print(f"Warning: Could not find variable name in OrToolsModelAdapter map: {var_name}")
        # 見つからない場合は 0 を返す (非アクティブなノードの変数など)
        return self._get_value_wrapper(0)


    def _get_value_wrapper(self, value):
        """SolutionReporterが要求する as_long() メソッドを持つラッパーオブジェクトを返す。"""
        class OrToolsValue:
            def __init__(self, val): self.value = val
            def as_long(self): return int(self.value)
        # valueがNoneの場合は0を返す (Or-Toolsが値を設定しなかった場合)
        return OrToolsValue(value if value is not None else 0)
        
    def get_model(self):
        # SolutionReporterの互換性のために、evalメソッドを持つ自身を返す
        return self
        
class OrToolsSolver:
    """
    Or-Tools CP-SATソルバーと対話し、最適化問題の制約を設定し、解を求めるクラス。
    """
    def __init__(self, problem, objective_mode="waste", max_workers=None):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        if max_workers is not None and isinstance(max_workers, int) and max_workers > 0:
            self.solver.parameters.num_search_workers = max_workers
            print(f"Solver set to use a maximum of {max_workers} CPU workers.")
        
        # 変数名（文字列）と Or-Tools 変数オブジェクトのマッピング
        self.variable_map = {}
        
        self._set_variables_and_constraints()

    # def solve(self, checkpoint_handler): # <--- 修正前
    def solve(self): # <--- 修正後
        """最適化問題を解くメインのメソッド（Or-Tools CP-SAT版）。"""
        

        start_time = time.time()
        
        print(f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")

        # ソルバーの実行
        status = self.solver.Solve(self.model)
        elapsed_time = time.time() - start_time
        
        best_model = None
        best_value = None
        best_analysis = None
        
        # Or-ToolsのSolve()は、最適解が見つかった場合に cp_model.OPTIMAL を返す
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            print(f"Or-Tools found an optimal solution with {self.objective_mode}: {int(best_value)}")

            # SolutionReporter互換のためのアダプタを生成
            best_model = OrToolsModelAdapter(self.solver, self.variable_map, best_value)
            
            # SolutionReporterによる分析
            reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
            best_analysis = reporter.analyze_solution()
            

        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
            
            if status == cp_model.INFEASIBLE:
                print("No feasible solution found.")


        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time

    # --- 変数定義と制約設定メソッド群 ---
    
    def _add_var(self, name, lb, ub):
        """変数をモデルとMapに追加するヘルパー関数"""
        if name in self.variable_map:
            return self.variable_map[name]
        var = self.model.NewIntVar(lb, ub, name)
        self.variable_map[name] = var
        return var

    def _get_var(self, name):
        """Mapから変数を取得するヘルパー関数"""
        return self.variable_map[name]

    def _set_variables_and_constraints(self):
        """全ての変数定義と制約設定を統括する。"""
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_range_constraints()
        self._set_activity_constraints()
        self.objective_variable = self._set_objective_function()
        
    def _define_or_tools_variables(self):
        """MTWMProblemの構造（変数名）に基づき、Or-Toolsの変数を定義する。"""
        MAX_BOUND = 900 # 経験的な最大値
        
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                for k, node_def in enumerate(nodes):
                    
                    # 比率変数
                    for var_name in node_def['ratio_vars']:
                        self._add_var(var_name, 0, MAX_BOUND)
                    # 試薬変数
                    for var_name in node_def['reagent_vars']:
                        self._add_var(var_name, 0, MAX_BOUND)
                        
                    # 共有変数
                    max_sharing_vol = min(MAX_BOUND, MAX_SHARING_VOLUME or MAX_BOUND)
                    for var_name in node_def.get('intra_sharing_vars', {}).values():
                         self._add_var(var_name, 0, max_sharing_vol)
                    for var_name in node_def.get('inter_sharing_vars', {}).values():
                         self._add_var(var_name, 0, max_sharing_vol)
                        
                    # ヘルパー変数 (総入力、活動状態、廃棄物量)
                    self._add_var(node_def['total_input_var_name'], 0, MAX_BOUND)
                    self._add_var(f"IsActive_m{m}_l{l}_k{k}", 0, 1) # BoolVar
                    if node_def['waste_var_name']:
                        self._add_var(node_def['waste_var_name'], 0, MAX_BOUND)


    def _get_input_vars(self, node_def):
        """特定のノード定義（辞書）に関連するOr-Tools入力変数のリストを取得する"""
        var_names = (node_def.get('reagent_vars', []) +
                     list(node_def.get('intra_sharing_vars', {}).values()) +
                     list(node_def.get('inter_sharing_vars', {}).values()))
        return [self._get_var(name) for name in var_names]

    def _get_outgoing_vars(self, m_src, l_src, k_src):
        """特定のノードから出ていくOr-Tools共有変数のリストを取得する"""
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
        """Problem定義の全ノードをイテレートする"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                for k, node_def in enumerate(nodes):
                    yield m, l, k, node_def

    # --- 制約設定メソッド (Or-Tools構文) ---
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
                
                # 内部共有
                for key, w_var_name in node_def.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src_var = self._get_var(self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t])
                    w_var = self._get_var(w_var_name)
                    p_src = self.problem.p_values[m_dst][(l_src, k_src)]
                    
                    product_var = self._add_var(f"Prod_intra_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}", 0, MAX_PRODUCT_BOUND)
                    self.model.AddMultiplicationEquality(product_var, [r_src_var, w_var])
                    
                    scale_factor = (p_dst // p_src)
                    rhs_terms.append(product_var * scale_factor) 
                    
                # 外部共有
                for key, w_var_name in node_def.get('inter_sharing_vars', {}).items():
                    m_src_str, lk_src_str = key.replace("from_m", "").split("_l")
                    m_src = int(m_src_str)
                    l_src, k_src = map(int, lk_src_str.split("k"))
                    r_src_var = self._get_var(self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t])
                    w_var = self._get_var(w_var_name)
                    p_src = self.problem.p_values[m_src][(l_src, k_src)]

                    product_var = self._add_var(f"Prod_inter_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}", 0, MAX_PRODUCT_BOUND)
                    self.model.AddMultiplicationEquality(product_var, [r_src_var, w_var])
                    
                    scale_factor = (p_dst // p_src)
                    rhs_terms.append(product_var * scale_factor)
                
                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        for m, l, k, node_def in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            ratio_vars = [self._get_var(name) for name in node_def['ratio_vars']]
            self.model.Add(sum(ratio_vars) == p_node)

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
        for m, l, k, node_def in self._iterate_all_nodes():
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum_var = self._get_var(node_def['total_input_var_name'])
            is_active_var = self._get_var(f"IsActive_m{m}_l{l}_k{k}")
            
            # total_sum > 0 <=> is_active
            self.model.Add(total_sum_var > 0).OnlyEnforceIf(is_active_var)
            self.model.Add(total_sum_var == 0).OnlyEnforceIf(is_active_var.Not())

            if l == 0: 
                self.model.Add(total_sum_var == f_value)
            else: 
                self.model.Add(total_sum_var == f_value).OnlyEnforceIf(is_active_var)
                self.model.Add(total_sum_var == 0).OnlyEnforceIf(is_active_var.Not())

    def _set_range_constraints(self):
        for m, l, k, node_def in self._iterate_all_nodes():
            upper_bound = self.problem.targets_config[m]['factors'][l] - 1
            
            for var_name in node_def.get('reagent_vars', []):
                self.model.Add(self._get_var(var_name) <= upper_bound)
            
            # 共有変数の上限は _define_or_tools_variables で設定済み

    def _set_activity_constraints(self):
        for m_src, l_src, k_src, node_def in self._iterate_all_nodes():
            if l_src == 0: continue 
            
            total_used_vars = self._get_outgoing_vars(m_src, l_src, k_src)
            is_active_var = self._get_var(f"IsActive_m{m_src}_l{l_src}_k{k_src}")
            
            is_used_var = self._add_var(f"IsUsed_m{m_src}_l{l_src}_k{k_src}", 0, 1)
            self.model.Add(sum(total_used_vars) >= 1).OnlyEnforceIf(is_used_var)
            self.model.Add(sum(total_used_vars) == 0).OnlyEnforceIf(is_used_var.Not())
            
            self.model.AddImplication(is_active_var, is_used_var)

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
            self.variable_map["objective_variable"] = total_waste # アダプタ用
            return total_waste
        elif self.objective_mode == 'operations':
            self.model.Minimize(total_operations)
            self.variable_map["objective_variable"] = total_operations # アダプタ用
            return total_operations
        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'. Must be 'waste' or 'operations'.")