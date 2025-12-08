import time
import sys
from ortools.sat.python import cp_model
from utils.config_loader import Config
from utils import parse_sharing_key
from .solution import OrToolsSolutionModel
import math
from functools import reduce

sys.setrecursionlimit(2000)

class SolutionPrinter(cp_model.CpSolverSolutionCallback):
    """解が見つかるたびに進捗を表示するコールバッククラス"""
    def __init__(self):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.__solution_count = 0
        self.__start_time = time.time()

    def on_solution_callback(self):
        self.__solution_count += 1
        current_time = time.time()
        obj = self.ObjectiveValue()
        print(f"Solution #{self.__solution_count}: Objective = {obj}, Time = {current_time - self.__start_time:.2f}s")

    @property
    def solution_count(self):
        return self.__solution_count

class OrToolsSolver:
    """MTWMProblem を Or-Tools CP-SAT モデルに変換し、最適化を実行するクラス。"""

    def __init__(self, problem, objective_mode="waste"):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # 変数格納用コンテナ
        self.forest_vars = [] 
        
        # 既存システム(SolutionModel等)との互換性のためのマップ
        self.variable_map = {} 
        self.objective_variable = None

        self._configure_solver()
        self._set_variables_and_constraints()

    def _configure_solver(self):
        """ソルバーのパラメータ設定"""
        if Config.MAX_CPU_WORKERS and Config.MAX_CPU_WORKERS > 0:
            self.solver.parameters.num_workers = Config.MAX_CPU_WORKERS
        else:
            self.solver.parameters.num_workers = 0 
        
        if Config.MAX_TIME_PER_RUN_SECONDS and Config.MAX_TIME_PER_RUN_SECONDS > 0:
            self.solver.parameters.max_time_in_seconds = float(Config.MAX_TIME_PER_RUN_SECONDS)

        if Config.ABSOLUTE_GAP_LIMIT and Config.ABSOLUTE_GAP_LIMIT > 0:
            self.solver.parameters.absolute_gap_limit = float(Config.ABSOLUTE_GAP_LIMIT)
        
        self.solver.parameters.linearization_level = 2
        self.solver.parameters.optimize_with_core =False
        self.solver.parameters.max_num_cuts = 2000 
        self.solver.parameters.cut_level = 2
        self.solver.parameters.boolean_encoding_level = 2
        self.solver.parameters.symmetry_level = 2 
        self.solver.parameters.log_search_progress = True

    def solve(self):
        start_time = time.time()
        print(f"\n--- Solving (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")
        
        solution_printer = SolutionPrinter()
        status = self.solver.Solve(self.model, solution_printer)
        
        elapsed_time = time.time() - start_time
        best_model = None
        best_value = None
        best_analysis = None

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
            print(f"Or-Tools finished: {status_str} solution found. Value: {int(best_value)}")
            print(f"Total solutions found: {solution_printer.solution_count}")
            
            # Peer変数は存在しないため空リストを渡すか、引数から除外（SolutionModelの実装依存）
            # ここでは標準的な引数構成を想定
            best_model = OrToolsSolutionModel(
                self.problem, self.solver, self.variable_map,
                self.forest_vars, [], best_value
            )
            best_analysis = best_model.analyze()
        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
                
        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time

    # --- 変数定義 ---

    def _add_var(self, var, name):
        """変数をvariable_mapに登録するヘルパー"""
        self.variable_map[name] = var
        return var

    def _define_or_tools_variables(self):
        """変数定義：DFMMノードの変数を初期化"""
        self.forest_vars = []

        for target_idx, tree in enumerate(self.problem.forest):
            tree_data = {}
            # tree は {level: [nodes...]} の辞書
            for level, nodes in tree.items():
                level_nodes = []
                for k, node_def in enumerate(nodes):
                    # p_values を使用
                    p_node = self.problem.p_values[target_idx][(level, k)]
                    f_value = self.problem.targets_config[target_idx]['factors'][level]
                    
                    reagent_max = max(0, f_value - 1)
                    
                    # 比率変数
                    ratio_vars = [
                        self._add_var(self.model.NewIntVar(0, p_node, name), name)
                        for name in node_def['ratio_vars']
                    ]
                    
                    # 試薬使用量変数
                    reagent_vars = [
                        self._add_var(self.model.NewIntVar(0, reagent_max, name), name)
                        for name in node_def['reagent_vars']
                    ]
                    
                    max_sharing_vol = f_value
                    if Config.MAX_SHARING_VOLUME is not None:
                        max_sharing_vol = min(f_value, Config.MAX_SHARING_VOLUME)

                    # 内部共有変数 (Intra)
                    intra_sharing_vars = {}
                    for key, name in node_def.get('intra_sharing_vars', {}).items():
                        intra_sharing_vars[key] = self._add_var(
                            self.model.NewIntVar(0, max_sharing_vol, name), name
                        )
                    
                    # 外部共有変数 (Inter)
                    inter_sharing_vars = {}
                    for key, name in node_def.get('inter_sharing_vars', {}).items():
                        inter_sharing_vars[key] = self._add_var(
                            self.model.NewIntVar(0, max_sharing_vol, name), name
                        )

                    # 基本状態変数
                    total_input_var = self._add_var(
                        self.model.NewIntVar(0, f_value, node_def['total_input_var_name']),
                        node_def['total_input_var_name']
                    )
                    
                    # IsActive変数の名前は固定パターンで生成
                    is_active_name = f"IsActive_m{target_idx}_l{level}_k{k}"
                    is_active_var = self._add_var(
                        self.model.NewBoolVar(is_active_name), is_active_name
                    )

                    waste_var = None
                    if node_def['waste_var_name']:
                        waste_var = self._add_var(
                            self.model.NewIntVar(0, f_value, node_def['waste_var_name']),
                            node_def['waste_var_name']
                        )

                    # 構造化データとして保存
                    node_vars = {
                        "ratio_vars": ratio_vars,
                        "reagent_vars": reagent_vars,
                        "intra_sharing_vars": intra_sharing_vars,
                        "inter_sharing_vars": inter_sharing_vars,
                        "total_input_var": total_input_var,
                        "is_active_var": is_active_var,
                        "waste_var": waste_var
                    }
                    level_nodes.append(node_vars)
                
                tree_data[level] = level_nodes
            self.forest_vars.append(tree_data)

    def _set_variables_and_constraints(self):
        """制約設定のメインフロー"""
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_activity_constraints()
        
        self.objective_variable = self._set_objective_function()

    # --- ヘルパーメソッド ---

    def _get_input_vars(self, node_vars):
        """ノードへの全入力変数を取得（試薬 + Intra + Inter）"""
        return (
            node_vars.get("reagent_vars", [])
            + list(node_vars.get("intra_sharing_vars", {}).values())
            + list(node_vars.get("inter_sharing_vars", {}).values())
        )

    def _get_outgoing_vars(self, src_target_idx, src_level, src_node_idx):
        """あるノードから出ていく全共有変数を取得"""
        outgoing = []
        key_intra = f"from_l{src_level}k{src_node_idx}"
        key_inter = f"from_m{src_target_idx}_l{src_level}k{src_node_idx}"
        
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for node_dst in level_dst:
                    # Intra-sharing
                    if src_target_idx == dst_target_idx and key_intra in node_dst.get("intra_sharing_vars", {}):
                        outgoing.append(node_dst["intra_sharing_vars"][key_intra])
                    # Inter-sharing
                    elif src_target_idx != dst_target_idx and key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        return outgoing

    def _iterate_all_nodes(self):
        """全DFMMノードをイテレートするジェネレータ"""
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node_vars in enumerate(nodes):
                    yield target_idx, level, node_idx, node_vars

    # --- 制約メソッド ---

    def _set_initial_constraints(self):
        """ルートノードの濃度比率をターゲット定義に固定"""
        for m, target in enumerate(self.problem.targets_config):
            if 0 in self.forest_vars[m] and self.forest_vars[m][0]:
                root_vars = self.forest_vars[m][0][0]
                for t in range(self.problem.num_reagents):
                    self.model.Add(root_vars['ratio_vars'][t] == target['ratios'][t])

    def _set_conservation_constraints(self):
        """質量保存則: 生産量 == 全入力の和"""
        for _, _, _, node_vars in self._iterate_all_nodes():
            total_produced = node_vars["total_input_var"]
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))

    def _lcm(self, numbers):
        """整数のリストの最小公倍数を計算するヘルパー"""
        if not numbers:
            return 1
        return reduce(lambda x, y: (x * y) // math.gcd(x, y), numbers)

    def _set_concentration_constraints(self):
        """濃度保存則: LCMを用いて整数演算のみで厳密に計算する"""
        
        for dst_target_idx, dst_level, dst_node_idx, node_vars in self._iterate_all_nodes():
            p_dst = self.problem.p_values[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.problem.targets_config[dst_target_idx]['factors'][dst_level]
            node_name_prefix = f"m{dst_target_idx}l{dst_level}k{dst_node_idx}"

            # 1. 入力元の情報を収集 (P値と変数を取得)
            # 形式: (p_src, ratio_var, volume_var, key_name, scaling_limit)
            input_sources = []

            # (A) Intra Sharing
            for key, w_var in node_vars.get('intra_sharing_vars', {}).items():
                key_no_prefix = key.replace("from_", "")
                parsed = parse_sharing_key(key_no_prefix)
                src_l, src_k = parsed["level"], parsed["node_idx"]
                
                p_src = self.problem.p_values[dst_target_idx][(src_l, src_k)]
                r_src_vars = self.forest_vars[dst_target_idx][src_l][src_k]['ratio_vars']
                f_src = self.problem.targets_config[dst_target_idx]['factors'][src_l]
                
                input_sources.append({
                    "p_src": p_src, "ratio_vars": r_src_vars, "w_var": w_var,
                    "key": key, "limit_vol": f_src
                })

            # (B) Inter Sharing
            for key, w_var in node_vars.get('inter_sharing_vars', {}).items():
                key_no_prefix = key.replace("from_", "")
                parsed = parse_sharing_key(key_no_prefix)
                src_m, src_l, src_k = parsed["target_idx"], parsed["level"], parsed["node_idx"]
                
                p_src = self.problem.p_values[src_m][(src_l, src_k)]
                r_src_vars = self.forest_vars[src_m][src_l][src_k]['ratio_vars']
                f_src = self.problem.targets_config[src_m]['factors'][src_l]

                input_sources.append({
                    "p_src": p_src, "ratio_vars": r_src_vars, "w_var": w_var,
                    "key": key, "limit_vol": f_src
                })

            # 2. LCM (最小公倍数) の計算
            # ターゲットのp_dst と すべてのソースの p_src のLCMをとる
            all_p_values = [src["p_src"] for src in input_sources] + [p_dst]
            common_multiple = self._lcm(all_p_values)

            # 3. 試薬ごとの保存則制約を作成
            # 基本式: Vol * Ratio * (LCM / P) の総和が等しい
            
            for t in range(self.problem.num_reagents):
                # --- 左辺 (Output) ---
                # LHS = f_dst * ratio_dst * (LCM / p_dst)
                lhs_scale = common_multiple // p_dst
                # 大きくなりすぎないよう、計算途中用の変数を定義するか、直接式を書く
                # ここではスッキリさせるため直接記述
                lhs_term = f_dst * node_vars['ratio_vars'][t] * lhs_scale

                # --- 右辺 (Inputs) ---
                rhs_terms = []

                # (1) 直接投入試薬 (Pure Reagent)
                # 純粋試薬は「濃度1 (100%)」とみなす => P=1 相当
                # したがって、スケールは LCM / 1 = LCM
                if t < len(node_vars['reagent_vars']):
                    vol_var = node_vars['reagent_vars'][t]
                    rhs_terms.append(vol_var * common_multiple)

                # (2) 共有入力 (Intra + Inter)
                for src in input_sources:
                    scale = common_multiple // src["p_src"]
                    r_src_var = src["ratio_vars"][t]
                    w_var = src["w_var"]
                    
                    # 積: prod = w_var * r_src_var
                    # 変数の上限を見積もる (Volume_Max * P_Max)
                    prod_max = src["limit_vol"] * src["p_src"]
                    
                    prod = self.model.NewIntVar(0, prod_max, f"Prod_{node_name_prefix}_{src['key']}_r{t}")
                    self.model.AddMultiplicationEquality(prod, [w_var, r_src_var])
                    
                    # スケール倍して加算
                    rhs_terms.append(prod * scale)

                # 等式の登録
                self.model.Add(lhs_term == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """比率変数の総和制約"""
        for m, l, k, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            is_active = node_vars["is_active_var"]
            self.model.Add(sum(node_vars['ratio_vars']) == p_node * is_active)

    def _set_leaf_node_constraints(self):
        """葉ノード制約"""
        for m, l, k, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            f_node = self.problem.targets_config[m]['factors'][l]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.model.Add(node_vars['ratio_vars'][t] == node_vars['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        """ミキサー容量制約"""
        for m, l, k, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum = node_vars["total_input_var"]
            is_active = node_vars["is_active_var"]
            
            if l == 0:
                self.model.Add(total_sum == f_value)
                self.model.Add(is_active == 1)
            else:
                self.model.Add(total_sum == f_value * is_active)

    def _set_activity_constraints(self):
        """アクティビティ制約"""
        for m, l, k, node_vars in self._iterate_all_nodes():
            if l == 0: continue 
            total_used_vars = self._get_outgoing_vars(m, l, k)
            is_active = node_vars["is_active_var"]
            total_used = sum(total_used_vars)
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_active)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_active.Not())

    def _set_objective_function(self):
        """目的関数の設定"""
        all_waste_vars = []
        all_activity_vars = []
        all_reagent_vars = []
        
        for m, l, k, node_vars in self._iterate_all_nodes():
            if l == 0:
                all_activity_vars.append(node_vars["is_active_var"])
                continue
            
            total_prod = node_vars["total_input_var"]
            total_used = sum(self._get_outgoing_vars(m, l, k))
            waste_var = node_vars["waste_var"]
            
            self.model.Add(waste_var == total_prod - total_used)
            
            all_waste_vars.append(waste_var)
            all_activity_vars.append(node_vars["is_active_var"])
            all_reagent_vars.extend(node_vars.get("reagent_vars", []))
            
        total_waste = sum(all_waste_vars)
        total_operations = sum(all_activity_vars)
        total_reagents = sum(all_reagent_vars)

        if self.objective_mode == "waste":
            self.model.Add(total_waste >= 1)
            self.model.Minimize(total_waste)
            self.variable_map["objective_variable"] = total_waste
            return total_waste
            
        elif self.objective_mode == "operations":
            self.model.Minimize(total_operations)
            self.variable_map["objective_variable"] = total_operations
            return total_operations

        elif self.objective_mode == "reagents":
            self.model.Minimize(total_reagents)
            return total_reagents

        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'")
