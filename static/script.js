document.addEventListener('DOMContentLoaded', () => {
    const tweetUrlInput = document.getElementById('tweetUrlInput');
    const analyzeButton = document.getElementById('analyzeButton');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const errorMessageDiv = document.getElementById('error-message');
    const resultsDiv = document.querySelector('.analysis-results'); // Get the main results container

    const mainPostDisplay = document.getElementById('main-post-display');
    const overallSummaryDiv = document.getElementById('overall-summary');
    const clustersContainer = document.getElementById('clusters-columns-container');

    // Check for preloaded data (from Flask template)
    if (typeof window.preloadedAnalysisData !== 'undefined' && window.preloadedAnalysisData !== null) {
        showLoading(false); // Ensure loading is hidden
        hideError();
        displayAnalysisData(window.preloadedAnalysisData);
    } else {
        // Hide results container if no preloaded data, show it only after analysis
        if(resultsDiv) resultsDiv.style.display = 'none';
    }

    // Function to escape HTML special characters
    function escapeHTML(str) {
        if (typeof str !== 'string') return '';
        return str.replace(/[&<>'"/]/g, function (s) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;', // IE only supports &#39; for single quote
                '/': '&#x2F;'
            }[s];
        });
    }

    analyzeButton.addEventListener('click', handleAnalyzeClick);

    async function handleAnalyzeClick() {
        const tweetUrl = tweetUrlInput.value.trim();
        if (!tweetUrl) {
            showError('Please enter a Tweet URL.');
            return;
        }

        showLoading(true);
        hideError();
        clearResults();

        try {
            const response = await fetch('/api/analyze_url', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ tweet_url: tweetUrl })
            });

            showLoading(false);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! Status: ${response.status}` }));
                showError(errorData.error || `HTTP error! Status: ${response.status}`);
                return;
            }

            const data = await response.json();
            
            if (data.error) {
                showError(data.error);
                return;
            }

            // New: Redirect if view_url is present, otherwise display directly (fallback)
            if (data.view_url) {
                window.location.href = data.view_url;
            } else {
                // Fallback to display data if no view_url (should not happen with new API structure)
                displayAnalysisData(data.data); 
            }

        } catch (error) {
            showLoading(false);
            showError(`Request failed: ${error.message}`);
            console.error('Fetch error:', error);
        }
    }

    function createTweetHTML(tweetData, isMainPost = false) {
        if (!tweetData) return '<p>Tweet data not available.</p>';

        const authorHandle = tweetData.author_handle || 'unknown_user';
        const authorDisplayName = tweetData.author_display_name || 'Unknown User';
        const userDisplay = authorHandle === 'unknown_user' && authorDisplayName === 'Unknown User' ? 
                            'User N/A' : 
                            `${authorDisplayName} (@${authorHandle})`;

        const text = tweetData.text || 'No text content.';
        const likes = tweetData.like_count !== undefined ? tweetData.like_count : 'N/A';
        const timestamp = tweetData.timestamp ? new Date(tweetData.timestamp).toLocaleString() : 'N/A';
        const avatarUrl = tweetData.avatar_url;

        let avatarHTML = '';
        if (avatarUrl) {
            avatarHTML = `<img src="${avatarUrl}" alt="Avatar" class="tweet-avatar">`;
        } else {
            avatarHTML = '<div class="avatar-placeholder"></div>';
        }

        const classificationHTML = !isMainPost && tweetData.llm_classification ? 
            `<p><small>Classifications: ${JSON.stringify(tweetData.llm_classification)}</small></p>` : '';
        
        // CSS will handle avatar size

        // Add tweet type indicator
        let typeIndicator = '';
        if (tweetData.tweet_type === 'quote_tweet') {
            typeIndicator = '<span class="tweet-type-indicator">(Quote Tweet)</span>';
        } else if (tweetData.tweet_type === 'reply') {
            // typeIndicator = '<span class="tweet-type-indicator">(Reply)</span>'; // Optional: if you want to label replies too
        }

        const tweetHeaderHTML = `
            <div class="tweet-header">
                <strong class="tweet-author-name">${escapeHTML(authorDisplayName)}</strong>
                <span class="tweet-author-handle">@${escapeHTML(authorHandle)}</span>
                ${typeIndicator}
            </div>
        `;

        const tweetTextHTML = `<p class="tweet-text">${escapeHTML(tweetData.text || 'No text available.')}</p>`;

        return `
            <div class="tweet-item ${isMainPost ? 'main-tweet-item' : 'reply-tweet-item'}">
                <div class="tweet-avatar-container">
                    ${avatarHTML}
                </div>
                <div class="tweet-content-container">
                    ${tweetHeaderHTML}
                    ${tweetTextHTML}
                    <p class="tweet-meta">Likes: ${likes} | Timestamp: ${timestamp}</p>
                    ${classificationHTML}
                </div>
            </div>
        `;
    }

    function displayMainPost(mainPostData) {
        if (!mainPostData || !mainPostData.main_post_id) {
            mainPostDisplay.innerHTML = '<p>Main post data not available or incomplete.</p>';
            return;
        }
        const mainTweetObject = {
            author_handle: mainPostData.main_post_author_handle,
            author_display_name: mainPostData.main_post_author_display_name,
            text: mainPostData.main_post_text,
            like_count: mainPostData.main_post_likes,
            timestamp: mainPostData.main_post_timestamp,
            avatar_url: mainPostData.main_post_avatar_url
        };
        mainPostDisplay.innerHTML = createTweetHTML(mainTweetObject, true);
    }

    function displayOverallSummary(summaryText) {
        if (typeof summaryText === 'string' && summaryText.includes("disabled")) {
            overallSummaryDiv.innerHTML = `<p><em>${escapeHTML(summaryText)}</em></p>`;
        } else if (summaryText && summaryText.trim() !== "") {
            overallSummaryDiv.innerHTML = `<p>${escapeHTML(summaryText)}</p>`;
        } else {
            overallSummaryDiv.innerHTML = '<p>No overall summary available.</p>';
        }
    }

    function displayClusters(clusterDetails) {
        clustersContainer.innerHTML = '';
        if (!clusterDetails) {
            clustersContainer.innerHTML = '<p>Cluster data not available.</p>';
            return;
        }

        const sentimentOrder = ["positive", "neutral", "negative"];
        const agreementOrder = ["agrees", "neutral", "disagrees"];
        
        let displayIndex = 0;

        sentimentOrder.forEach(sentiment => {
            agreementOrder.forEach(agreement => {
                const clusterName = `${sentiment}_${agreement}`;
                const cluster = clusterDetails[clusterName];
                
                const actualClusterData = cluster || { summary: "No replies in this cluster.", tweets: [] };
                const tweetCount = actualClusterData.tweets ? actualClusterData.tweets.length : 0;
                
                const clusterDiv = document.createElement('div');
                clusterDiv.classList.add('cluster-column');
                const sanitizedClusterNameClass = clusterName.replace(/[^a-zA-Z0-9-_]/g, '-');
                clusterDiv.classList.add(`cluster-style-${sanitizedClusterNameClass}`);

                const tweetListId = `tweet-list-${displayIndex++}`;
                let tweetsHtml = '';

                if (tweetCount > 0) {
                    actualClusterData.tweets.forEach(tweet => {
                        tweetsHtml += createTweetHTML(tweet, false);
                    });
                } else {
                    tweetsHtml = '<p>No replies in this cluster.</p>';
                }

                clusterDiv.innerHTML = `
                    <h3>${clusterName.replace(/_/g, ' ')} (${tweetCount} ${tweetCount === 1 ? 'reply' : 'replies'})</h3>
                    <p><strong>Summary:</strong> ${actualClusterData.summary || 'No summary available.'}</p>
                    <button class="toggle-tweets-btn" data-target="${tweetListId}">Show Replies</button>
                    <div class="tweet-list" id="${tweetListId}" style="display: none;">
                        <h4>Replies in this cluster:</h4>
                        ${tweetsHtml}
                    </div>
                `;
                clustersContainer.appendChild(clusterDiv);
            });
        });

        const displayedStandardKeys = new Set(sentimentOrder.flatMap(s => agreementOrder.map(a => `${s}_${a}`)))
        Object.keys(clusterDetails).forEach(clusterName => {
            if (!displayedStandardKeys.has(clusterName)) {
                const cluster = clusterDetails[clusterName];
                const tweetCount = cluster.tweets ? cluster.tweets.length : 0;
                const clusterDiv = document.createElement('div');
                clusterDiv.classList.add('cluster-column', 'additional-cluster');
                const sanitizedClusterNameClassAdditional = clusterName.replace(/[^a-zA-Z0-9-_]/g, '-');
                clusterDiv.classList.add(`cluster-style-${sanitizedClusterNameClassAdditional}`);

                const tweetListId = `tweet-list-${displayIndex++}`;
                let tweetsHtml = '';

                if (tweetCount > 0) {
                    cluster.tweets.forEach(tweet => {
                        tweetsHtml += createTweetHTML(tweet, false);
                    });
                } else {
                    tweetsHtml = '<p>No replies in this cluster.</p>';
                }

                clusterDiv.innerHTML = `
                    <h3>${clusterName.replace(/_/g, ' ')} (${tweetCount} ${tweetCount === 1 ? 'reply' : 'replies'})</h3>
                    <p><strong>Summary:</strong> ${cluster.summary || 'No summary available.'}</p>
                    <button class="toggle-tweets-btn" data-target="${tweetListId}">Show Replies</button>
                    <div class="tweet-list" id="${tweetListId}" style="display: none;">
                        <h4>Replies in this cluster:</h4>
                        ${tweetsHtml}
                    </div>
                `;
                clustersContainer.appendChild(clusterDiv);
            }
        });

        document.querySelectorAll('.toggle-tweets-btn').forEach(button => {
            button.addEventListener('click', function() {
                const targetId = this.dataset.target;
                const tweetList = document.getElementById(targetId);
                if (tweetList) {
                    const isHidden = tweetList.style.display === 'none';
                    tweetList.style.display = isHidden ? 'block' : 'none';
                    this.textContent = isHidden ? 'Hide Replies' : 'Show Replies';
                }
            });
        });
    }

    function showLoading(isLoading) {
        loadingIndicator.style.display = isLoading ? 'block' : 'none';
    }

    function showError(message) {
        errorMessageDiv.textContent = message || "An unknown error occurred.";
        errorMessageDiv.style.display = 'block';
    }

    function hideError() {
        errorMessageDiv.style.display = 'none';
    }
    
    function clearResults() {
        mainPostDisplay.innerHTML = '';
        overallSummaryDiv.innerHTML = '';
        clustersContainer.innerHTML = '';
        if(resultsDiv) resultsDiv.style.display = 'none';
    }

    function displayAnalysisData(analysisData) {
        if (!analysisData) {
            showError('No analysis data received.');
            if(resultsDiv) resultsDiv.style.display = 'none';
            return;
        }
        if(resultsDiv) resultsDiv.style.display = 'block'; // Show results container

        // Clear previous results specifically targeting areas that will be repopulated
        if(mainPostDisplay) mainPostDisplay.innerHTML = '';
        if(overallSummaryDiv) overallSummaryDiv.innerHTML = '';
        if(clustersContainer) clustersContainer.innerHTML = '';
        const tweetDetailDisplay = document.getElementById('tweet-detail-display');
        if (tweetDetailDisplay) tweetDetailDisplay.innerHTML = ''; // Clear old tweet details

        displayMainPost(analysisData);
        displayOverallSummary(analysisData.overall_summary);
        displayClusters(analysisData.cluster_details);

        // Removed Cytoscape initialization
        // if (analysisData.cytoscape_elements && analysisData.graph_metrics) {
        //     initializeCytoscapeGraph(analysisData.cytoscape_elements, analysisData.graph_metrics);
        //     displayGraphMetrics(analysisData.graph_metrics); 
        // } else {
        //     console.warn('Cytoscape elements or graph metrics missing in analysis data.');
        //     if (graphContainer) graphContainer.innerHTML = '<p>Graph data not available.</p>';
        // }

        // TODO: Add D3.js graph initialization here using analysisData.d3_graph_data and analysisData.graph_metrics
        if (analysisData.d3_graph_data && analysisData.d3_graph_data.status !== "Graph visualization disabled" && 
            analysisData.graph_metrics && analysisData.graph_metrics.status !== "Graph visualization disabled" &&
            Array.isArray(analysisData.d3_graph_data.nodes) /* Ensure nodes is an array for valid data */ ) {
            console.log("D3 graph data received:", analysisData.d3_graph_data);
            console.log("Graph metrics received:", analysisData.graph_metrics);
            initializeD3Graph(analysisData.d3_graph_data, analysisData.graph_metrics);
            displayGraphMetrics(analysisData.graph_metrics);
        } else {
            console.warn('D3 graph data or graph metrics missing, disabled, or invalid.');
            const svgContainer = document.getElementById('d3-graph-svg');
            const d3GraphSection = document.getElementById('d3-graph-section');
            if (analysisData.d3_graph_data && analysisData.d3_graph_data.status === "Graph visualization disabled") {
                if(d3GraphSection) d3GraphSection.style.display = 'none'; // Hide the whole section
            } else {
                if(svgContainer) svgContainer.innerHTML = '<text x="10" y="30" style="font-family: sans-serif; font-size: 16px;">Graph data not available or insufficient for display.</text>';
                if(d3GraphSection) d3GraphSection.style.display = 'block';
            }
            
            const metricsDisplay = document.getElementById('graph-metrics-display');
            if (analysisData.graph_metrics && analysisData.graph_metrics.status === "Graph visualization disabled") {
                 if(metricsDisplay) metricsDisplay.innerHTML = '<p><em>Graph metrics disabled.</em></p>';
            } else {
                 if(metricsDisplay) metricsDisplay.innerHTML = '<p>Graph metrics unavailable.</p>';
            }
        }

    }

    function initializeD3Graph(graphData, graphMetrics) {
        console.log("Initializing D3 graph with:", graphData, graphMetrics);
        const svg = d3.select("#d3-graph-svg");

        if (!graphData || !graphData.nodes || !graphData.links) {
            console.error("D3 graph data is incomplete (missing nodes or links).");
            svg.append("text")
               .attr("x", 10)
               .attr("y", 20)
               .text("Error: Graph data is incomplete.");
            return;
        }

        const width = +svg.attr("width");
        const height = +svg.attr("height");

        // Clear previous SVG contents
        svg.selectAll("*").remove();
        // Add a main <g> element for zoom & pan
        const g = svg.append("g");

        // Links (edges) - appended to the main <g>
        const link = g.append("g")
            .attr("stroke", "#999")
            .attr("stroke-opacity", 0.6)
            .selectAll("line")
            .data(graphData.links)
            .join("line")
            .style("stroke", d => d.relationship === 'quotes' ? '#FF851B' : '#999') // Orange for quotes, grey for replies
            .style("stroke-width", d => d.relationship === 'quotes' ? 2.5 : 1.5);

        // Nodes - appended to the main <g>
        const node = g.append("g")
            .attr("stroke", "#fff")
            .attr("stroke-width", 1.5)
            .selectAll("circle")
            .data(graphData.nodes)
            .join("circle")
            // .attr("r", 5) // Radius now set by getNodeRadius
            // .attr("fill", "#69b3a2"); // Fill now set by getNodeColor

        // Add text labels for nodes - appended to the main <g>
        const labels = g.append("g")
            .attr("class", "labels")
            .selectAll("text")
            .data(graphData.nodes)
            .join("text")
            .text(d => d.author || 'unknown')
            .attr("x", d => d.x + getNodeRadius(d.likes) + 2) // Position text to the right of the node
            .attr("y", d => d.y + 4) // Slightly offset y for better alignment
            .style("font-size", "10px")
            .style("fill", "#333");
        
        // Helper function for node color based on type
        function getNodeColor(nodeType) {
            if (nodeType === 'main_post') return '#FF4136'; // Red
            if (nodeType === 'quote_tweet') return '#2ECC40'; // Green
            return '#0074D9'; // Blue for reply or unknown
        }

        // Helper function for node radius based on likes
        function getNodeRadius(likes) {
            const baseRadius = 5;
            const maxRadius = 20;
            // Scale likes (e.g., log scale) to make radius changes more visually apparent for varying like counts
            // Add 1 to likes to handle log(0) or log(1)
            const scaledLikes = Math.log2(likes + 1);
            // Adjust multiplier as needed for good visual scaling
            return Math.min(baseRadius + scaledLikes * 1.5, maxRadius); 
        }

        // Apply styles to nodes
        node.attr("r", d => getNodeRadius(d.likes))
            .attr("fill", d => getNodeColor(d.type))
            .on("click", function(event, d) {
                // 'd' is the datum of the clicked node
                console.log("Node clicked:", d);
                displayTweetDetail(d); // Pass the node's data to the existing display function
            });

        // Force Simulation
        const simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.links)
                .id(d => d.id)
                .distance(d => d.relationship === 'quotes' ? 750 : 50) // Quotes significantly further (750), replies closer (50)
                .strength(d => d.relationship === 'quotes' ? 0.3 : 0.7) // Replies have stronger links
            )
            .force("charge", d3.forceManyBody().strength(d => {
                if (d.type === 'quote_tweet') {
                    return -250; // Stronger repulsion for quote tweets
                }
                return -150; // Default repulsion for other nodes
            }))
            .force("center", d3.forceCenter(width / 2, height / 2));

        // Identify main post and apply specific forces
        const mainPostNode = graphData.nodes.find(node => node.type === 'main_post');

        if (mainPostNode) {
            // Fix the main post to the center of the SVG
            mainPostNode.fx = width / 2;
            mainPostNode.fy = height / 2;
            
            // Remove the previous forces that were pulling the main post, as fx/fy is a hard constraint
            simulation.force("mainPostX", null);
            simulation.force("mainPostY", null);

            // The yByType force might also be removed or adjusted based on new requirements
            // For now, let's remove it to simplify for the new X-based positioning of quotes
            simulation.force("yByType", null);
        }

        // Add a force to pull quote tweets to the right side
        simulation.force("quoteX", d3.forceX(d => {
            if (d.type === 'quote_tweet') {
                return width * 2.0; // Target X for quote tweets extremely far to the right
            }
            return width / 2; // Default X target for other nodes
        }).strength(d => d.type === 'quote_tweet' ? 0.95 : 0.001)); // Very strong pull for quotes, very weak for others

        // Tick function to update positions
        simulation.on("tick", () => {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);
            
            labels
                .attr("x", d => d.x + getNodeRadius(d.likes) + 2) // Adjust x based on node radius
                .attr("y", d => d.y + 4); // Keep y alignment
        });

        // Zoom and Pan functionality
        const zoomHandler = d3.zoom()
            .scaleExtent([0.1, 4]) // Set min/max zoom scale
            .on("zoom", (event) => {
                g.attr("transform", event.transform);
            });
        
        svg.call(zoomHandler);

        console.log("D3: Force simulation started. Zoom/pan enabled.");
        console.log("SVG width:", width, "SVG height:", height);
    }

    // Kept and adapted displayTweetDetail for D3
    function displayTweetDetail(tweetData) {
        const detailDiv = document.getElementById('tweet-detail-display');
        if (!detailDiv) return;

        if (!tweetData) {
            detailDiv.innerHTML = '<p>No tweet data to display.</p>';
            detailDiv.style.display = 'block';
            return;
        }

        // Construct a similar object to what createTweetHTML expects
        // The attributes might be slightly different depending on how D3 nodes store them.
        // For now, assume direct properties or access via a 'data' property if D3 nodes wrap it.
        const displayData = {
            text: tweetData.text || 'N/A',
            author_handle: tweetData.author || 'N/A',
            author_display_name: tweetData.display_name || 'N/A',
            like_count: tweetData.likes !== undefined ? tweetData.likes : 'N/A',
            timestamp: tweetData.timestamp ? new Date(tweetData.timestamp).toLocaleString() : 'N/A',
            avatar_url: tweetData.avatar_url, // Assuming avatar_url will be part of node data
            llm_classification: tweetData.classification, // Assuming classification is part of node data
            tweet_type: tweetData.type // Assuming type is part of node data
        };

        detailDiv.innerHTML = createTweetHTML(displayData, tweetData.type === 'main_post');
        detailDiv.style.display = 'block';
    }

    // Kept and adapted displayGraphMetrics for D3
    function displayGraphMetrics(metrics) {
        const metricsDiv = document.getElementById('graph-metrics-display'); 
        if (!metricsDiv) {
            console.warn("graph-metrics-display element not found for displaying metrics.");
            return;
        }
        if (metrics && metrics.status === "Graph visualization disabled"){
            metricsDiv.innerHTML = `<p><em>${escapeHTML(metrics.status)}</em></p>`;
            return;
        }
        if (!metrics || Object.keys(metrics).length === 0 || metrics.total_tweets === undefined) { // Check for empty or uninitialized metrics
            metricsDiv.innerHTML = '<p>Graph metrics not available.</p>';
            return;
        }

        let metricsHTML = '<h4>Graph Metrics:</h4><ul>';
        metricsHTML += `<li>Total Tweets: ${metrics.total_tweets}</li>`;
        metricsHTML += `<li>Total Relationships (Replies/Quotes): ${metrics.total_replies}</li>`;
        if (metrics.main_post) {
            metricsHTML += `<li>Main Post: ${escapeHTML(metrics.main_post.author)} - "${escapeHTML(metrics.main_post.text.substring(0, 30))}..."</li>`;
        }
        metricsHTML += `<li>Max Reply Depth: ${metrics.reply_depth}</li>`;

        if (metrics.most_replied_to) {
            metricsHTML += `<li>Most Replied To: ${escapeHTML(metrics.most_replied_to.author)} (${metrics.most_replied_to.reply_count} replies) - "${escapeHTML(metrics.most_replied_to.text.substring(0,30))}..."</li>`;
        }

        metricsHTML += '</ul>';
        // We might want to display author stats differently or in a more condensed form later
        // metricsHTML += '<h5>Author Stats:</h5><pre>' + escapeHTML(JSON.stringify(metrics.author_stats, null, 2)) + '</pre>';
        
        metricsDiv.innerHTML = metricsHTML;
    }

    // Event delegation for toggle buttons if they are added dynamically
    // ... existing code ...
}); 