import requests
import time
import json
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import quote_plus

class RedditJSONSearcher:
    def __init__(self):
        self.base_url = "https://www.reddit.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.rate_limit_delay = 1.1  # Slightly more than 1 second to be safe
    
    def search_subreddit(self, subreddit: str, search_term: str, limit: int = 25, sort: str = 'relevance') -> List[Dict]:
        """
        Search for posts in a subreddit using Reddit's JSON API
        
        Args:
            subreddit (str): Name of the subreddit (without 'r/')
            search_term (str): Term to search for
            limit (int): Number of posts to return (max 25 per request)
            sort (str): Sort method ('relevance', 'hot', 'top', 'new', 'comments')
            
        Returns:
            List[Dict]: List of posts with their details
        """
        url = f"{self.base_url}/r/{subreddit}/search.json"
        
        params = {
            'q': search_term,
            'limit': min(limit, 25),  # Reddit JSON API limit
            'sort': sort,
            't': 'all',  # Time filter: hour, day, week, month, year, all
            'restrict_sr': 'on'  # Restrict search to subreddit
        }
        
        try:
            print(f"Searching r/{subreddit} for '{search_term}'...")
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            posts = []
            
            if 'data' in data and 'children' in data['data']:
                for post in data['data']['children']:
                    post_data = post['data']
                    
                    # Convert timestamp to datetime
                    created_time = datetime.fromtimestamp(post_data['created_utc'])
                    
                    post_info = {
                        'title': post_data['title'],
                        'url': f"https://reddit.com{post_data['permalink']}",
                        'author': post_data['author'] if post_data['author'] != '[deleted]' else '[deleted]',
                        'score': post_data['score'],
                        'num_comments': post_data['num_comments'],
                        'created_utc': created_time,
                        'selftext': post_data['selftext'][:500] + '...' if len(post_data['selftext']) > 500 else post_data['selftext'],
                        'subreddit': subreddit,
                        'search_term': search_term,
                        'upvote_ratio': post_data.get('upvote_ratio', 0),
                        'is_self': post_data['is_self'],
                        'domain': post_data['domain']
                    }
                    posts.append(post_info)
            
            print(f"Found {len(posts)} posts")
            return posts
            
        except requests.exceptions.RequestException as e:
            print(f"Error searching r/{subreddit}: {e}")
            return []
    
    def get_subreddit_posts(self, subreddit: str, listing: str = 'hot', limit: int = 25) -> List[Dict]:
        """
        Get posts from a subreddit using different listings
        
        Args:
            subreddit (str): Name of the subreddit (without 'r/')
            listing (str): Type of listing ('hot', 'new', 'top', 'rising')
            limit (int): Number of posts to return
            
        Returns:
            List[Dict]: List of posts with their details
        """
        url = f"{self.base_url}/r/{subreddit}/{listing}.json"
        
        params = {
            'limit': min(limit, 25)
        }
        
        try:
            print(f"Getting {listing} posts from r/{subreddit}...")
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            posts = []
            
            if 'data' in data and 'children' in data['data']:
                for post in data['data']['children']:
                    post_data = post['data']
                    
                    created_time = datetime.fromtimestamp(post_data['created_utc'])
                    
                    post_info = {
                        'title': post_data['title'],
                        'url': f"https://reddit.com{post_data['permalink']}",
                        'author': post_data['author'] if post_data['author'] != '[deleted]' else '[deleted]',
                        'score': post_data['score'],
                        'num_comments': post_data['num_comments'],
                        'created_utc': created_time,
                        'selftext': post_data['selftext'][:500] + '...' if len(post_data['selftext']) > 500 else post_data['selftext'],
                        'subreddit': subreddit,
                        'listing': listing,
                        'upvote_ratio': post_data.get('upvote_ratio', 0),
                        'is_self': post_data['is_self'],
                        'domain': post_data['domain']
                    }
                    posts.append(post_info)
            
            print(f"Found {len(posts)} posts")
            return posts
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting posts from r/{subreddit}: {e}")
            return []
    
    def search_multiple_terms(self, subreddit: str, search_terms: List[str], limit_per_term: int = 25) -> Dict[str, List[Dict]]:
        """
        Search for multiple terms in a subreddit
        
        Args:
            subreddit (str): Name of the subreddit
            search_terms (List[str]): List of terms to search for
            limit_per_term (int): Number of posts per search term
            
        Returns:
            Dict[str, List[Dict]]: Dictionary with search terms as keys and posts as values
        """
        results = {}
        
        for term in search_terms:
            posts = self.search_subreddit(subreddit, term, limit_per_term)
            results[term] = posts
            
            # Respect rate limits
            if len(search_terms) > 1:
                time.sleep(self.rate_limit_delay)
        
        return results
    
    def save_results_to_json(self, posts: List[Dict], filename: str):
        """
        Save search results to a JSON file
        
        Args:
            posts (List[Dict]): List of posts to save
            filename (str): Name of the output file
        """
        # Convert datetime objects to strings for JSON serialization
        serializable_posts = []
        for post in posts:
            post_copy = post.copy()
            if isinstance(post_copy['created_utc'], datetime):
                post_copy['created_utc'] = post_copy['created_utc'].isoformat()
            serializable_posts.append(post_copy)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(serializable_posts, f, indent=2, ensure_ascii=False)
        
        print(f"Results saved to {filename}")
    
    def search_subreddit_paginated(self, subreddit: str, search_term: str, max_posts: int = 100, sort: str = 'relevance') -> List[Dict]:
        """
        Search for posts in a subreddit with pagination to get more than 25 posts
        
        Args:
            subreddit (str): Name of the subreddit (without 'r/')
            search_term (str): Term to search for
            max_posts (int): Maximum number of posts to return
            sort (str): Sort method ('relevance', 'hot', 'top', 'new', 'comments')
            
        Returns:
            List[Dict]: List of posts with their details
        """
        all_posts = []
        after = None
        posts_per_request = 25
        
        while len(all_posts) < max_posts:
            url = f"{self.base_url}/r/{subreddit}/search.json"
            
            params = {
                'q': search_term,
                'limit': posts_per_request,
                'sort': sort,
                't': 'all',
                'restrict_sr': 'on'
            }
            
            # Add pagination parameter
            if after:
                params['after'] = after
            
            try:
                print(f"Searching r/{subreddit} for '{search_term}'... (page {len(all_posts)//posts_per_request + 1})")
                response = requests.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                
                data = response.json()
                
                if 'data' in data and 'children' in data['data']:
                    posts = data['data']['children']
                    
                    if not posts:  # No more posts available
                        break
                    
                    for post in posts:
                        post_data = post['data']
                        
                        # Convert timestamp to datetime
                        created_time = datetime.fromtimestamp(post_data['created_utc'])
                        
                        post_info = {
                            'title': post_data['title'],
                            'url': f"https://reddit.com{post_data['permalink']}",
                            'author': post_data['author'] if post_data['author'] != '[deleted]' else '[deleted]',
                            'score': post_data['score'],
                            'num_comments': post_data['num_comments'],
                            'created_utc': created_time,
                            'selftext': post_data['selftext'][:500] + '...' if len(post_data['selftext']) > 500 else post_data['selftext'],
                            'subreddit': subreddit,
                            'search_term': search_term,
                            'upvote_ratio': post_data.get('upvote_ratio', 0),
                            'is_self': post_data['is_self'],
                            'domain': post_data['domain']
                        }
                        all_posts.append(post_info)
                    
                    # Get the 'after' parameter for next page
                    after = data['data']['after']
                    
                    if not after:  # No more pages
                        break
                    
                    print(f"Found {len(posts)} posts (total: {len(all_posts)})")
                    
                    # Respect rate limits
                    time.sleep(self.rate_limit_delay)
                else:
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Error searching r/{subreddit}: {e}")
                break
        
        print(f"Total posts found: {len(all_posts)}")
        return all_posts[:max_posts]  # Return only up to max_posts
    
    def get_subreddit_posts_paginated(self, subreddit: str, listing: str = 'hot', max_posts: int = 100) -> List[Dict]:
        """
        Get posts from a subreddit with pagination to get more than 25 posts
        
        Args:
            subreddit (str): Name of the subreddit (without 'r/')
            listing (str): Type of listing ('hot', 'new', 'top', 'rising')
            max_posts (int): Maximum number of posts to return
            
        Returns:
            List[Dict]: List of posts with their details
        """
        all_posts = []
        after = None
        posts_per_request = 25
        
        while len(all_posts) < max_posts:
            url = f"{self.base_url}/r/{subreddit}/{listing}.json"
            
            params = {
                'limit': posts_per_request
            }
            
            # Add pagination parameter
            if after:
                params['after'] = after
            
            try:
                print(f"Getting {listing} posts from r/{subreddit}... (page {len(all_posts)//posts_per_request + 1})")
                response = requests.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                
                data = response.json()
                
                if 'data' in data and 'children' in data['data']:
                    posts = data['data']['children']
                    
                    if not posts:  # No more posts available
                        break
                    
                    for post in posts:
                        post_data = post['data']
                        
                        created_time = datetime.fromtimestamp(post_data['created_utc'])
                        
                        post_info = {
                            'title': post_data['title'],
                            'url': f"https://reddit.com{post_data['permalink']}",
                            'author': post_data['author'] if post_data['author'] != '[deleted]' else '[deleted]',
                            'score': post_data['score'],
                            'num_comments': post_data['num_comments'],
                            'created_utc': created_time,
                            'selftext': post_data['selftext'][:500] + '...' if len(post_data['selftext']) > 500 else post_data['selftext'],
                            'subreddit': subreddit,
                            'listing': listing,
                            'upvote_ratio': post_data.get('upvote_ratio', 0),
                            'is_self': post_data['is_self'],
                            'domain': post_data['domain']
                        }
                        all_posts.append(post_info)
                    
                    # Get the 'after' parameter for next page
                    after = data['data']['after']
                    
                    if not after:  # No more pages
                        break
                    
                    print(f"Found {len(posts)} posts (total: {len(all_posts)})")
                    
                    # Respect rate limits
                    time.sleep(self.rate_limit_delay)
                else:
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Error getting posts from r/{subreddit}: {e}")
                break
        
        print(f"Total posts found: {len(all_posts)}")
        return all_posts[:max_posts]  # Return only up to max_posts

