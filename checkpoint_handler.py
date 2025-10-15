# checkpoint_handler.py (修正版)
import pickle
import os
import json
import hashlib

class CheckpointHandler:
    """
    計算の途中結果（チェックポイント）の保存と読み込みを管理するクラス。
    """
    # --- ここからが修正部分 ---
    def __init__(self, targets_config, mode="waste"):
        """
        コンストラクタ
        Args:
            targets_config (list): 目標混合液の設定データ。
            mode (str): 最適化モード ('waste' or 'operations')
        """
        self.targets_config = targets_config
        self.mode = mode
        self.checkpoint_file = self._get_checkpoint_filename()
    # --- ここまでが修正部分 ---

    def _get_checkpoint_filename(self):
        """
        設定データとモードを元にハッシュを計算し、一意のファイル名を生成する。
        """
        # --- ここからが修正部分 ---
        # ハッシュの元データにモードを追加
        config_str = json.dumps(self.targets_config, sort_keys=True) + self.mode
        # --- ここまでが修正部分 ---
        hasher = hashlib.md5()
        hasher.update(config_str.encode('utf-8'))
        config_hash = hasher.hexdigest()
        return f"checkpoint_{config_hash}.pkl"

    def save_checkpoint(self, analysis_results, best_value, elapsed_time):
        """
        現在の最適化状態をpickleファイルに保存する。
        """
        print(f"Checkpoint saved to {self.checkpoint_file}. Current best {self.mode}: {best_value}")
        
        data_to_save = {
            'targets_config': self.targets_config,
            'mode': self.mode, # モードも保存
            'analysis_results': analysis_results,
            'best_value': best_value,
            'elapsed_time': elapsed_time
        }
        
        with open(self.checkpoint_file, 'wb') as f:
            pickle.dump(data_to_save, f)

    def load_checkpoint(self):
        """
        チェックポイントファイルを読み込み、以前の計算状態を復元する。
        """
        if not os.path.exists(self.checkpoint_file):
            print("No checkpoint file found for this configuration. Starting fresh.")
            return None, None
            
        try:
            with open(self.checkpoint_file, 'rb') as f:
                data = pickle.load(f)
                
            # 設定とモードが一致するか確認
            if data['targets_config'] != self.targets_config or data.get('mode') != self.mode:
                print("Warning: Checkpoint file is for a different configuration/mode. Starting fresh.")
                return None, None
                
            print(f"Checkpoint loaded from {self.checkpoint_file}. Resuming with best {self.mode} < {data['best_value']}")
            return data['best_value'], data['analysis_results']

        except (EOFError, KeyError):
            print("Warning: Checkpoint file is corrupted. Starting fresh.")
            self.delete_checkpoint()
            return None, None

    def delete_checkpoint(self):
        """
        現在の設定に対応するチェックポイントファイルを削除する。
        """
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            print(f"Removed checkpoint file: {self.checkpoint_file}")