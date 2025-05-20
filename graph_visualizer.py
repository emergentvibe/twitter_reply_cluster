import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import networkx as nx
import matplotlib.pyplot as plt
from typing import List, Dict, Any
import json
import os
import logging # For better logging
# from networkx.readwrite import cytoscape_data # No longer needed

# Configure logging for this module (optional, but good practice)
logger = logging.getLogger(__name__)
# Example: If you want to see these logs in Flask console, ensure Flask's logger is configured appropriately
# or use app.logger if this code was part of the Flask app module.
# For standalone script use, basicConfig might be enough:
# logging.basicConfig(level=logging.INFO) 
# Using print for now for simplicity if Flask logger isn't readily available here

def create_reply_graph(tweets_data: List[Dict[str, Any]]) -> nx.DiGraph:
    """
    Creates a directed graph from tweet data where:
    - Nodes are tweets
    - Edges represent reply relationships and quote relationships
    - Node attributes include text, author, and classification
    - Edge attributes include the type of relationship
    """
    print(f"[DEBUG gv.py create_reply_graph] Received {len(tweets_data)} tweets.")
    if not tweets_data:
        print("[DEBUG gv.py create_reply_graph] tweets_data is empty. Returning empty graph.")
        return nx.DiGraph() # Return an empty graph object

    # --- BEGIN DIAGNOSTIC LOGGING: Print first few full tweet dicts --- 
    if tweets_data and len(tweets_data) > 0:
        print("[DEBUG gv.py create_reply_graph] First 3 tweet dicts received:")
        for i, tweet_item_log in enumerate(tweets_data[:3]):
            print(f"  [DEBUG gv.py tweet_dict {i}]: {tweet_item_log}")
    # --- END DIAGNOSTIC LOGGING ---

    G = nx.DiGraph()

    # First pass to add all nodes with their attributes
    for tweet in tweets_data:
        node_id = tweet.get('id') 
        if not node_id:
            print(f"[DEBUG gv.py create_reply_graph] Tweet missing ID: {tweet}. Skipping node add.")
            continue
        
        author_handle = tweet.get('author_handle')
        display_name = tweet.get('author_display_name')
        like_count = tweet.get('like_count')

        node_attrs = {
            'text': tweet.get('text', ''),
            'author': author_handle if author_handle is not None else 'unknown',
            'display_name': display_name if display_name is not None else 'Unknown User',
            'type': tweet.get('tweet_type', 'unknown'),
            'likes': like_count if like_count is not None else 0,
            'timestamp': tweet.get('timestamp', ''),
            'classification': tweet.get('llm_classification', {}),
            'qt_level': tweet.get('qt_level', -1) 
        }
        G.add_node(str(node_id), **node_attrs) 
    
    print(f"[DEBUG gv.py create_reply_graph] Added {G.number_of_nodes()} nodes to graph.")
    if G.number_of_nodes() > 0 and G.number_of_nodes() < 20: 
         print(f"[DEBUG gv.py create_reply_graph] Node IDs in G: {list(G.nodes())}")

    # Second pass to add edges based on parent_tweet_id
    edge_add_attempts = 0
    actual_edges_added = 0
    print("[DEBUG gv.py create_reply_graph] Starting edge creation loop...")
    for i, tweet in enumerate(tweets_data):
        current_node_id = str(tweet.get('id'))
        parent_id_for_graph = str(tweet.get('parent_tweet_id')) if tweet.get('parent_tweet_id') else None
        actual_reply_parent_id = str(tweet.get('actual_reply_to_id')) if tweet.get('actual_reply_to_id') else None
        tweet_type = tweet.get('tweet_type')

        log_prefix = f"  [DEBUG gv.py edge_loop {i}]"
        print(f"{log_prefix} Processing tweet: id={current_node_id}, parent_id_for_graph={parent_id_for_graph}, actual_reply_parent_id={actual_reply_parent_id}, tweet_type={tweet_type}")

        # Edge based on parent_tweet_id (primary link, often for quotes or main thread structure)
        if parent_id_for_graph and current_node_id:
            edge_add_attempts += 1
            if current_node_id in G and parent_id_for_graph in G:
                if G.has_edge(current_node_id, parent_id_for_graph) or G.has_edge(parent_id_for_graph, current_node_id):
                    print(f"    {log_prefix} Edge between {current_node_id} and {parent_id_for_graph} (based on parent_tweet_id) already exists. Skipping.")
                elif current_node_id == parent_id_for_graph:
                    print(f"    {log_prefix} SKIPPED ADDING SELF-LOOP EDGE (parent_tweet_id): {current_node_id} -> {parent_id_for_graph}")
                else:
                    relationship_type = 'quote_link' if tweet_type == 'quote_tweet' else 'reply_to_main_thread'
                    G.add_edge(current_node_id, parent_id_for_graph, relationship=relationship_type)
                    actual_edges_added += 1
                    print(f"    {log_prefix} SUCCESSFULLY ADDED EDGE (parent_tweet_id): {current_node_id} -> {parent_id_for_graph} ({relationship_type})")
            else:
                print(f"    {log_prefix} EDGE NOT ADDED (parent_tweet_id): {current_node_id} -> {parent_id_for_graph}. current_node_id in G? {current_node_id in G}. parent_id_for_graph in G? {parent_id_for_graph in G}")
        elif current_node_id and not parent_id_for_graph and tweet_type != 'main_post':
             print(f"    {log_prefix} Node {current_node_id} (type: {tweet_type}) has no parent_id_for_graph. Edge not added.")

        # Additional edge based on actual_reply_to_id (for direct conversation flow)
        if actual_reply_parent_id and current_node_id:
            # Only add this if it's different from the parent_id_for_graph link (if parent_id_for_graph link exists)
            # to avoid redundant reply links when parent_tweet_id already captures the direct reply.
            # Also, ensure we are not creating a self-loop.
            if current_node_id == actual_reply_parent_id:
                print(f"    {log_prefix} SKIPPED ADDING SELF-LOOP EDGE (actual_reply_to_id): {current_node_id} -> {actual_reply_parent_id}")
            elif actual_reply_parent_id != parent_id_for_graph or not parent_id_for_graph:
                edge_add_attempts += 1 # Count as an attempt
                if current_node_id in G and actual_reply_parent_id in G:
                    # Check if this specific direct reply edge already exists
                    if G.has_edge(current_node_id, actual_reply_parent_id) and G[current_node_id][actual_reply_parent_id].get('relationship') == 'direct_reply_within_thread':
                        print(f"    {log_prefix} Edge between {current_node_id} and {actual_reply_parent_id} (relationship: direct_reply_within_thread) already exists. Skipping.")
                    elif G.has_edge(actual_reply_parent_id, current_node_id) and G[actual_reply_parent_id][current_node_id].get('relationship') == 'direct_reply_within_thread': # Check reverse too
                        print(f"    {log_prefix} Edge between {actual_reply_parent_id} and {current_node_id} (relationship: direct_reply_within_thread) already exists. Skipping.")
                    # Also check if a general edge exists if we don't want to double-link (e.g. parent_id_for_graph already covered it)
                    # The condition `actual_reply_parent_id != parent_id_for_graph` should handle most cases where parent_id_for_graph is the same.
                    # However, if parent_id_for_graph was None, we definitely want to add this direct reply link if it exists.
                    elif G.has_edge(current_node_id, actual_reply_parent_id) or G.has_edge(actual_reply_parent_id, current_node_id):
                        # An edge exists, but it might be the quote link. Add this one if it's different or parent_id_for_graph was None.
                        if parent_id_for_graph != actual_reply_parent_id:
                            G.add_edge(current_node_id, actual_reply_parent_id, relationship='direct_reply_within_thread')
                            print(f"    {log_prefix} SUCCESSFULLY ADDED EDGE (actual_reply_to_id): {current_node_id} -> {actual_reply_parent_id} (direct_reply_within_thread) - (was different from existing parent_id_for_graph link)")
                        else:
                             print(f"    {log_prefix} Edge between {current_node_id} and {actual_reply_parent_id} already exists (likely from parent_tweet_id logic as they matched). Skipping direct_reply_within_thread specific add.")
                    else:
                        G.add_edge(current_node_id, actual_reply_parent_id, relationship='direct_reply_within_thread')
                        print(f"    {log_prefix} SUCCESSFULLY ADDED EDGE (actual_reply_to_id): {current_node_id} -> {actual_reply_parent_id} (direct_reply_within_thread)")
                else:
                    print(f"    {log_prefix} EDGE NOT ADDED (actual_reply_to_id): {current_node_id} -> {actual_reply_parent_id}. current_node_id in G? {current_node_id in G}. actual_reply_parent_id in G? {actual_reply_parent_id in G}")
            elif actual_reply_parent_id == parent_id_for_graph:
                 print(f"    {log_prefix} Skipped adding redundant direct_reply_within_thread for actual_reply_to_id as it matches parent_id_for_graph: {current_node_id} -> {actual_reply_parent_id}")

    final_edge_count = G.number_of_edges()
    print(f"[DEBUG gv.py create_reply_graph] Edge add attempts: {edge_add_attempts}. Final distinct edges in graph: {final_edge_count}.")
    return G

