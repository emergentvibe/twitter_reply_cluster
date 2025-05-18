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
        if (summaryText && summaryText.trim() !== "") {
            overallSummaryDiv.innerHTML = `<p>${summaryText}</p>`;
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

    // Central function to display all parts of the analysis data
    function displayAnalysisData(analysisData) {
        if (!analysisData) {
            showError("No analysis data to display.");
            if(resultsDiv) resultsDiv.style.display = 'none';
            return;
        }
        displayMainPost(analysisData); // Expects the full analysis object from analyze_tweets or cache
        displayOverallSummary(analysisData.overall_summary);
        displayClusters(analysisData.cluster_details);
        if(resultsDiv) resultsDiv.style.display = 'block';
    }
}); 