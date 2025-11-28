import os
import sys
from collections import defaultdict

# --- パス解決 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)
# --------------------

# 必要なモジュールをインポート
from utils.config_loader import Config
from utils import create_dfmm_node_name
from core.algorithm.dfmm import build_dfmm_forest, calculate_p_values_from_structure, apply_auto_factors
from core.model.problem import MTWMProblem
from scenarios import TARGETS_FOR_MANUAL_MODE, TARGETS_FOR_AUTO_MODE

def count_edges_for_analysis():
    """
    現在の設定に基づいてMTWMProblemを構築し、
    ソルバーに渡される「エッジ（接続候補）」の数を数えて分類表示し、
    結果をテキストファイルに出力します。
    """
    
    # 出力ファイルのパス設定
    output_filepath = os.path.join(current_dir, "edge_analysis_result.txt")

    # ファイルを開き、log関数で書き込みと表示を同時に行う
    with open(output_filepath, "w", encoding="utf-8") as f:
        
        def log(message=""):
            """コンソール表示とファイル書き込みを同時に行うヘルパー"""
            print(message)
            f.write(message + "\n")

        # 1. ターゲット設定の取得
        log(f"--- Edge Analysis for Mode: {Config.MODE} ---")
        if Config.MODE in ['auto', 'auto_permutations']:
            # リストをコピーして使用
            targets_config = [t.copy() for t in TARGETS_FOR_AUTO_MODE] 
            apply_auto_factors(targets_config, Config.MAX_MIXER_SIZE)
        elif Config.MODE == 'manual':
            targets_config = TARGETS_FOR_MANUAL_MODE
        else:
            log(f"Mode '{Config.MODE}' is not supported for this analysis script.")
            return

        log(f"Run Name: {Config.RUN_NAME}")
        for t in targets_config:
            log(f"  Target: {t['name']}")
            log(f"    - Ratios:  {t['ratios']}")
            log(f"    - Factors: {t['factors']}")
        log("-" * 60)

        # 2. 問題構造の構築
        tree_structures = build_dfmm_forest(targets_config)
        p_values = calculate_p_values_from_structure(tree_structures, targets_config)
        problem = MTWMProblem(targets_config, tree_structures, p_values)

        # --- 集計用変数の初期化 ---
        num_reagents = len(targets_config[0]['ratios'])
        
        # A. 試薬エッジ (Reagent -> Node)
        # forest構造: [ {level: [node_dicts...]}, ... ]
        total_dfmm_nodes = 0
        for tree in problem.forest:
            for level, nodes in tree.items():
                total_dfmm_nodes += len(nodes)

        total_reagent_edges = total_dfmm_nodes * num_reagents
        
        # B. 混合エッジ (Node <-> Node)
        counts = {
            "Default DFMM (Child->Parent)": 0,
            "Intra-Sharing (Skip Level)": 0,
            "Inter-Sharing (Cross Tree)": 0
        }
        
        # デフォルト接続（必須エッジ）の特定
        default_connections = set()
        for m_idx, tree in enumerate(tree_structures):
            for (p_lvl, p_idx), data in tree.items():
                for (c_lvl, c_idx) in data['children']:
                    dst = (m_idx, p_lvl, p_idx)
                    src = (m_idx, c_lvl, c_idx)
                    default_connections.add((dst, src))

        # (1) DFMMノードへの入力エッジを集計
        # potential_sources_map keys: (m, l, k)
        for dst_key, sources in problem.potential_sources_map.items():
            dst_m, _, _ = dst_key
            for src in sources:
                # src is (m, l, k) tuple
                src_m, _, _ = src
                connection_pair = (dst_key, src)
                
                if src_m != dst_m:
                    counts["Inter-Sharing (Cross Tree)"] += 1
                else:
                    if connection_pair in default_connections:
                        counts["Default DFMM (Child->Parent)"] += 1
                    else:
                        counts["Intra-Sharing (Skip Level)"] += 1

        total_mixing_edges = sum(counts.values())

        # 4. 結果の出力
        log("\n" + "="*30 + " EDGE COUNT ANALYSIS " + "="*30)
        log(f"Total Nodes (DFMM): {total_dfmm_nodes}")
        log(f"Number of Reagents: {num_reagents}")
        log("-" * 80)
        
        log(f"[1] Reagent Edges (Variables created by Solver)")
        log(f"    Count: {total_reagent_edges}")
        log(f"    (Note: {total_dfmm_nodes} nodes * {num_reagents} reagents)")
        
        log("-" * 80)
        
        log(f"[2] Mixing Node Edges (Connections between nodes)")
        log(f"    Total Potential Edges: {total_mixing_edges}")
        
        log(f"\n    --- Breakdown ---")
        for key in ["Default DFMM (Child->Parent)", "Intra-Sharing (Skip Level)", "Inter-Sharing (Cross Tree)"]:
            log(f"    {key:<35}: {counts[key]:>5}")
        
        log("=" * 80)
        
        total_vars = total_reagent_edges + total_mixing_edges
        log(f"Total Flow Input Variables (Reagent + Mixing): {total_vars}")
        
        if getattr(Config, "MAX_SHARED_INPUTS", None):
            log(f"\nConstraint Active: MAX_SHARED_INPUTS = {Config.MAX_SHARED_INPUTS}")

        # --- 接続詳細リストの出力 ---
        log("\n" + "="*30 + " [3] CONNECTION DETAILS " + "="*30)
        log("(Format: Destination <--- Source [Type])")
        
        # 供給先(Destination)をソート: (m, l, k)
        sorted_destinations = sorted(problem.potential_sources_map.keys())
        
        current_target = -1
        for dst_key in sorted_destinations:
            dst_m, dst_l, dst_k = dst_key
            
            # ターゲットが変わったらヘッダーを表示
            if dst_m != current_target:
                t_name = targets_config[dst_m]['name']
                log(f"\n[Target {dst_m+1}: {t_name}]")
                current_target = dst_m

            dst_name = create_dfmm_node_name(dst_m, dst_l, dst_k)
            sources = problem.potential_sources_map[dst_key]
            
            for src in sources:
                src_m, src_l, src_k = src
                src_name = create_dfmm_node_name(src_m, src_l, src_k)
                
                if src_m != dst_m:
                    edge_type = "Inter-Sharing"
                elif (dst_key, src) in default_connections:
                    edge_type = "Default DFMM"
                else:
                    edge_type = "Intra-Sharing"
                
                # 出力
                log(f"  {dst_name:<30} <--- {src_name:<30} [{edge_type}]")
            
    print(f"\nAnalysis results saved to: {output_filepath}")

if __name__ == "__main__":
    count_edges_for_analysis()