# main.py
from utils.config_loader import Config
from runners import RUNNER_MAP

def main():
    mode = Config.MODE
    print(f"--- Factor Determination Mode: {mode.upper()} ---")
    
    runner_class = RUNNER_MAP.get(mode)
    if runner_class:
        runner_class(Config).run()
    else:
        raise ValueError(f"Unknown Mode: '{mode}'.")

if __name__ == "__main__":
    main()