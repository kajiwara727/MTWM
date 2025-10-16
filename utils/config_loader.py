# utils/config_loader.py
import config

class Config:
    """設定ファイルから値を読み込み、一元的に管理するクラス"""
    RUN_NAME = config.RUN_NAME
    MODE = config.FACTOR_EXECUTION_MODE
    OPTIMIZATION_MODE = config.OPTIMIZATION_MODE
    ENABLE_CHECKPOINTING = config.ENABLE_CHECKPOINTING
    MAX_SHARING_VOLUME = config.MAX_SHARING_VOLUME
    MAX_LEVEL_DIFF = config.MAX_LEVEL_DIFF
    MAX_MIXER_SIZE = config.MAX_MIXER_SIZE
    RANDOM_SETTINGS = config.RANDOM_SETTINGS

    @staticmethod
    def get_targets_config():
        """
        実行モードに応じて、適切なターゲット設定リストを返します。
        """
        if Config.MODE in ['auto', 'auto_permutations']:
            return config.TARGETS_FOR_AUTO_MODE
        elif Config.MODE == 'manual':
            return config.TARGETS_FOR_MANUAL_MODE
        elif Config.MODE == 'random':
            return [] # randomモードでは動的に生成するため、ここでは空
        else:
            raise ValueError(f"Unknown FACTOR_EXECUTION_MODE in config.py: '{Config.MODE}'")