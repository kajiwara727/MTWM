# reporting/visualizer.py
import os
import networkx as nx
import matplotlib.pyplot as plt
import z3

class SolutionVisualizer:
    """最適化された混合手順をグラフとして可視化するクラス"""
    
    STYLE_CONFIG = {
        'mix_node': {'color': '#87CEEB', 'size': 2000},
        'target_node': {'color': '#90EE90', 'size': 2000},
        'reagent_node': {'color': '#FFDAB9', 'size': 1500},
        'waste_node': {'color': 'black', 'size': 300, 'shape': 'o'},
        'default_node': {'color': 'gray', 'size': 1000},
        'edge': {'width': 1.5, 'arrowsize': 20, 'connectionstyle': 'arc3,rad=0.1'},
        'font': {'font_size': 10, 'font_weight': 'bold', 'font_color': 'black'},
        'edge_label_bbox': dict(facecolor='white', edgecolor='none', alpha=0.7, pad=1),
    }
    LAYOUT_CONFIG = {
        'x_gap': 6.0, 'y_gap': 5.0, 'tree_gap': 10.0,
        'waste_node_offset_x': 3.5, 'waste_node_stagger_y': 0.8,
    }

    def __init__(self, problem, model):
        self.problem = problem
        self.model = model

    def visualize_solution(self, output_dir):
        """混合ツリーのグラフを構築し、画像として保存する"""
        graph, edge_volumes = self._build_graph_from_model()
        if not graph.nodes():
            print("No active nodes to visualize.")
            return

        positions = self._calculate_node_positions(graph)
        self._draw_graph(graph, positions, edge_volumes, output_dir)

    def _build_graph_from_model(self):
        """ソルバーのモデルから、networkx用のグラフデータを構築する"""
        G = nx.DiGraph()
        edge_volumes = {}
        
        for m, l, k, node, total_input in self._iterate_active_nodes():
            node_name = f"m{m}_l{l}_k{k}"
            ratio_vals = [self.model.eval(r).as_long() for r in node['ratio_vars']]
            label = f"R{m+1}:[{':'.join(map(str, ratio_vals))}]" if l == 0 else ':'.join(map(str, ratio_vals))
            
            G.add_node(node_name, label=label, level=l, target=m, type='mix')
            
            self._add_waste_node(G, node, node_name)
            self._add_reagent_edges(G, edge_volumes, node, node_name, l, m)
            self._add_sharing_edges(G, edge_volumes, node, node_name, m)
            
        return G, edge_volumes

    def _iterate_active_nodes(self):
        """モデルで実際に使用されているノードのみを巡回するジェネレータ"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                for k, node in enumerate(nodes):
                    inputs = (node.get('reagent_vars', []) +
                              list(node.get('intra_sharing_vars', {}).values()) +
                              list(node.get('inter_sharing_vars', {}).values()))
                    total_input = self.model.eval(z3.Sum(inputs)).as_long()
                    if total_input > 0:
                        yield m, l, k, node, total_input
    
    def _add_waste_node(self, G, node, parent_name):
        """ノードに廃棄物があれば、グラフに廃棄ノードを追加する"""
        waste_var = node.get('waste_var')
        if waste_var is not None and self.model.eval(waste_var).as_long() > 0:
            waste_node_name = f"waste_{parent_name}"
            G.add_node(waste_node_name, level=G.nodes[parent_name]['level'], target=G.nodes[parent_name]['target'], type='waste')
            G.add_edge(parent_name, waste_node_name, style='invisible')

    def _add_reagent_edges(self, G, edge_volumes, node, dest_name, level, target_idx):
        """試薬から混合ノードへのエッジを追加する"""
        for r_idx, r_var in enumerate(node.get('reagent_vars', [])):
            if (r_val := self.model.eval(r_var).as_long()) > 0:
                reagent_name = f"Reagent_{dest_name}_t{r_idx}"
                G.add_node(reagent_name, label=chr(0x2460 + r_idx), level=level + 1, target=target_idx, type='reagent')
                G.add_edge(reagent_name, dest_name, volume=r_val)
                edge_volumes[(reagent_name, dest_name)] = r_val

    def _add_sharing_edges(self, G, edge_volumes, node, dest_name, dest_tree_idx):
        """中間液の共有を表すエッジを追加する"""
        all_sharing = {**node.get('intra_sharing_vars',{}), **node.get('inter_sharing_vars',{})}
        for key, w_var in all_sharing.items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                src_name = self._parse_source_node_name(key, dest_tree_idx)
                G.add_edge(src_name, dest_name, volume=val)
                edge_volumes[(src_name, dest_name)] = val

    def _parse_source_node_name(self, key, dest_tree_idx):
        """共有変数のキー文字列から供給元ノード名を復元する"""
        key = key.replace('from_', '')
        if key.startswith('m'):
            m_src, lk_src = key.split('_l')
            l_src, k_src = lk_src.split('k')
            return f"{m_src}_l{l_src}_k{k_src}"
        else:
            l_src, k_src = key.split('k')
            return f"m{dest_tree_idx}_l{l_src.replace('l','')}_k{k_src}"

    def _calculate_node_positions(self, G):
        """ノードを見やすく配置するための座標を計算する"""
        pos = {}
        targets = sorted({d["target"] for n, d in G.nodes(data=True) if d.get("target") is not None})
        current_x_offset = 0.0

        for target_idx in targets:
            sub_nodes = [n for n, d in G.nodes(data=True) if d.get("target") == target_idx and d.get("type") != "waste"]
            if not sub_nodes: continue

            max_width = self._position_nodes_by_level(G, pos, sub_nodes, current_x_offset)
            self._position_waste_nodes(G, pos, target_idx)
            current_x_offset += max_width + self.LAYOUT_CONFIG['tree_gap']

        return pos
    
    def _position_nodes_by_level(self, G, pos, sub_nodes, x_offset):
        """レベルごとにノードのX,Y座標を決定する"""
        max_width_in_tree = 0
        levels = sorted({G.nodes[n]["level"] for n in sub_nodes})
        
        for level in levels:
            nodes_at_level = [n for n in sub_nodes if G.nodes[n].get("level") == level]
            reagent_nodes = {u for n in nodes_at_level for u, _ in G.in_edges(n) if G.nodes.get(u, {}).get("type") == "reagent"}
            full_row = sorted(list(set(nodes_at_level) | reagent_nodes))
            
            total_width = (len(full_row) - 1) * self.LAYOUT_CONFIG['x_gap']
            start_x = x_offset - total_width / 2.0
            
            for i, node_name in enumerate(full_row):
                pos[node_name] = (start_x + i * self.LAYOUT_CONFIG['x_gap'], -level * self.LAYOUT_CONFIG['y_gap'])
            max_width_in_tree = max(max_width_in_tree, total_width)
            
        return max_width_in_tree

    def _position_waste_nodes(self, G, pos, target_idx):
        """廃棄ノードを親ノードの右側に配置する"""
        waste_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "waste" and d.get("target") == target_idx]
        for wn in waste_nodes:
            parent = next(iter(G.predecessors(wn)), None)
            if parent and parent in pos:
                px, py = pos[parent]
                pos[wn] = (px + self.LAYOUT_CONFIG['waste_node_offset_x'], py)

    def _draw_graph(self, G, pos, edge_volumes, output_dir):
        """計算された座標に基づき、グラフを描画しPNGファイルとして保存する"""
        fig, ax = plt.subplots(figsize=(20, 12))
        
        drawable_nodes = [n for n in G.nodes() if n in pos]
        drawable_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('style') != 'invisible' and u in pos and v in pos]

        node_styles = {n: self._get_node_style(G.nodes[n]) for n in drawable_nodes}
        
        for shape in {s['shape'] for s in node_styles.values()}:
            nodelist = [n for n, s in node_styles.items() if s['shape'] == shape]
            nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=nodelist, node_shape=shape,
                                   node_size=[node_styles[n]['size'] for n in nodelist],
                                   node_color=[node_styles[n]['color'] for n in nodelist],
                                   edgecolors='black', linewidths=1.0)
        
        labels = {n: d['label'] for n, d in G.nodes(data=True) if n in drawable_nodes and 'label' in d and d.get('type') != 'waste'}
        nx.draw_networkx_labels(G, pos, ax=ax, labels=labels, **self.STYLE_CONFIG['font'])
        nx.draw_networkx_edges(G, pos, edgelist=drawable_edges, ax=ax, node_size=self.STYLE_CONFIG['mix_node']['size'], **self.STYLE_CONFIG['edge'])
        
        edge_labels = {k: v for k, v in edge_volumes.items() if k in drawable_edges}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                     font_size=self.STYLE_CONFIG['font']['font_size'],
                                     font_color=self.STYLE_CONFIG['font']['font_color'],
                                     bbox=self.STYLE_CONFIG['edge_label_bbox'])

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
        """ノードのデータに基づいてスタイル辞書を返す"""
        cfg = self.STYLE_CONFIG
        node_type = node_data.get('type')
        if node_type == 'mix': style = cfg['target_node'] if node_data.get('level') == 0 else cfg['mix_node']
        elif node_type == 'reagent': style = cfg['reagent_node']
        elif node_type == 'waste': style = cfg['waste_node']
        else: style = cfg['default_node']
        return {'color': style['color'], 'size': style['size'], 'shape': style.get('shape', 'o')}