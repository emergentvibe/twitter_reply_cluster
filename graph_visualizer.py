import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import networkx as nx
import matplotlib.pyplot as plt
from typing import List, Dict, Any
import json
import os
# from networkx.readwrite import cytoscape_data # No longer needed

def create_reply_graph(tweets_data: List[Dict[str, Any]]) -> nx.DiGraph:
    """
    Creates a directed graph from tweet data where:
    - Nodes are tweets
    - Edges represent reply relationships and quote relationships
    - Node attributes include text, author, and classification
    - Edge attributes include the type of relationship
    """
    G = nx.DiGraph()
    main_post_id = None

    # First pass to identify the main_post_id and add all nodes
    for tweet in tweets_data:
        node_id = tweet['id']
        if tweet.get('tweet_type') == 'main_post':
            main_post_id = node_id
        
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
            'classification': tweet.get('llm_classification', {})
        }
        G.add_node(node_id, **node_attrs)
    
    # Second pass to add edges
    for tweet in tweets_data:
        current_node_id = tweet['id']
        # Add reply edges
        reply_to_id = tweet.get('reply_to_tweet_id')
        if reply_to_id and current_node_id in G and reply_to_id in G:
            G.add_edge(
                current_node_id,
                reply_to_id,
                relationship='reply'
            )
        
        # Add quote edges (quote tweet points TO the main post)
        if tweet.get('tweet_type') == 'quote_tweet' and main_post_id and current_node_id in G and main_post_id in G:
            # Ensure we don't add a self-loop if a quote tweet somehow is the main post (unlikely)
            if current_node_id != main_post_id: 
                G.add_edge(
                    current_node_id, 
                    main_post_id, 
                    relationship='quotes'
                )
    
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

def convert_to_d3_format(G: nx.DiGraph) -> Dict[str, List[Dict[str, Any]]]:
    """
    Converts a NetworkX graph to a D3.js compatible format.
    (Nodes list and Links list)
    """
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
            'classification': data.get('classification', {})
        })

    links = []
    for source, target, data in G.edges(data=True):
        links.append({
            'source': source,
            'target': target,
            'relationship': data.get('relationship', 'unknown')
        })
    
    return {'nodes': nodes, 'links': links}

def process_tweet_data(tweets_data: List[Dict[str, Any]], output_prefix: str = 'tweet_analysis'):
    """
    Main function to process tweet data, generate graph analysis, 
    and return data for D3.js.
    """
    # Create the graph
    G = create_reply_graph(tweets_data)
    
    # Perform analysis
    graph_metrics = analyze_graph(G)
    
    # Convert graph to D3.js compatible format
    d3_graph_data = convert_to_d3_format(G)
    
    # Optional: Save the D3 JSON data (e.g., for debugging or local use)
    # d3_json_path = os.path.join(os.getcwd(), f'{output_prefix}_d3_data.json') # Example path
    # with open(d3_json_path, 'w') as f:
    #     json.dump(d3_graph_data, f, indent=2)
    
    return {
        'graph_metrics': graph_metrics,
        'd3_graph_data': d3_graph_data
    } 