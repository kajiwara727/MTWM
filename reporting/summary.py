# reporting/summary.py
import os

def save_random_run_summary(results_list, output_dir):
    """
    ランダムモードで実行された全シミュレーション結果の概要を単一ファイルに保存する。
    """
    filepath = os.path.join(output_dir, "_random_runs_summary.txt")
    
    content = [
        "==================================================",
        "      Summary of All Random Simulation Runs       ",
        "==================================================",
        f"\nTotal simulations executed: {len(results_list)}\n"
    ]

    for result in results_list:
        content.append("-" * 50)
        content.append(f"Run Name: {result['run_name']}")
        content.append(f"  -> Execution Time: {result['elapsed_time']:.2f} seconds")
        
        if result['final_value'] is not None:
            content.append(f"  -> Minimum Waste Found: {result['final_value']}")
            content.append(f"  -> Total Operations: {result['total_operations']}")
            content.append(f"  -> Total Reagent Units: {result['total_reagents']}")
        else:
            content.append("  -> No solution was found for this configuration.")

        content.append("  -> Target Configurations:")
        for i, config in enumerate(result['config']):
            ratios_str = ', '.join(map(str, config['ratios']))
            content.append(f"    - Target {i+1}: Ratios = [{ratios_str}]")
        content.append("")

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        print("\n" + "="*60)
        print(f"SUCCESS: A summary of all random runs has been saved to:")
        print(f"  -> {filepath}")
        print("="*60)
    except IOError as e:
        print(f"\nError saving random run summary file: {e}")