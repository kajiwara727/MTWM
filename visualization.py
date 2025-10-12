# visualization.py (Corrected)
import os
import networkx as nx
import matplotlib.pyplot as plt
import z3

class SolutionVisualizer:
    """
    最適化された混合手順をグラフとして可視化するクラス。
    """
    # ... (スタイルやレイアウトの設定) ...
    STYLE_CONFIG = {
        'mix_node': {'color': '#87CEEB', 'size': 2000},
        'target_node': {'color': '#90EE90', 'size': 2000},
        'reagent_node': {'color': '#FFDAB9', 'size': 1500},
        'waste_node': {'color': 'black', 'size': 300, 'shape': 'o'},
        'default_node': {'color': 'gray', 'size': 1000},
        'edge': {'width': 1.5, 'arrowsize': 20, 'connectionstyle': 'arc3,rad=0.1'},
        'font': {'size': 10, 'weight': 'bold', 'color': 'black'},
        'edge_label_bbox': dict(facecolor='white', edgecolor='none', alpha=0.7, pad=1),
    }
    LAYOUT_CONFIG = {
        'x_gap': 6.0,
        'y_gap': 5.0,
        'tree_gap': 10.0,
        'waste_node_offset_x': 3.5,
        'waste_node_stagger_y': 0.8,
    }

    def __init__(self, problem, model):
        self.problem = problem
        self.model = model

    def visualize_solution(self, output_dir):
        """
        混合ツリーのグラフを構築し、画像として保存する。
        """
        graph, edge_volumes = self._build_graph_from_model()
        if not graph.nodes():
            print("No active nodes to visualize.")
            return

        positions = self._calculate_node_positions(graph)
        self._draw_graph(graph, positions, edge_volumes, output_dir)

    def _build_graph_from_model(self):
        """
        ソルバーのモデルから、networkxライブラリ用のグラフデータを構築する。
        ノード（混合操作、試薬）とエッジ（液体の流れ）を定義する。
        """
        G = nx.DiGraph()
        edge_volumes = {}
        for tree_idx, tree in enumerate(self.problem.forest):
            for level in sorted(tree.keys()):
                for node_idx, node in enumerate(tree[level]):
                    inputs = (node.get('reagent_vars', []) +
                              list(node.get('intra_sharing_vars', {}).values()) +
                              list(node.get('inter_sharing_vars', {}).values()))
                    total_input = self.model.eval(z3.Sum(inputs)).as_long()
                    if total_input == 0: continue

                    node_name = f"m{tree_idx}_l{level}_k{node_idx}"
                    ratio_vals = [self.model.eval(r).as_long() for r in node['ratio_vars']]
                    label = f"R{tree_idx+1}:[{':'.join(map(str, ratio_vals))}]" if level == 0 else ':'.join(map(str, ratio_vals))
                    G.add_node(node_name, label=label, level=level, target=tree_idx, type='mix')

                    self._add_waste_node(G, node, node_name)
                    self._add_reagent_edges(G, edge_volumes, node, node_name, level, tree_idx)
                    self._add_sharing_edges(G, edge_volumes, node, node_name, tree_idx)
        return G, edge_volumes
    
    def _add_waste_node(self, G, node, parent_name):
        waste_var = node.get('waste_var')
        if waste_var is not None and self.model.eval(waste_var).as_long() > 0:
            waste_node_name = f"waste_{parent_name}"
            G.add_node(waste_node_name, level=G.nodes[parent_name]['level'], target=G.nodes[parent_name]['target'], type='waste')
            G.add_edge(parent_name, waste_node_name, style='invisible')

    def _add_reagent_edges(self, G, edge_volumes, node, dest_name, level, target_idx):
        for r_idx, r_var in enumerate(node.get('reagent_vars', [])):
            r_val = self.model.eval(r_var).as_long()
            if r_val > 0:
                reagent_name = f"Reagent_{dest_name}_t{r_idx}"
                G.add_node(reagent_name, label=chr(0x2460 + r_idx), level=level + 1, target=target_idx, type='reagent')
                G.add_edge(reagent_name, dest_name, volume=r_val)
                edge_volumes[(reagent_name, dest_name)] = r_val

    def _add_sharing_edges(self, G, edge_volumes, node, dest_name, dest_tree_idx):
        sharing_sources = [(node.get('intra_sharing_vars', {}), 'intra'), (node.get('inter_sharing_vars', {}), 'inter')]
        for share_vars, s_type in sharing_sources:
            for key, w_var in share_vars.items():
                val = self.model.eval(w_var).as_long()
                if val > 0:
                    src_name = self._parse_source_node_name(key, s_type, dest_tree_idx)
                    G.add_edge(src_name, dest_name, volume=val)
                    edge_volumes[(src_name, dest_name)] = val

    def _parse_source_node_name(self, key, share_type, dest_tree_idx):
        """Correctly parses the source node name from the variable key."""
        # incoming keys are like "from_m{m}_l{l}k{k}" or "from_l{l}k{k}"
        if share_type == 'inter':
            # key: "from_m0_l1k0" -> m0_l1_k0
            key_parts = key.replace('from_m', '').split('_l')
            m_src = key_parts[0]
            lk_src = key_parts[1].split('k')
            return f"m{m_src}_l{lk_src[0]}_k{lk_src[1]}"
        else:  # intra
            # key: "from_l1k0" -> m{dest_tree_idx}_l1_k0
            key_parts = key.replace('from_l', '').split('k')
            return f"m{dest_tree_idx}_l{key_parts[0]}_k{key_parts[1]}"

    def _calculate_node_positions(self, G):
        """
        生成されたグラフのノードを見やすく配置するための座標を計算する。
        """
        pos = {}
        cfg = self.LAYOUT_CONFIG
        targets = sorted({data.get("target") for _, data in G.nodes(data=True) if data.get("target") is not None})
        current_x_offset = 0.0

        for target_idx in targets:
            sub_nodes = [n for n, d in G.nodes(data=True) if d.get("target") == target_idx and d.get("type") != "waste"]
            if not sub_nodes: continue

            max_width_in_tree = self._position_nodes_by_level(G, pos, sub_nodes, current_x_offset)
            self._position_waste_nodes(G, pos, target_idx)
            current_x_offset += max_width_in_tree + cfg['tree_gap']

        missing_nodes = [n for n in G.nodes() if n not in pos]
        if missing_nodes:
            print(f"Warning: Could not determine position for {len(missing_nodes)} node(s): {missing_nodes}")
            for n in missing_nodes: pos[n] = (0, 0)
        return pos
    
    def _position_nodes_by_level(self, G, pos, sub_nodes, x_offset):
        cfg = self.LAYOUT_CONFIG
        levels = sorted({G.nodes[n]["level"] for n in sub_nodes if 'level' in G.nodes[n]})
        max_width_in_tree = 0
        for level in levels:
            nodes_at_level = sorted([n for n in sub_nodes if G.nodes[n].get("level") == level])
            reagent_nodes = sorted({u for n in nodes_at_level for u, _ in G.in_edges(n) if G.nodes.get(u, {}).get("type") == "reagent"})
            full_row = sorted(list(set(nodes_at_level + reagent_nodes)))
            
            total_width = (len(full_row) - 1) * cfg['x_gap']
            start_x = x_offset - total_width / 2.0
            for i, node_name in enumerate(full_row):
                pos[node_name] = (start_x + i * cfg['x_gap'], -level * cfg['y_gap'])
            max_width_in_tree = max(max_width_in_tree, total_width)
        return max_width_in_tree

    def _position_waste_nodes(self, G, pos, target_idx):
        cfg = self.LAYOUT_CONFIG
        waste_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "waste" and d.get("target") == target_idx]
        
        waste_by_level = {}
        for wn in waste_nodes:
            parent = next(iter(G.predecessors(wn)), None)
            if parent and parent in pos:
                level = G.nodes[parent]['level']
                waste_by_level.setdefault(level, []).append(wn)
        
        for level, nodes in waste_by_level.items():
            sorted_nodes = sorted(nodes, key=lambda n: pos[next(iter(G.predecessors(n)))][0])
            for i, wn in enumerate(sorted_nodes):
                parent = next(iter(G.predecessors(wn)))
                px, py = pos[parent]
                pos[wn] = (px + cfg['waste_node_offset_x'], py - (i * cfg['waste_node_stagger_y']))

    def _draw_graph(self, G, pos, edge_volumes, output_dir):
        """
        計算された座標に基づき、グラフを描画し、PNGファイルとして保存する。
        """
        fig, ax = plt.subplots(figsize=(20, 12))
        cfg = self.STYLE_CONFIG
        drawable_nodes = [n for n in G.nodes() if n in pos]
        drawable_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('style') != 'invisible' and u in pos and v in pos]

        node_styles = {n: self._get_node_style(G.nodes[n]) for n in drawable_nodes if G.nodes.get(n)}
        
        for shape in {s['shape'] for s in node_styles.values()}:
            nodelist = [n for n, s in node_styles.items() if s['shape'] == shape]
            nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=nodelist, node_shape=shape,
                                   node_size=[node_styles[n]['size'] for n in nodelist],
                                   node_color=[node_styles[n]['color'] for n in nodelist],
                                   edgecolors='black', linewidths=1.0)
        
        labels = {n: d['label'] for n, d in G.nodes(data=True) if n in drawable_nodes and 'label' in d and d.get('type') != 'waste'}

        nx.draw_networkx_labels(G, pos, ax=ax, labels=labels, font_size=cfg['font']['size'], font_weight=cfg['font']['weight'])
        nx.draw_networkx_edges(G, pos, edgelist=drawable_edges, ax=ax, node_size=cfg['mix_node']['size'], arrowstyle='->',
                               arrowsize=cfg['edge']['arrowsize'], width=cfg['edge']['width'], connectionstyle=cfg['edge']['connectionstyle'])
        
        edge_labels = {k: v for k, v in edge_volumes.items() if k in drawable_edges}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=cfg['font']['size'],
                                     font_color=cfg['font']['color'], bbox=cfg['edge_label_bbox'])

        ax.set_title("Mixing Tree Visualization", fontsize=18, pad=20)
        ax.axis('off')
        plt.tight_layout()
        image_path = os.path.join(output_dir, 'mixing_tree_visualization.png')
        try:
            plt.savefig(image_path, dpi=300, bbox_inches='tight')
            print(f"Graph visualization saved to: {image_path}")
        except Exception as e:
            print(f"Error saving visualization image: {e}")
        finally:
            plt.close(fig)

    def _get_node_style(self, node_data):
        cfg = self.STYLE_CONFIG
        node_type = node_data.get('type')
        if node_type == 'mix': style = cfg['target_node'] if node_data.get('level') == 0 else cfg['mix_node']
        elif node_type == 'reagent': style = cfg['reagent_node']
        elif node_type == 'waste': style = cfg['waste_node']
        else: style = cfg['default_node']
        return {'color': style['color'], 'size': style['size'], 'shape': style.get('shape', 'o')}