def visualize_graph(G: nx.DiGraph, output_file: str = 'tweet_graph.png'):
    """
    Creates a visualization of the tweet graph and saves it to a file.
    """
    plt.figure(figsize=(15, 10))
    
    # Use spring layout for better visualization
    pos = nx.spring_layout(G, k=1, iterations=50)
    
    # Draw nodes with different colors based on tweet type
    node_colors = []
    for node in G.nodes():
        tweet_type = G.nodes[node]['type']
        if tweet_type == 'main_post':
            node_colors.append('red')
        elif tweet_type == 'quote_tweet':
            node_colors.append('green')
        else:  # reply
            node_colors.append('blue')
    
    # Draw the graph
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=500, alpha=0.7)
    nx.draw_networkx_edges(G, pos, edge_color='gray', arrows=True, arrowsize=20)
    
    # Add labels (author handles)
    labels = {node: G.nodes[node]['author'] for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=8)
    
    plt.title('Twitter Reply Thread Visualization')
    plt.axis('off')
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()

def analyze_graph(G: nx.DiGraph) -> Dict[str, Any]:
    """
    Performs basic analysis on the graph and returns metrics.
    """
    analysis = {
        'total_tweets': G.number_of_nodes(),
        'total_replies': G.number_of_edges(),
        'main_post': None,
        'reply_depth': 0,
        'most_replied_to': None,
        'author_stats': {}
    }
    
    if not G.nodes(): # Handle empty graph
        return analysis

    # Find main post by its type attribute
    main_node_id = None
    for node_id, data in G.nodes(data=True):
        if data.get('type') == 'main_post':
            main_node_id = node_id
            analysis['main_post'] = {
                'id': node_id,
                'author': data.get('author', 'unknown'),
                'text': data.get('text', '')
            }
            break # Assuming only one main_post
    
    # Calculate reply depth (only if main_post was found)
    if main_node_id and main_node_id in G:
        try:
            path_lengths = nx.shortest_path_length(G, source=main_node_id)
            if path_lengths:
                analysis['reply_depth'] = max(path_lengths.values())
        except nx.NetworkXNoPath:
            analysis['reply_depth'] = 0
        except Exception as e:
            print(f"Error calculating reply depth: {e}") 
            analysis['reply_depth'] = 0 
    
    # Find most replied to tweet
    max_replies = -1 # Initialize to -1 to correctly find if any tweet has 0 replies
    most_replied_node_id = None
    for node_id in G.nodes():
        # Consider in_degree for replies *to* this node
        in_degree = G.in_degree(node_id)
        if in_degree > max_replies:
            max_replies = in_degree
            most_replied_node_id = node_id
    
    if most_replied_node_id is not None:
        analysis['most_replied_to'] = {
            'id': most_replied_node_id,
            'author': G.nodes[most_replied_node_id].get('author', 'unknown'),
            'text': G.nodes[most_replied_node_id].get('text', ''),
            'reply_count': max_replies
        }
    
    # Calculate author statistics
    for node_id in G.nodes():
        author = G.nodes[node_id].get('author', 'unknown') or 'unknown'
        if author not in analysis['author_stats']:
            analysis['author_stats'][author] = {
                'tweet_count': 0,
                'reply_count': 0 # out_degree for replies *from* this author's tweets
            }
        analysis['author_stats'][author]['tweet_count'] += 1
        analysis['author_stats'][author]['reply_count'] += G.out_degree(node_id)
    
    return analysis

