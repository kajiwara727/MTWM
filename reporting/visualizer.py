# reporting/visualizer.py
import os
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from utils import create_dfmm_node_name, parse_sharing_key

class SolutionVisualizer:
    """
    ソルバーの解（OrToolsSolutionModel）を読み取り、networkxでグラフを構築し、
    matplotlibで可視化（PNG画像として保存）するクラス。
    """
    STYLE_CONFIG = {
        "mix_node": {"color": "#87CEEB", "size": 2000},
        "target_node": {"color": "#90EE90", "size": 2000},
        "mix_peer_node": {"color": "#FFB6C1", "size": 1800},
        "reagent_node": {"color": "#FFDAB9", "size": 1500},
        "waste_node": {"color": "black", "size": 300, "shape": "o"},
        "default_node": {"color": "gray", "size": 1000},
        "edge": {"width": 1.5, "arrowsize": 20, "connectionstyle": "arc3,rad=0.1"},
        "font": {"font_size": 10, "font_weight": "bold", "font_color": "black"},
        "edge_label_bbox": dict(facecolor="white", edgecolor="none", alpha=0.7, pad=1),
        "edge_colormap": "viridis",
    }
    LAYOUT_CONFIG = {
        "x_gap": 6.0, "y_gap": 5.0, "tree_gap": 10.0,
        "waste_node_offset_x": 3.5, "waste_node_stagger_y": 0.8,
    }

    def __init__(self, problem, model):
        self.problem = problem
        self.model = model

    def visualize_solution(self, output_dir):
        graph, edge_volumes = self._build_graph_from_model()
        if not graph.nodes():
            print("No active nodes to visualize.")
            return
        positions = self._calculate_node_positions(graph)
        self._draw_graph(graph, positions, edge_volumes, output_dir)

    def _build_graph_from_model(self):
        G = nx.DiGraph()
        edge_volumes = {}
        
        # 1. Active DFMM nodes
        for target_idx, tree_vars in enumerate(self.model.forest_vars):
            for level, node_vars_list in tree_vars.items():
                for node_idx, node_vars in enumerate(node_vars_list):
                    
                    total_input = self.model._v(node_vars["total_input_var"])
                    if total_input <= 0: continue
                    
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    ratio_vals = [self.model._v(r) for r in node_vars["ratio_vars"]]
                    label = f"R{target_idx+1}:[{':'.join(map(str, ratio_vals))}]" if level == 0 else ":".join(map(str, ratio_vals))
                    
                    G.add_node(node_name, label=label, level=level, target=target_idx, type="mix")
                    self._add_waste_node(G, node_vars, node_name)
                    self._add_reagent_edges(G, edge_volumes, node_vars, node_name, level, target_idx)
                    self._add_sharing_edges(G, edge_volumes, node_vars, node_name, target_idx)

        # 2. Peer nodes (MTWMでは現状空だが、拡張性のため維持)
        for i, peer_vars in enumerate(self.model.peer_vars):
            if self.model._v(peer_vars["total_input_var"]) <= 0: continue
            
            node_name = peer_vars["name"]
            ratio_vals = [self.model._v(r) for r in peer_vars["ratio_vars"]]
            src_a = self.problem.peer_nodes[i]["source_a_id"]
            level = (src_a[1] + self.problem.peer_nodes[i]["source_b_id"][1]) / 2.0 - 0.5
            
            G.add_node(node_name, label=f"R-Mix\n[{':'.join(map(str, ratio_vals))}]", level=level, target=src_a[0], type="mix_peer")
            self._add_waste_node(G, peer_vars, node_name)
            
            for key in ["from_a", "from_b"]:
                if (val := self.model._v(peer_vars["input_vars"][key])) > 0:
                    src_id = self.problem.peer_nodes[i]["source_a_id" if key == "from_a" else "source_b_id"]
                    src_name = create_dfmm_node_name(*src_id)
                    G.add_edge(src_name, node_name, volume=val)
                    edge_volumes[(src_name, node_name)] = val

        return G, edge_volumes

    def _add_waste_node(self, G, node_vars, parent):
        # [MODIFIED] waste_var が存在する場合のみ値を取得
        waste_var = node_vars.get("waste_var")
        if waste_var is not None and (waste := self.model._v(waste_var)) > 0:
            wn = f"waste_{parent}"
            G.add_node(wn, level=G.nodes[parent]["level"], target=G.nodes[parent]["target"], type="waste")
            G.add_edge(parent, wn, style="invisible")

    def _add_reagent_edges(self, G, edge_volumes, node_vars, dest, level, target):
        for r_idx, r_var in enumerate(node_vars.get("reagent_vars", [])):
            if (val := self.model._v(r_var)) > 0:
                rn = f"Reagent_{dest}_t{r_idx}"
                G.add_node(rn, label=chr(0x2460 + r_idx), level=level+1, target=target, type="reagent")
                G.add_edge(rn, dest, volume=val)
                edge_volumes[(rn, dest)] = val

    def _add_sharing_edges(self, G, edge_volumes, node_vars, dest, target):
        all_sharing = {**node_vars.get("intra_sharing_vars", {}), **node_vars.get("inter_sharing_vars", {})}
        for key, var in all_sharing.items():
            if (val := self.model._v(var)) > 0:
                src = self._parse_src_name(key, target)
                G.add_edge(src, dest, volume=val)
                edge_volumes[(src, dest)] = val

    def _parse_src_name(self, key, target):
        key = key.replace("from_", "")
        try:
            parsed = parse_sharing_key(key)
            if parsed["type"] == "PEER": return self.problem.peer_nodes[parsed["idx"]]["name"]
            elif parsed["type"] == "DFMM": return create_dfmm_node_name(parsed["target_idx"], parsed["level"], parsed["node_idx"])
            elif parsed["type"] == "INTRA": return create_dfmm_node_name(target, parsed["level"], parsed["node_idx"])
        except: return f"Unknown_{key}"

    def _calculate_node_positions(self, G):
        pos = {}
        targets = sorted({d["target"] for n, d in G.nodes(data=True) if d.get("target") is not None})
        x_offset = 0.0
        for t in targets:
            sub = [n for n, d in G.nodes(data=True) if d.get("target") == t and d.get("type") != "waste"]
            if not sub: continue
            width = self._pos_level(G, pos, sub, x_offset)
            self._pos_waste(G, pos, t)
            x_offset += width + self.LAYOUT_CONFIG["tree_gap"]
        return pos

    def _pos_level(self, G, pos, nodes, x_off):
        max_w = 0
        levels = sorted({G.nodes[n]["level"] for n in nodes})
        for l in levels:
            row_nodes = [n for n in nodes if G.nodes[n]["level"] == l]
            reagents = {u for n in row_nodes for u, _ in G.in_edges(n) if G.nodes.get(u, {}).get("type") == "reagent"}
            row = sorted(list(set(row_nodes) | reagents))
            width = (len(row) - 1) * self.LAYOUT_CONFIG["x_gap"]
            start = x_off - width / 2.0
            for i, n in enumerate(row):
                pos[n] = (start + i * self.LAYOUT_CONFIG["x_gap"], -l * self.LAYOUT_CONFIG["y_gap"])
            max_w = max(max_w, width)
        return max_w

    def _pos_waste(self, G, pos, t):
        for n in [n for n, d in G.nodes(data=True) if d.get("type") == "waste" and d.get("target") == t]:
            p = next(iter(G.predecessors(n)), None)
            if p and p in pos: pos[n] = (pos[p][0] + self.LAYOUT_CONFIG["waste_node_offset_x"], pos[p][1])

    def _draw_graph(self, G, pos, vols, out):
        fig, ax = plt.subplots(figsize=(20, 12))
        draw_nodes = [n for n in G.nodes() if n in pos]
        draw_edges = [(u,v) for u,v,d in G.edges(data=True) if d.get('style')!='invisible' and u in pos and v in pos]
        
        if not draw_nodes:
             plt.close(fig)
             return

        styles = {n: self._style(G.nodes[n]) for n in draw_nodes}
        for s in {v['shape'] for v in styles.values()}:
            nl = [n for n, v in styles.items() if v['shape'] == s]
            nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=nl, node_shape=s, 
                                   node_size=[styles[n]['size'] for n in nl], 
                                   node_color=[styles[n]['color'] for n in nl], 
                                   edgecolors='black')
        
        labels = {n: d['label'] for n,d in G.nodes(data=True) if n in draw_nodes and 'label' in d and d['type']!='waste'}
        nx.draw_networkx_labels(G, pos, ax=ax, labels=labels, **self.STYLE_CONFIG["font"])

        if vols:
            vals = [vols.get(e, 0) for e in draw_edges]
            if vals:
                norm = mcolors.Normalize(vmin=min(vals), vmax=max(vals) if max(vals) > min(vals) else min(vals)+1)
                cmap = plt.get_cmap(self.STYLE_CONFIG["edge_colormap"])
                cols = [cmap(norm(v)) for v in vals]
                nx.draw_networkx_edges(G, pos, edgelist=draw_edges, ax=ax, edge_color=cols, **self.STYLE_CONFIG["edge"])
                sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm); sm.set_array([])
                fig.colorbar(sm, ax=ax, orientation='vertical', fraction=0.02, pad=0.04).set_label("Volume")
            else:
                nx.draw_networkx_edges(G, pos, edgelist=draw_edges, ax=ax, edge_color='gray', **self.STYLE_CONFIG["edge"])
        elif draw_edges:
            nx.draw_networkx_edges(G, pos, edgelist=draw_edges, ax=ax, edge_color='gray', **self.STYLE_CONFIG["edge"])

        # [NOTE] 数値ラベルの描画はコメントアウト済み
        
        ax.set_title("Mixing Tree Visualization", fontsize=18); ax.axis('off')
        plt.tight_layout()
        try:
            plt.savefig(os.path.join(out, 'mixing_tree_visualization.png'), dpi=300, bbox_inches='tight')
            print(f"Graph saved to: {out}")
        except Exception as e: print(f"Error saving graph: {e}")
        finally: plt.close(fig)

    def _style(self, d):
        t = d.get('type')
        c = self.STYLE_CONFIG
        s = c['target_node'] if t=='mix' and d.get('level')==0 else c['mix_node'] if t=='mix' else c['mix_peer_node'] if t=='mix_peer' else c['reagent_node'] if t=='reagent' else c['waste_node'] if t=='waste' else c['default_node']
        return {'color': s['color'], 'size': s['size'], 'shape': s.get('shape', 'o')}