# p_checker.py
import math

class PValueChecker:
    """
    MTWMProblemのインスタンスを受け取り、
    構築されたツリー構造に基づいてPの値を計算・表示するクラス。
    """
    def __init__(self, problem):
        """
        コンストラクタ

        Args:
            problem (MTWMProblem): 解析対象のMTWMProblemインスタンス。
        """
        self.problem = problem
        # Pの値はproblemインスタンスに既に計算されているため、それを参照するだけ
        self.p_values = problem.p_values

    def display_p_values(self):
        """計算済みのPの値を分かりやすくコンソールに出力する。"""
        print("\n--- Calculated P-values per Node (for verification) ---")
        
        for m, p_tree in enumerate(self.p_values):
            target_info = self.problem.targets_config[m]
            print(f"\n[Target: {target_info['name']}] (Ratios: {target_info['ratios']}, Factors: {target_info['factors']})")
            
            if not p_tree:
                print("  No nodes generated for this target.")
                continue
                
            # ノードID (level, k) でソートして表示
            sorted_nodes = sorted(p_tree.items())
            
            for node_id, p_value in sorted_nodes:
                level, k = node_id
                # どのターゲットのノードかを明確にするため 'm' を含める
                print(f"  Node v_m{m}_l{level}_k{k}: P = {p_value}")
        
        print("-" * 55)