def save_graph_data(G: nx.DiGraph, output_file: str = 'tweet_graph.json'):
    """
    Saves the graph data to a JSON file for later use or analysis.
    """
    graph_data = {
        'nodes': [],
        'edges': []
    }
    
    # Save nodes
    for node in G.nodes():
        node_data = G.nodes[node]
        graph_data['nodes'].append({
            'id': node,
            'text': node_data['text'],
            'author': node_data['author'],
            'display_name': node_data['display_name'],
            'type': node_data['type'],
            'likes': node_data['likes'],
            'timestamp': node_data['timestamp'],
            'classification': node_data['classification']
        })
    
    # Save edges
    for edge in G.edges():
        graph_data['edges'].append({
            'source': edge[0],
            'target': edge[1],
            'relationship': G.edges[edge]['relationship']
        })
    
    with open(output_file, 'w') as f:
        json.dump(graph_data, f, indent=2)

def convert_to_d3_format(G: nx.DiGraph, main_post_id=None) -> Dict[str, List[Dict[str, Any]]]:
    """Converts a NetworkX graph to a D3.js compatible format."""
    print(f"[DEBUG gv.py convert_to_d3_format] Received graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    nodes = []
    for node_id, data in G.nodes(data=True):
        nodes.append({
            'id': node_id, 
            'text': data.get('text', ''),
            'author': data.get('author', 'unknown'),
            'display_name': data.get('display_name', 'Unknown User'),
            'type': data.get('type', 'unknown'),
            'likes': data.get('likes', 0),
            'timestamp': data.get('timestamp', ''),
            'classification': data.get('classification', {}),
            'qt_level': data.get('qt_level', -1) 
        })

    links = []
    for edge_num, (u, v, data) in enumerate(G.edges(data=True)):
        # Use main_post_id if source/target is None (should not happen with ID-based nodes)
        # Ensure u and v are strings, as D3 expects string IDs for source/target if they are not numerical indices.
        source_id = str(u) if u is not None else None # Keep None if truly None initially
        target_id = str(v) if v is not None else None # Keep None if truly None initially
        relationship = data.get('relationship', 'unknown') # Get relationship type
        
        # Defensive check: if for some reason an edge to None was added, try to link to main_post_id
        # This should ideally be prevented upstream by not adding edges to None.
        if source_id is None: source_id = str(main_post_id) if main_post_id else None
        if target_id is None: target_id = str(main_post_id) if main_post_id else None

        if source_id and target_id:
            links.append({"source": source_id, "target": target_id, "relationship": relationship})
        else:
            print(f"[DEBUG gv.py convert_to_d3_format edge {edge_num}] SKIPPING D3 LINK CREATION due to None ID after fallback: source_input={u}, target_input={v}, main_post_id={main_post_id}, final_source={source_id}, final_target={target_id}")

    print(f"[DEBUG gv.py convert_to_d3_format] Created {len(links)} D3 links.")
    if links and len(links) < 10: 
        print(f"[DEBUG gv.py convert_to_d3_format] D3 links created: {links}")
    elif links: 
        print(f"[DEBUG gv.py convert_to_d3_format] First 5 D3 links (or fewer): {links[:5]}")
    return {"nodes": nodes, "links": links}

def process_tweet_data(tweets_data: List[Dict[str, Any]], output_prefix: str = 'tweet_analysis'):
    """
    Main function to process tweet data, generate graph analysis, 
    and return data for D3.js.
    """
    if not tweets_data:
        print(f"[DEBUG gv.py process_tweet_data] Received empty or null tweets_data. Tweets count: {len(tweets_data) if tweets_data is not None else 'None'}")
        return {
            "graph_metrics": {"status": "No tweet data to process", "total_tweets":0, "total_replies":0},
            "d3_graph_data": {"nodes": [], "links": [], "status": "No tweet data to process"}
        }
    else:
        print(f"[DEBUG gv.py process_tweet_data] Received {len(tweets_data)} tweets.")

    G = create_reply_graph(tweets_data)
    graph_metrics = analyze_graph(G)
    d3_data = convert_to_d3_format(G)
    
    return {
        'graph_metrics': graph_metrics,
        'd3_graph_data': d3_data
    } 