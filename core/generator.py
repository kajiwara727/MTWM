import random
import itertools
import copy
from core.algorithm.dfmm import find_factors_for_sum, generate_unique_permutations
from core.algorithm.math_utils import generate_random_ratios

class RandomScenarioGenerator:
    def __init__(self, config):
        self.config = config

    def generate_batch_configs(self, num_runs):
        generated_configs = []
        for i in range(num_runs):
            specs = self._determine_specs()
            config = self._create_run_config(i, specs)
            if config: generated_configs.append(config)
        return generated_configs

    def _determine_specs(self):
        seq = self.config.RANDOM_S_RATIO_SUM_SEQUENCE
        cands = self.config.RANDOM_S_RATIO_SUM_CANDIDATES
        n_targets = self.config.RANDOM_N_TARGETS
        
        if seq and len(seq) == n_targets: return seq
        elif cands: return [random.choice(cands) for _ in range(n_targets)]
        else: return [self.config.RANDOM_S_RATIO_SUM_DEFAULT] * n_targets

    def _create_run_config(self, run_idx, specs):
        targets_list = []
        for j, spec in enumerate(specs):
            base_sum = spec.get('base_sum', 0) if isinstance(spec, dict) else int(spec)
            multiplier = spec.get('multiplier', 1) if isinstance(spec, dict) else 1
            if base_sum <= 0: return None
            
            try:
                base_ratios = generate_random_ratios(self.config.RANDOM_T_REAGENTS, base_sum)
                ratios = [r * multiplier for r in base_ratios]
                base_factors = find_factors_for_sum(base_sum, self.config.MAX_MIXER_SIZE)
                mult_factors = find_factors_for_sum(multiplier, self.config.MAX_MIXER_SIZE)
                if not base_factors or not mult_factors: return None
                
                factors = sorted(base_factors + mult_factors, reverse=True)
                targets_list.append({
                    'name': f"RandomTarget_{run_idx+1}_{j+1}",
                    'ratios': ratios, 'factors': factors
                })
            except ValueError: return None
            
        return {'run_name': f"run_{run_idx+1}", 'targets': targets_list}

class PermutationScenarioGenerator:
    def __init__(self, config):
        self.config = config

    def generate_permutations(self, base_config):
        target_perms_options = []
        for target in base_config:
            base_factors = find_factors_for_sum(sum(target['ratios']), self.config.MAX_MIXER_SIZE)
            if not base_factors: raise ValueError(f"No factors for {target['name']}")
            target_perms_options.append(generate_unique_permutations(base_factors))

        scenarios = []
        for i, combo in enumerate(itertools.product(*target_perms_options)):
            temp_config = copy.deepcopy(base_config)
            name_parts = []
            for j, target in enumerate(temp_config):
                target['factors'] = list(combo[j])
                name_parts.append("_".join(map(str, combo[j])))
            
            run_name = f"run_{i+1}_{'-'.join(name_parts)}"
            scenarios.append({'run_name': run_name, 'targets': temp_config})
        return scenarios