# core/solver/solution.py
from ortools.sat.python import cp_model
from utils import create_dfmm_node_name, parse_sharing_key

class OrToolsSolutionModel:
    """
    Or-Toolsソルバーが見つけた「解」を保持し、
    分析データ (analyze) を提供するクラス。
    """
    def __init__(self, problem, solver, variable_map, forest_vars, peer_vars, objective_value):
        self.problem = problem
        self.solver = solver
        self.variable_map = variable_map 
        self.forest_vars = forest_vars
        self.peer_vars = peer_vars
        self.objective_value = objective_value

    def eval(self, target):
        """変数オブジェクトまたは変数名から値を取得する"""
        # 文字列の場合のチェックを先に行う
        if isinstance(target, str):
            if target == "objective_variable": 
                return self.objective_value
            if target in self.variable_map:
                var = self.variable_map[target]
                return self.solver.Value(var)
            return 0 

        # 変数オブジェクトの場合
        try:
            return self.solver.Value(target)
        except:
            return 0

    def _v(self, target):
        """evalのエイリアス (整数値を返す)"""
        return int(self.eval(target))

    def analyze(self):
        """
        解を分析し、レポート用の辞書を返します。
        """
        results = {
            "total_operations": 0,
            "total_reagent_units": 0,
            "total_waste": 0,
            "reagent_usage": {},
            "nodes_details": [],
        }

        # forest_vars (構造化データ) を使用して反復
        for target_idx, tree_vars in enumerate(self.forest_vars):
            for level, node_vars_list in tree_vars.items():
                for node_idx, node_vars in enumerate(node_vars_list):
                    
                    total_input = self._v(node_vars['total_input_var'])
                    
                    if total_input == 0: continue

                    results["total_operations"] += 1
                    
                    # 試薬使用量
                    reagent_vals = [self._v(var) for var in node_vars['reagent_vars']]
                    for r_idx, val in enumerate(reagent_vals):
                        if val > 0:
                            results["total_reagent_units"] += val
                            results["reagent_usage"][r_idx] = results["reagent_usage"].get(r_idx, 0) + val
                            
                    # 廃棄物量 [MODIFIED] 明示的に is not None でチェックする
                    if node_vars['waste_var'] is not None:
                         results["total_waste"] += self._v(node_vars['waste_var'])
                         
                    # ノード詳細
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    results["nodes_details"].append({
                        "target_id": target_idx,
                        "level": level,
                        "name": node_name,
                        "total_input": total_input,
                        "ratio_composition": [self._v(var) for var in node_vars['ratio_vars']],
                        "mixing_str": self._generate_mixing_description(node_vars, target_idx)
                    })
                    
        results["nodes_details"].sort(key=lambda x: (x["target_id"], x["level"]))
        return results

    def _generate_mixing_description(self, node_vars, tree_idx):
        """ノードの混合内容を説明する文字列を生成"""
        desc = []
        # 試薬
        for r_idx, var in enumerate(node_vars.get('reagent_vars', [])):
            if (val := self._v(var)) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
        # 内部共有
        for key, var in node_vars.get('intra_sharing_vars', {}).items():
            if (val := self._v(var)) > 0:
                # key="from_l{l}k{k}" -> v_m{tree}_l{l}_k{k}
                parsed = parse_sharing_key(key.replace("from_", ""))
                src_name = create_dfmm_node_name(tree_idx, parsed["level"], parsed["node_idx"])
                desc.append(f"{val} x {src_name}")
        # 外部共有
        for key, var in node_vars.get('inter_sharing_vars', {}).items():
            if (val := self._v(var)) > 0:
                # key="from_m{m}_l{l}k{k}" -> v_m{m}_l{l}_k{k}
                parsed = parse_sharing_key(key.replace("from_", ""))
                src_name = create_dfmm_node_name(parsed["target_idx"], parsed["level"], parsed["node_idx"])
                desc.append(f"{val} x {src_name}")
        return ' + '.join(desc)