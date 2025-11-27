import os
from abc import ABC, abstractmethod
from core.execution import ExecutionEngine

class BaseRunner(ABC):
    def __init__(self, config):
        self.config = config
        self.engine = ExecutionEngine(config)

    @abstractmethod
    def run(self): pass

    def _get_unique_output_directory_name(self, config_hash, base_name_prefix):
        base_name = f"{base_name_prefix}_{config_hash[:8]}"
        output_dir = base_name
        counter = 1
        while os.path.isdir(output_dir):
            output_dir = f"{base_name}_{counter}"
            counter += 1
        return output_dir