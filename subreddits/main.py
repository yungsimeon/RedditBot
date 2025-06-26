import json
import os
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List, Dict
from reddit_search import RedditJSONSearcher
from datetime import datetime

class RedditAnalyzer:
    def __init__(self):
        load_dotenv()
        
        # Configure Gemini API
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Please set GEMINI_API_KEY in your .env file")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    def load_input_config(self) -> Dict:
        """
        Load configuration from input.json file
        
        Returns:
            Dict: Configuration containing subreddit and other parameters
        """
        try:
            with open('subreddits/input.json', 'r') as f:
                config = json.load(f)
                if 'subreddit' not in config:
                    raise ValueError("input.json must contain a 'subreddit' field, received: ", config)
                return config
        except FileNotFoundError:
            print("Error: input.json file not found")
            exit(1)
        except json.JSONDecodeError:
            print("Error: input.json is not valid JSON")
            exit(1)
        except ValueError as e:
            print(f"Error: {str(e)}")
            exit(1)

    def prepare_posts_for_analysis(self, posts: List[Dict]) -> str:
        """
        Prepare Reddit posts data for Gemini analysis
        
        Args:
            posts (List[Dict]): List of Reddit posts
            
        Returns:
            str: Formatted string for analysis
        """
        formatted_posts = []
        
        for i, post in enumerate(posts, 1):
            formatted_post = f"""
Post {i}:
Title: {post['title']}
Author: {post['author']}
Score: {post['score']}
Comments: {post['num_comments']}
Created: {post['created_utc']}
Content: {post['selftext']}
URL: {post['url']}
"""
            formatted_posts.append(formatted_post)
        
        return "\n".join(formatted_posts)
    
    def analyze_help_posts(self, posts: List[Dict], subreddit: str) -> Dict:
        """
        Analyze Reddit help posts using Gemini
        
        Args:
            posts (List[Dict]): List of Reddit help posts
            subreddit (str): Name of the subreddit being analyzed
            
        Returns:
            Dict: Analysis results
        """
        if not posts:
            return {"error": "No posts to analyze"}
        
        # Prepare the data for analysis
        posts_text = self.prepare_posts_for_analysis(posts)
        
        # Create the prompt for Gemini
        prompt = f"""
You are an expert analyst specializing in user experience and technical support. I have collected {len(posts)} help-seeking posts from the r/{subreddit} subreddit. 

Please analyze these posts and provide a comprehensive summary of the problems users are facing. Focus on:

1. **Problem Categorization**: Group similar problems together
2. **Frequency Analysis**: Identify which problems occur most often
3. **Severity Assessment**: Rate problems by impact (high/medium/low)
4. **Common Patterns**: Identify recurring themes or patterns
5. **User Sentiment**: Overall sentiment of help requests
6. **Technical vs Non-Technical**: Distinguish between technical and user experience issues

Here are the posts to analyze:

{posts_text}

Please provide your analysis in the following JSON format:
{{
    "summary": "Brief overview of the analysis",
    "subreddit": "{subreddit}",
    "total_posts_analyzed": {len(posts)},
    "problem_categories": [
        {{
            "category": "Category name",
            "description": "Description of the problem type",
            "frequency": "Number of occurrences",
            "percentage": "Percentage of total posts",
            "severity": "high/medium/low",
            "example_posts": ["Post titles that exemplify this category"]
        }}
    ],
    "most_common_problems": [
        {{
            "problem": "Specific problem description",
            "count": "Number of occurrences",
            "impact": "Description of user impact"
        }}
    ],
    "user_sentiment": {{
        "overall_sentiment": "positive/negative/neutral",
        "frustration_level": "high/medium/low",
        "common_emotions": ["emotion1", "emotion2"]
    }},
    "recommendations": [
        "Specific recommendation 1",
        "Specific recommendation 2"
    ]
}}

Focus on being specific and actionable in your analysis.
"""
        
        try:
            # Generate analysis using Gemini
            response = self.model.generate_content(prompt)
            
            # Parse the JSON response
            analysis_text = response.text
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                start_idx = analysis_text.find('{')
                end_idx = analysis_text.rfind('}') + 1
                
                if start_idx != -1 and end_idx != 0:
                    json_str = analysis_text[start_idx:end_idx]
                    analysis = json.loads(json_str)
                else:
                    # If no JSON found, create a structured response
                    analysis = {
                        "raw_response": analysis_text,
                        "error": "Could not parse JSON response"
                    }
            except json.JSONDecodeError as e:
                analysis = {
                    "raw_response": analysis_text,
                    "error": f"JSON parsing error: {str(e)}"
                }
            
            return analysis
            
        except Exception as e:
            return {"error": f"Analysis failed: {str(e)}"}
    
    def save_analysis(self, analysis: Dict, subreddit: str):
        """
        Save analysis results to a JSON file with dynamic filename
        
        Args:
            analysis (Dict): Analysis results
            subreddit (str): Name of the subreddit
        """
        # Create timestamp for filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"subreddits/{subreddit}-{timestamp}.json"
        
        # Ensure the reddit directory exists
        os.makedirs("subreddits", exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        print(f"Analysis saved to {filename}")
    
    def print_analysis_summary(self, analysis: Dict):
        """
        Print a formatted summary of the analysis
        
        Args:
            analysis (Dict): Analysis results
        """
        if "error" in analysis:
            print(f"Error: {analysis['error']}")
            if "raw_response" in analysis:
                print("\nRaw Gemini Response:")
                print(analysis['raw_response'])
            return
        
        print("=" * 80)
        print("REDDIT HELP POSTS ANALYSIS")
        print("=" * 80)
        
        if "subreddit" in analysis:
            print(f"\nSubreddit: r/{analysis['subreddit']}")
        
        if "summary" in analysis:
            print(f"\nSUMMARY:")
            print(analysis['summary'])
        
        if "total_posts_analyzed" in analysis:
            print(f"\nTotal posts analyzed: {analysis['total_posts_analyzed']}")
        
        if "problem_categories" in analysis:
            print(f"\nPROBLEM CATEGORIES:")
            for category in analysis['problem_categories']:
                print(f"\n• {category['category']} ({category['frequency']} posts, {category['percentage']})")
                print(f"  Severity: {category['severity']}")
                print(f"  Description: {category['description']}")
                if category['example_posts']:
                    print(f"  Examples: {', '.join(category['example_posts'][:3])}")
        
        if "most_common_problems" in analysis:
            print(f"\nMOST COMMON PROBLEMS:")
            for i, problem in enumerate(analysis['most_common_problems'][:5], 1):
                print(f"{i}. {problem['problem']} ({problem['count']} occurrences)")
                print(f"   Impact: {problem['impact']}")
        
        if "user_sentiment" in analysis:
            sentiment = analysis['user_sentiment']
            print(f"\nUSER SENTIMENT:")
            print(f"• Overall: {sentiment['overall_sentiment']}")
            print(f"• Frustration Level: {sentiment['frustration_level']}")
            print(f"• Common Emotions: {', '.join(sentiment['common_emotions'])}")
        
        if "recommendations" in analysis:
            print(f"\nRECOMMENDATIONS:")
            for i, rec in enumerate(analysis['recommendations'], 1):
                print(f"{i}. {rec}")

def main():
    # Initialize the analyzer
    analyzer = RedditAnalyzer()
    
    # Load configuration from input.json
    config = analyzer.load_input_config()
    subreddit = config['subreddit']
    search_query = config['search_query']
    # Get Reddit posts
    print(f"Fetching Reddit help posts from r/{subreddit}...")
    searcher = RedditJSONSearcher()
    
    # Search for help posts with pagination
    help_posts = searcher.search_subreddit_paginated(subreddit, search_query, max_posts=100)
    
    if not help_posts:
        print("No help posts found!")
        return
    
    print(f"Found {len(help_posts)} help posts. Analyzing with Gemini...")
    
    # Analyze the posts
    analysis = analyzer.analyze_help_posts(help_posts, subreddit)
    
    # Print the analysis
    analyzer.print_analysis_summary(analysis)
    
    # Save the analysis with dynamic filename
    analyzer.save_analysis(analysis, subreddit)
    
    # Also save the raw posts for reference
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_filename = f"subreddits/{subreddit}-posts-{timestamp}.json"
    os.makedirs("subreddits", exist_ok=True)
    searcher.save_results_to_json(help_posts, raw_filename)

if __name__ == "__main__":
    main() 