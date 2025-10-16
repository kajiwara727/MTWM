# utils/checkpoint.py
import pickle
import os
from .helpers import generate_config_hash

class CheckpointHandler:
    """
    計算の途中結果（チェックポイント）の保存と読み込みを管理するクラス。
    """
    def __init__(self, targets_config, mode, run_name, config_hash):
        """
        コンストラクタ
        Args:
            targets_config (list): 目標混合液の設定データ。
            mode (str): 最適化モード ('waste' or 'operations')。
            run_name (str): config.pyで設定された実行名。
            config_hash (str): utilsで計算された設定ハッシュ。
        """
        self.targets_config = targets_config
        self.mode = mode
        self.run_name = run_name
        self.config_hash = config_hash
        self.checkpoint_file = self._get_checkpoint_filename()
    
    def _get_checkpoint_filename(self):
        """
        設定ハッシュに基づき、一意のファイル名を生成する。
        """
        return f"checkpoint_{self.config_hash}.pkl"

    def save_checkpoint(self, analysis_results, best_value, elapsed_time):
        """
        現在の最適化状態をpickleファイルに保存する。
        """
        print(f"Checkpoint saved to {self.checkpoint_file}. Current best {self.mode}: {best_value}")
        
        data_to_save = {
            'run_name': self.run_name,
            'targets_config': self.targets_config,
            'mode': self.mode,
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
                
            current_hash_check = generate_config_hash(self.targets_config, self.mode, self.run_name)
            if self.config_hash != current_hash_check:
                print("Warning: Checkpoint file is for a different configuration. Starting fresh.")
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