def main():
    searcher = RedditJSONSearcher()
    
    # Load configuration from input.json
    try:
        with open('subreddits/input.json', 'r') as f:
            config = json.load(f)
            subreddit = config['subreddit']
    except FileNotFoundError:
        print("Error: input.json file not found")
        exit(1)
    except json.JSONDecodeError:
        print("Error: input.json is not valid JSON")
        exit(1)
    except KeyError:
        print("Error: input.json must contain a 'subreddit' field, received: ", config)
        exit(1)
  
    help_posts = searcher.search_subreddit_paginated(subreddit, 'help', max_posts=100)
    
    if help_posts:
        print(f"\nFound {len(help_posts)} help posts:")
        for i, post in enumerate(help_posts[:10], 1):  # Show first 10 posts
            print(f"{i}. {post['title']}")
            print(f"   Author: {post['author']} | Score: {post['score']} | Comments: {post['num_comments']}")
            print(f"   URL: {post['url']}")
            print(f"   Created: {post['created_utc']}")
            if post['selftext']:
                print(f"   Text: {post['selftext'][:200]}...")
            print("-" * 80)
        
        if len(help_posts) > 10:
            print(f"... and {len(help_posts) - 10} more posts")
    
    # Respect rate limits
    time.sleep(searcher.rate_limit_delay)

    

if __name__ == "__main__":
    main() 