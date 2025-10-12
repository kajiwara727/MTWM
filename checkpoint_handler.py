# checkpoint_handler.py
import pickle
import os
import json
import hashlib

class CheckpointHandler:
    """
    計算の途中結果（チェックポイント）の保存と読み込みを管理するクラス。
    """
    def __init__(self, targets_config):
        """
        コンストラクタ
        Args:
            targets_config (list): 目標混合液の設定データ。
        """
        self.targets_config = targets_config
        self.checkpoint_file = self._get_checkpoint_filename()

    def _get_checkpoint_filename(self):
        """
        設定データ（targets_config）を元にMD5ハッシュを計算し、
        設定ごとに一意のチェックポイントファイル名を生成する。
        """
        config_str = json.dumps(self.targets_config, sort_keys=True)
        hasher = hashlib.md5()
        hasher.update(config_str.encode('utf-8'))
        config_hash = hasher.hexdigest()
        return f"checkpoint_{config_hash}.pkl"

    def save_checkpoint(self, analysis_results, best_waste, elapsed_time):
        """
        現在の最適化状態（解析結果、最小廃棄物量など）をpickleファイルに保存する。
        """
        print(f"Checkpoint saved to {self.checkpoint_file}. Current best waste: {best_waste}")
        
        data_to_save = {
            'targets_config': self.targets_config,
            'analysis_results': analysis_results,
            'best_waste': best_waste,
            'elapsed_time': elapsed_time
        }
        
        with open(self.checkpoint_file, 'wb') as f:
            pickle.dump(data_to_save, f)

    def load_checkpoint(self):
        """
        チェックポイントファイルを読み込み、以前の計算状態を復元する。
        ファイルが存在しない、または破損している場合は最初から計算を始める。
        """
        if not os.path.exists(self.checkpoint_file):
            print("No checkpoint file found for this configuration. Starting fresh.")
            return None, None
            
        try:
            with open(self.checkpoint_file, 'rb') as f:
                data = pickle.load(f)
                
            if data['targets_config'] != self.targets_config:
                print("Warning: Checkpoint file is for a different configuration. Starting fresh.")
                return None, None
                
            print(f"Checkpoint loaded from {self.checkpoint_file}. Resuming with best waste < {data['best_waste']}")
            return data['best_waste'], data['analysis_results']

        except (EOFError, KeyError):
            print("Warning: Checkpoint file is corrupted. Starting fresh.")
            self.delete_checkpoint()
            return None, None

    def delete_checkpoint(self):
        """
        現在の設定に対応するチェックポイントファイルを削除する。
        （解が見つからなかった場合などに使用）
        """
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            print(f"Removed checkpoint file: {self.checkpoint_file}")