import os
import random
import json
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum
from utils.helpers import generate_random_ratios
from reporting.summary import save_random_run_summary

class RandomRunner(BaseRunner):
    """
    'random' モードの実行を担当するクラス。
    config.pyのRANDOM_SETTINGSに基づき、ランダムなシナリオを複数回実行します。
    """
    def run(self):
        # 1. Configからランダム実行用の設定を読み込む
        k_runs = self.config.RANDOM_K_RUNS          # 実行回数 (例: 100)
        num_targets = self.config.RANDOM_N_TARGETS   # 1回あたりのターゲット数 (例: 3)
        num_reagents = self.config.RANDOM_T_REAGENTS # 試薬の種類の数 (例: 3)
        
        # 比率の合計値 (S_ratio_sum) を決めるルール
        sequence = self.config.RANDOM_S_RATIO_SUM_SEQUENCE     # 優先度1: 固定シーケンス
        candidates = self.config.RANDOM_S_RATIO_SUM_CANDIDATES # 優先度2: 候補からランダム
        default_sum = self.config.RANDOM_S_RATIO_SUM_DEFAULT   # 優先度3: デフォルト値
        
        run_name_prefix = self.config.RUN_NAME # config.pyのRUN_NAME (例: "ExperimentA")

        print(f"Preparing to run {k_runs} random simulations...")
        
        # 2. ベースとなる出力ディレクトリ名を決定
        
        # --- フォルダ名用の比率合計モード文字列を生成 ---
        ratio_sum_mode_str = ""
        if sequence and isinstance(sequence, list) and len(sequence) > 0:
            # 優先度1: 固定シーケンス
            # (multiplier は無視し、base_sum か数値のみを抽出)
            seq_parts = []
            for spec in sequence:
                if isinstance(spec, dict):
                    # 辞書の場合は 'base_sum' の値を取得
                    seq_parts.append(str(spec.get("base_sum", "Err")))
                elif isinstance(spec, (int, float)):
                    # 数値の場合はそのまま使用
                    seq_parts.append(str(spec))
            # 例: "Seq[18_18_24]"
            ratio_sum_mode_str = f"Seq[{'_'.join(seq_parts)}]"
            
        elif candidates and isinstance(candidates, list) and len(candidates) > 0:
            # 優先度2: 候補リストからランダム選択
            # 重複を除きソートして分かりやすくする (例: "Cand[18_24_30]")
            cand_parts = sorted(list(set(candidates))) 
            ratio_sum_mode_str = f"Cand[{'_'.join(map(str, cand_parts))}]"
            
        else:
            # 優先度3: デフォルト値 (例: "Def[12]")
            ratio_sum_mode_str = f"Def[{default_sum}]"
        # --- ここまで ---

        # (RUN_NAME)-(濃度比)-(目標濃度数)-(試薬数)-(実行数) の順序
        # (例: "ExperimentA-Def[12]-3targets-3reagents-100runs")
        base_run_name = f"{run_name_prefix}-{ratio_sum_mode_str}-{num_targets}targets-{num_reagents}reagents-{k_runs}runs"
        
        base_output_dir = self._get_unique_output_directory_name("random", base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All random run results will be saved under: '{base_output_dir}/'")

        all_run_results = []
        saved_configs = [] 

        for i in range(k_runs):
            print(f"\n{'='*20} Running Random Simulation {i+1}/{k_runs} {'='*20}")

            # --- 混合比和の決定ロジック (configから直接読み込む) ---
            sequence = self.config.RANDOM_S_RATIO_SUM_SEQUENCE
            candidates = self.config.RANDOM_S_RATIO_SUM_CANDIDATES
            n_targets = self.config.RANDOM_N_TARGETS
            
            if sequence and isinstance(sequence, list) and len(sequence) == n_targets:
                mode = 'sequence'
                specs_for_run = sequence
                print(f"-> Mode: Fixed Sequence. Using S_ratio_sum specifications: {specs_for_run}")
            
            elif candidates and isinstance(candidates, list) and len(candidates) > 0:
                mode = 'random_candidates'
                specs_for_run = [random.choice(candidates) for _ in range(n_targets)]
                print(f"-> Mode: Random per Target. Generated S_ratio_sum specifications for this run: {specs_for_run}")

            else:
                mode = 'default'
                default_sum = self.config.RANDOM_S_RATIO_SUM_DEFAULT
                specs_for_run = [default_sum] * n_targets
                print(f"-> Mode: Default. Using single S_ratio_sum '{default_sum}' for all targets.")
            
            temp_config = []
            valid_run = True
            for j in range(n_targets):
                spec = specs_for_run[j]
                
                # --- spec（設定値）を解析して、base_sumとmultiplierを決定 ---
                base_sum = 0
                multiplier = 1
                
                if isinstance(spec, dict):
                    base_sum = spec.get('base_sum', 0)
                    multiplier = spec.get('multiplier', 1)
                elif isinstance(spec, (int, float)):
                    base_sum = int(spec)
                    multiplier = 1
                else:
                    print(f"Warning: Invalid spec format for target {j+1}: {spec}. Skipping this run.")
                    valid_run = False
                    break
                
                if base_sum <= 0:
                    print(f"Warning: Invalid base_sum ({base_sum}) for target {j+1}. Skipping this run.")
                    valid_run = False
                    break
                
                try:
                    # 1. 基本比率を生成 (configから試薬数を読み込む)
                    base_ratios = generate_random_ratios(self.config.RANDOM_T_REAGENTS, base_sum)
                    # 2. 倍率を適用して最終的な比率を計算
                    ratios = [r * multiplier for r in base_ratios]
                    
                    print(f"  -> Target {j+1}: Spec={spec}")
                    print(f"     Base ratios (sum={base_sum}): {base_ratios} -> Multiplied by {multiplier} -> Final Ratios (sum={sum(ratios)}): {ratios}")
                except ValueError as e:
                    print(f"Warning: Could not generate base ratios for sum {base_sum}. Error: {e}. Skipping this run.")
                    valid_run = False
                    break

                # 3. factorsを「base_sumの因数」と「multiplierの因数」の合成で生成
                base_factors = find_factors_for_sum(base_sum, self.config.MAX_MIXER_SIZE)
                if base_factors is None:
                    print(f"Warning: Could not determine factors for base_sum {base_sum}. Skipping this run.")
                    valid_run = False
                    break

                multiplier_factors = find_factors_for_sum(multiplier, self.config.MAX_MIXER_SIZE)
                if multiplier_factors is None:
                    print(f"Warning: Could not determine factors for multiplier {multiplier}. Skipping this run.")
                    valid_run = False
                    break
                
                factors = base_factors + multiplier_factors
                
                factors.sort(reverse=True)
                
                print(f"     Factors for base ({base_sum}): {base_factors} + Factors for multiplier ({multiplier}): {multiplier_factors} -> Sorted Final Factors: {factors}")

                temp_config.append({
                    'name': f"RandomTarget_{i+1}_{j+1}",
                    'ratios': ratios,
                    'factors': factors
                })

            if not valid_run or not temp_config:
                continue

            run_name = f"run_{i+1}"
            output_dir = os.path.join(base_output_dir, run_name)

            final_waste, exec_time, total_ops, total_reagents = self._run_single_optimization(temp_config, output_dir, run_name)

            all_run_results.append({
                'run_name': run_name, 'config': temp_config,
                'final_value': final_waste, 'elapsed_time': exec_time,
                'total_operations': total_ops, 'total_reagents': total_reagents
            })

            saved_configs.append({
                'run_name': run_name,
                'targets': temp_config
            })

        save_random_run_summary(all_run_results, base_output_dir)
        
        config_log_path = os.path.join(base_output_dir, "random_configs.json")
        with open(config_log_path, 'w', encoding='utf-8') as f:
            json.dump(saved_configs, f, indent=4) 
        print(f"\nAll generated configurations saved to: {config_log_path}")