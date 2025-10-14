# z3_solver.py
import z3
import time
from reporting import SolutionReporter
from config import MAX_SHARING_VOLUME

# --- ヘルパー関数: ループ処理のカプセル化 ---

def _iterate_all_nodes(problem):
    """problem.forest内の全てのノードを巡回するジェネレータ。

    Args:
        problem: 最適化問題の定義を含むProblemオブジェクト。

    Yields:
        tuple: (m, l, k, node) - ツリーインデックス, レベル, ノードインデックス, ノードオブジェクト。
    """
    for m, tree in enumerate(problem.forest):
        for l, nodes in tree.items():
            for k, node in enumerate(nodes):
                yield m, l, k, node

def _get_node_inputs(node):
    """ノードへの全入力（試薬＋共有液）変数のリストを返す。

    Args:
        node (dict): Z3変数が格納されたノードオブジェクト。

    Returns:
        list: ノードへの入力となるZ3変数のリスト。
    """
    return (node.get('reagent_vars', []) +
            list(node.get('intra_sharing_vars', {}).values()) +
            list(node.get('inter_sharing_vars', {}).values()))

def _get_outgoing_vars(problem, m_src, l_src, k_src):
    """指定されたノードから出ていく全ての共有変数を取得する。

    Args:
        problem: 最適化問題の定義を含むProblemオブジェクト。
        m_src (int): ソースノードのツリーインデックス。
        l_src (int): ソースノードのレベル。
        k_src (int): ソースノードのインデックス。

    Returns:
        list: 指定ノードから出力される共有液のZ3変数リスト。
    """
    outgoing = []
    # 共有変数を格納しているキー名は、受け取り側（dst）の視点で定義されているため、
    # ここでは送信元（src）の情報からキーを生成し、全ノードを探索する。
    key_intra = f"from_l{l_src}k{k_src}"
    key_inter = f"from_m{m_src}_l{l_src}k{k_src}"

    for m_dst, tree_dst in enumerate(problem.forest):
        for l_dst, level_dst in tree_dst.items():
            for k_dst, node_dst in enumerate(level_dst):
                # ツリー内共有
                if m_src == m_dst and key_intra in node_dst.get('intra_sharing_vars', {}):
                    outgoing.append(node_dst['intra_sharing_vars'][key_intra])
                # ツリー間共有
                elif m_src != m_dst and key_inter in node_dst.get('inter_sharing_vars', {}):
                    outgoing.append(node_dst['inter_sharing_vars'][key_inter])
    return outgoing

# --- メインクラス ---

class Z3Solver:
    """
    Z3 Optimizeソルバーを使用して混合問題を定式化し、解を求めるクラス。
    """
    def __init__(self, problem):
        """
        Args:
            problem: 最適化問題の定義を含むProblemオブジェクト。
        """
        self.problem = problem
        self.opt = z3.Optimize()
        # メモリ上限を設定 (8GB)
        z3.set_param('memory_max_size', 8192)

        self.last_check_result = None
        self._set_all_constraints()
        self.total_waste_var = self._set_objective_function()

    def solve(self, checkpoint_handler):
        """最適化問題をインクリメンタルに解き、最良のモデルを返す。

        より良い解が見つかるたびにチェックポイントを保存する。
        Ctrl+Cで中断された場合は、その時点での最良解を返す。

        Args:
            checkpoint_handler: チェックポイントの読み書きを行うハンドラ。

        Returns:
            tuple: (best_model, min_waste_val, best_analysis, elapsed_time)
                   - 最良解のモデル、最小廃棄量、最良解の分析結果、経過時間。
        """
        last_best_waste, last_analysis = checkpoint_handler.load_checkpoint()
        if last_best_waste is not None:
            # 前回の最良解より良いものを探す制約を追加
            self.opt.add(self.total_waste_var < last_best_waste)

        print("\n--- Solving the optimization problem (press Ctrl+C to interrupt and save) ---")
        best_model = None
        min_waste_val = last_best_waste
        best_analysis = last_analysis
        start_time = time.time()
        
        try:
            # sat (satisfiable) の間、つまり解が存在する間ループを続ける
            while self.check() == z3.sat:
                current_model = self.get_model()
                current_waste = current_model.eval(self.total_waste_var).as_long()
                print(f"Found a new, better solution with waste: {current_waste}")
                
                # 最良解を更新
                min_waste_val = current_waste
                best_model = current_model
                
                # 解を分析し、チェックポイントを保存
                reporter = SolutionReporter(self.problem, best_model)
                analysis = reporter.analyze_solution()
                best_analysis = analysis # 最新の分析結果を保持
                checkpoint_handler.save_checkpoint(analysis, min_waste_val, time.time() - start_time)
                
                # 廃棄量ゼロは理論上の最適解なので、探索を終了
                if min_waste_val == 0:
                    print("Found optimal solution with zero waste.")
                    break
                
                # 次のループでは、現在の解よりもさらに良い解を探す
                self.opt.add(self.total_waste_var < min_waste_val)

        except KeyboardInterrupt:
            print("\nOptimization interrupted by user. Reporting the best solution found so far.")

        elapsed_time = time.time() - start_time
        print("--- Z3 Solver Finished ---")
        return best_model, min_waste_val, best_analysis, elapsed_time

    def check(self):
        """ソルバーの充足可能性をチェックする。"""
        self.last_check_result = self.opt.check()
        return self.last_check_result

    def get_model(self):
        """最後のcheck()がsatだった場合にモデルを返す。"""
        return self.opt.model()

    # --- 制約設定メソッド ---

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
        """ルートノードの組成比率が、最終目標の組成比率と一致するよう設定する。"""
        for m, target in enumerate(self.problem.targets_config):
            root = self.problem.forest[m][0][0]
            for t in range(self.problem.num_reagents):
                self.opt.add(root['ratio_vars'][t] == target['ratios'][t])

    def _set_conservation_constraints(self):
        """物質保存則：各ノードからの総出力量は、総入力量を超えてはならない。"""
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            total_produced = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            self.opt.add(total_used <= total_produced)

    def _set_concentration_constraints(self):
        """濃度（組成比）の制約：混合後の液体の組成比は、入力された液体の量と組成比から計算される。"""
        for m_dst, l_dst, k_dst, node in _iterate_all_nodes(self.problem):
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            p_dst = self.problem.p_values[m_dst][l_dst]
            for t in range(self.problem.num_reagents):
                # 左辺: 混合後の総液量 x 試薬tの比率 (スケーリング済み)
                lhs = f_dst * node['ratio_vars'][t]
                
                # 右辺: 各入力の液量 x 各入力の試薬tの比率 (スケーリング済み) の総和
                # p値は希釈係数の累積積であり、異なるレベル間の比率を比較可能にするためのスケーリングファクター
                rhs_terms = [p_dst * node['reagent_vars'][t]]
                
                # ツリー内共有からの入力
                for key, w_var in node.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src = self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_dst][l_src]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                    
                # ツリー間共有からの入力
                for key, w_var in node.get('inter_sharing_vars', {}).items():
                    m_src_str, lk_src_str = key.replace("from_m", "").split("_l")
                    m_src = int(m_src_str)
                    l_src, k_src = map(int, lk_src_str.split("k"))
                    r_src = self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_src][l_src]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                    
                self.opt.add(lhs == z3.Sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """全試薬の組成比の合計は、そのレベルのp値（累積希釈係数）と一致しなければならない。"""
        # ルートノードでの事前チェック
        for m, target in enumerate(self.problem.targets_config):
            p_root = self.problem.p_values[m][0]
            if sum(target['ratios']) != p_root:
                raise ValueError(
                    f"Target '{target['name']}' ratios sum ({sum(target['ratios'])}) "
                    f"does not match the root p-value ({p_root}). "
                    f"The sum of ratios must equal the product of all factors."
                )
        
        # 全ノードでの制約
        for m, l, k, node in _iterate_all_nodes(self.problem):
            self.opt.add(z3.Sum(node['ratio_vars']) == self.problem.p_values[m][l])

    def _set_leaf_node_constraints(self):
        """リーフノード（これ以上希釈されないノード）では、試薬の投入量がそのまま組成比になる。"""
        for m, l, k, node in _iterate_all_nodes(self.problem):
            # p_value == factor は、そのレベルが最後の希釈段階であることを示す
            if self.problem.p_values[m][l] == self.problem.targets_config[m]['factors'][l]:
                for t in range(self.problem.num_reagents):
                    self.opt.add(node['ratio_vars'][t] == node['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        """各ノード（ミキサー）の総入力量に関する制約。"""
        for m, l, k, node in _iterate_all_nodes(self.problem):
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum = z3.Sum(_get_node_inputs(node))
            
            if l == 0: # ルートノードは必ず目標量を生成する
                self.opt.add(total_sum == f_value)
            else: # 中間ノードは、使われるなら規定量(f_value)を生成し、使われないなら0を生成する
                # total_sum > 0 => total_sum == f_value
                self.opt.add(z3.Implies(total_sum > 0, total_sum == f_value))
                # 上記Impliesを補強し、探索を効率化するために明示的に制約を追加
                self.opt.add(z3.Or(total_sum == 0, total_sum == f_value))

    def _set_range_constraints(self):
        """各変数が取りうる値の範囲を定義する。"""
        for m, l, k, node in _iterate_all_nodes(self.problem):
            # 各ノードでの最大混合量は希釈係数-1。例えば希釈係数4なら、0-3の4段階の量を扱える。
            upper_bound = self.problem.targets_config[m]['factors'][l] - 1
            
            # 試薬投入量の範囲
            for var in node.get('reagent_vars', []):
                self.opt.add(var >= 0, var <= upper_bound)
            
            # 共有液量の範囲
            sharing_vars = (list(node.get('intra_sharing_vars', {}).values()) +
                            list(node.get('inter_sharing_vars', {}).values()))
            for var in sharing_vars:
                # 設定ファイルで最大共有量が指定されていれば、その値とupper_boundの小さい方を上限とする
                effective_upper = upper_bound
                if MAX_SHARING_VOLUME is not None:
                    effective_upper = min(upper_bound, MAX_SHARING_VOLUME)
                self.opt.add(var >= 0, var <= effective_upper)


    def _set_symmetry_breaking_constraints(self):
        """対称性の破壊：同一レベルに複数のノードがある場合、解の探索空間を削減するための制約。"""
        # 例えば、ノードAで2単位、ノードBで3単位生成する解と、
        # Aで3単位、Bで2単位生成する解は実質的に同じ。
        # このような等価な解を排除するため、ノードのインデックス順に生成量が
        # 小さくなる（or 等しくなる）よう制約を課す。
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                if len(nodes) > 1:
                    for k in range(len(nodes) - 1):
                        total_input_k = z3.Sum(_get_node_inputs(nodes[k]))
                        total_input_k1 = z3.Sum(_get_node_inputs(nodes[k+1]))
                        self.opt.add(total_input_k >= total_input_k1)

    def _set_activity_constraints(self):
        """活動制約：中間ノードで液体が生成された場合、それは必ずどこかで使用されなければならない。"""
        # ルートノード(l_src == 0)は最終生成物なので対象外
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            if l_src == 0: continue
            
            total_prod = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            
            # total_prod > 0 ならば total_used > 0
            # (生成されたが使われない、という無駄な中間生成を禁止する)
            self.opt.add(z3.Implies(total_prod > 0, total_used > 0))

    def _set_objective_function(self):
        """目的関数：総廃棄量（生成されたが使われなかった量）の最小化。"""
        all_waste_vars = []
        # ルートノード(l_src == 0)は最終生成物なので廃棄の対象外
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            if l_src == 0: continue
            
            total_prod = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            
            waste_var = z3.Int(f"waste_m{m_src}_l{l_src}_k{k_src}")
            node['waste_var'] = waste_var
            
            # waste = 生成量 - 消費量
            self.opt.add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            
        total_waste = z3.Int("total_waste")
        self.opt.add(total_waste == z3.Sum(all_waste_vars))
        self.opt.minimize(total_waste)
        return total_waste