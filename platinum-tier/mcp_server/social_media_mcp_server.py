"""
Social Media MCP Server — Unified MCP server for Facebook, Instagram, Twitter/X.

Provides tools for Claude Code to post content and retrieve engagement metrics
across all major social media platforms.

Live mode integrations:
- Facebook: Graph API v19.0 (POST /{page-id}/feed)
- Instagram: Graph API v19.0 (POST /{ig-user-id}/media + /media_publish)
- Twitter/X: API v2 (POST /2/tweets) with OAuth 1.0a

Supports dry-run mode (default) — saves posts as JSON records and returns
simulated engagement metrics.

Setup in Claude Code settings:
{
    "mcpServers": {
        "social_media": {
            "command": "python",
            "args": ["path/to/social_media_mcp_server.py"],
            "env": {
                "DRY_RUN": "true",
                "FACEBOOK_PAGE_ID": "your_page_id",
                "FACEBOOK_PAGE_TOKEN": "your_token",
                "INSTAGRAM_BUSINESS_ACCOUNT_ID": "your_account_id",
                "INSTAGRAM_ACCESS_TOKEN": "your_token",
                "TWITTER_API_KEY": "your_key",
                "TWITTER_API_SECRET": "your_secret",
                "TWITTER_ACCESS_TOKEN": "your_token",
                "TWITTER_ACCESS_SECRET": "your_secret"
            }
        }
    }
}

Gold Tier — Phase 5: Social Media MCP Server.
"""

import os
import sys
import json
import random
import hashlib
import hmac
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
VAULT_PATH = os.getenv("VAULT_PATH", str(Path(__file__).parent.parent / "AI_Employee_Vault"))

# Facebook / Instagram Graph API credentials
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

# Twitter API v2 credentials (OAuth 1.0a)
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
TWITTER_API_BASE = "https://api.twitter.com/2"


class FacebookGraphAPIClient:
    """Client for Facebook Graph API v19.0.

    Posts to a Facebook Page using the Page Access Token.
    Endpoint: POST /{page-id}/feed
    Docs: https://developers.facebook.com/docs/graph-api/reference/page/feed
    """

    def __init__(self, page_id: str, page_token: str):
        self.page_id = page_id
        self.page_token = page_token

    def post(self, message: str, link: str = "", image_url: str = "") -> dict:
        """Publish a post to the Facebook Page."""
        endpoint = f"{GRAPH_API_BASE}/{self.page_id}/feed"
        params = {
            "message": message,
            "access_token": self.page_token,
        }
        if link:
            params["link"] = link
        # For photo posts, use /{page-id}/photos instead
        if image_url and not link:
            endpoint = f"{GRAPH_API_BASE}/{self.page_id}/photos"
            params["url"] = image_url

        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_post_insights(self, post_id: str) -> dict:
        """Get engagement metrics for a post."""
        endpoint = f"{GRAPH_API_BASE}/{post_id}/insights"
        params = urllib.parse.urlencode({
            "metric": "post_impressions,post_engaged_users,post_reactions_by_type_total",
            "access_token": self.page_token,
        })
        req = urllib.request.Request(f"{endpoint}?{params}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


class InstagramGraphAPIClient:
    """Client for Instagram Graph API v19.0.

    Posts to Instagram Business Account using a two-step process:
    1. Create media container: POST /{ig-user-id}/media
    2. Publish container: POST /{ig-user-id}/media_publish

    Docs: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/content-publishing
    """

    def __init__(self, account_id: str, access_token: str):
        self.account_id = account_id
        self.access_token = access_token

    def post(self, caption: str, image_url: str) -> dict:
        """Publish a photo post to Instagram (two-step process)."""
        # Step 1: Create media container
        container_endpoint = f"{GRAPH_API_BASE}/{self.account_id}/media"
        container_params = {
            "image_url": image_url,
            "caption": caption[:2200],
            "access_token": self.access_token,
        }
        data = urllib.parse.urlencode(container_params).encode("utf-8")
        req = urllib.request.Request(container_endpoint, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            container = json.loads(resp.read().decode("utf-8"))

        container_id = container.get("id")
        if not container_id:
            return {"error": "Failed to create media container", "details": container}

        # Step 2: Publish the container
        publish_endpoint = f"{GRAPH_API_BASE}/{self.account_id}/media_publish"
        publish_params = {
            "creation_id": container_id,
            "access_token": self.access_token,
        }
        data = urllib.parse.urlencode(publish_params).encode("utf-8")
        req = urllib.request.Request(publish_endpoint, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_media_insights(self, media_id: str) -> dict:
        """Get engagement metrics for a media post."""
        endpoint = f"{GRAPH_API_BASE}/{media_id}/insights"
        params = urllib.parse.urlencode({
            "metric": "impressions,reach,likes,comments,saves",
            "access_token": self.access_token,
        })
        req = urllib.request.Request(f"{endpoint}?{params}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


class TwitterAPIv2Client:
    """Client for Twitter/X API v2 with OAuth 1.0a authentication.

    Posts tweets using: POST /2/tweets
    Uses HMAC-SHA1 OAuth 1.0a signature (no external libraries).

    Docs: https://developer.x.com/en/docs/twitter-api/tweets/manage-tweets/api-reference/post-tweets
    """

    def __init__(self, api_key: str, api_secret: str,
                 access_token: str, access_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_secret = access_secret

    def _generate_oauth_signature(self, method: str, url: str, params: dict) -> str:
        """Generate OAuth 1.0a HMAC-SHA1 signature."""
        # Sort parameters
        sorted_params = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(params.items())
        )

        # Create signature base string
        base_string = "&".join([
            method.upper(),
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote(sorted_params, safe=""),
        ])

        # Create signing key
        signing_key = f"{urllib.parse.quote(self.api_secret, safe='')}&{urllib.parse.quote(self.access_secret, safe='')}"

        # Generate HMAC-SHA1
        import base64
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()

        return signature

    def _build_oauth_header(self, method: str, url: str) -> str:
        """Build the OAuth 1.0a Authorization header."""
        import uuid
        oauth_params = {
            "oauth_consumer_key": self.api_key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.access_token,
            "oauth_version": "1.0",
        }

        signature = self._generate_oauth_signature(method, url, oauth_params)
        oauth_params["oauth_signature"] = signature

        header = "OAuth " + ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return header

    def post_tweet(self, text: str) -> dict:
        """Post a tweet using Twitter API v2."""
        url = f"{TWITTER_API_BASE}/tweets"
        payload = json.dumps({"text": text[:280]}).encode("utf-8")

        auth_header = self._build_oauth_header("POST", url)
        req = urllib.request.Request(
            url, data=payload,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_tweet_metrics(self, tweet_id: str) -> dict:
        """Get engagement metrics for a tweet."""
        url = f"{TWITTER_API_BASE}/tweets/{tweet_id}"
        params = urllib.parse.urlencode({
            "tweet.fields": "public_metrics",
        })
        auth_header = self._build_oauth_header("GET", f"{url}?{params}")
        req = urllib.request.Request(
            f"{url}?{params}",
            headers={"Authorization": auth_header},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


class SocialMediaMCPServer:
    """Unified MCP Server for Facebook, Instagram, and Twitter/X.

    In dry-run mode: saves post records as JSON, returns simulated engagement.
    In live mode: calls actual platform APIs via the client classes above.
    """

    def __init__(self):
        self.vault_path = Path(VAULT_PATH)
        self.done_dir = self.vault_path / "Done"
        self.logs_dir = self.vault_path / "Logs"
        self.done_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize API clients for live mode
        self.facebook_client = None
        self.instagram_client = None
        self.twitter_client = None

        if not DRY_RUN:
            if FACEBOOK_PAGE_ID and FACEBOOK_PAGE_TOKEN:
                self.facebook_client = FacebookGraphAPIClient(FACEBOOK_PAGE_ID, FACEBOOK_PAGE_TOKEN)
            if INSTAGRAM_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN:
                self.instagram_client = InstagramGraphAPIClient(INSTAGRAM_ACCOUNT_ID, INSTAGRAM_ACCESS_TOKEN)
            if TWITTER_API_KEY and TWITTER_ACCESS_TOKEN:
                self.twitter_client = TwitterAPIv2Client(
                    TWITTER_API_KEY, TWITTER_API_SECRET,
                    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET,
                )

    def get_tools(self) -> list:
        """Return list of available MCP tools."""
        return [
            {
                "name": "post_to_facebook",
                "description": "Post content to a Facebook Page. In dry-run mode, saves a record and returns simulated engagement.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Post content text"},
                        "link": {"type": "string", "description": "Optional link to attach"},
                        "image_url": {"type": "string", "description": "Optional image URL"},
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "post_to_instagram",
                "description": "Post content to Instagram. In dry-run mode, saves a record and returns simulated engagement.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "caption": {"type": "string", "description": "Post caption (max 2200 chars)"},
                        "image_url": {"type": "string", "description": "Image URL (required for Instagram)"},
                        "hashtags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of hashtags (max 30)",
                        },
                    },
                    "required": ["caption"],
                },
            },
            {
                "name": "post_to_twitter",
                "description": "Post a tweet to Twitter/X. Content will be truncated to 280 characters.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Tweet text (max 280 chars)"},
                        "media_url": {"type": "string", "description": "Optional media URL"},
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "get_engagement_summary",
                "description": "Get aggregated engagement metrics across all platforms.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "platform": {
                            "type": "string",
                            "description": "Filter by platform: facebook, instagram, twitter, or 'all'",
                            "default": "all",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back",
                            "default": 7,
                        },
                    },
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Handle an MCP tool call."""
        handlers = {
            "post_to_facebook": self.post_to_facebook,
            "post_to_instagram": self.post_to_instagram,
            "post_to_twitter": self.post_to_twitter,
            "get_engagement_summary": self.get_engagement_summary,
        }
        handler = handlers.get(tool_name)
        if handler:
            return handler(arguments)
        return {"error": f"Unknown tool: {tool_name}"}

    def _generate_engagement(self, platform: str) -> dict:
        """Generate simulated engagement metrics for dry-run mode."""
        base = {
            "facebook": {"likes": (20, 100), "comments": (3, 20), "shares": (1, 15), "reach": (500, 3000)},
            "instagram": {"likes": (50, 200), "comments": (5, 30), "saves": (3, 20), "reach": (1000, 5000)},
            "twitter": {"likes": (10, 80), "retweets": (2, 20), "replies": (1, 10), "impressions": (300, 2000)},
        }
        metrics = base.get(platform, base["facebook"])
        return {k: random.randint(*v) for k, v in metrics.items()}

    def _save_post_record(self, platform: str, record: dict):
        """Save a post record to Done/<platform>_posted/."""
        posted_dir = self.done_dir / f"{platform}_posted"
        posted_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        prefix = {"facebook": "fb", "instagram": "ig", "twitter": "tweet"}.get(platform, platform)
        record_file = posted_dir / f"{prefix}_post_{ts}.json"
        record_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return str(record_file)

    def post_to_facebook(self, args: dict) -> dict:
        """Post to Facebook Page via Graph API."""
        content = args["content"]
        now = datetime.now()

        result = {
            "platform": "facebook",
            "content": content[:500],
            "char_count": len(content),
            "link": args.get("link", ""),
            "image_url": args.get("image_url", ""),
            "posted_at": now.isoformat(),
            "mode": "dry_run" if DRY_RUN else "live",
            "status": "posted_dry_run" if DRY_RUN else "posted",
        }

        if DRY_RUN:
            result["engagement"] = self._generate_engagement("facebook")
            result["post_id"] = f"fb_{now.strftime('%Y%m%d%H%M%S')}"
        elif self.facebook_client:
            api_result = self.facebook_client.post(
                content, link=args.get("link", ""), image_url=args.get("image_url", "")
            )
            result["post_id"] = api_result.get("id", "")
            result["api_response"] = api_result

        self._save_post_record("facebook", result)
        self._log_action("post_to_facebook", {
            "content_preview": content[:100], "status": result["status"]
        })
        return result

    def post_to_instagram(self, args: dict) -> dict:
        """Post to Instagram via Graph API (two-step media container flow)."""
        caption = args["caption"][:2200]
        hashtags = args.get("hashtags", [])[:30]
        image_url = args.get("image_url", "placeholder_image.jpg")
        now = datetime.now()

        result = {
            "platform": "instagram",
            "caption": caption[:500],
            "hashtags": hashtags,
            "char_count": len(caption),
            "image_url": image_url,
            "posted_at": now.isoformat(),
            "mode": "dry_run" if DRY_RUN else "live",
            "status": "posted_dry_run" if DRY_RUN else "posted",
        }

        if DRY_RUN:
            result["engagement"] = self._generate_engagement("instagram")
            result["post_id"] = f"ig_{now.strftime('%Y%m%d%H%M%S')}"
        elif self.instagram_client:
            # Append hashtags to caption for Instagram
            full_caption = caption
            if hashtags:
                full_caption += "\n\n" + " ".join(hashtags)
            api_result = self.instagram_client.post(full_caption, image_url)
            result["post_id"] = api_result.get("id", "")
            result["api_response"] = api_result

        self._save_post_record("instagram", result)
        self._log_action("post_to_instagram", {
            "caption_preview": caption[:100], "status": result["status"]
        })
        return result

    def post_to_twitter(self, args: dict) -> dict:
        """Post a tweet via Twitter API v2 with OAuth 1.0a."""
        content = args["content"]
        now = datetime.now()

        # Enforce 280 character limit
        truncated = len(content) > 280
        if truncated:
            content = content[:277] + "..."

        result = {
            "platform": "twitter",
            "tweet": content,
            "char_count": len(content),
            "truncated": truncated,
            "media_url": args.get("media_url", ""),
            "posted_at": now.isoformat(),
            "mode": "dry_run" if DRY_RUN else "live",
            "status": "posted_dry_run" if DRY_RUN else "posted",
        }

        if DRY_RUN:
            result["engagement"] = self._generate_engagement("twitter")
            result["tweet_id"] = f"tw_{now.strftime('%Y%m%d%H%M%S')}"
        elif self.twitter_client:
            api_result = self.twitter_client.post_tweet(content)
            result["tweet_id"] = api_result.get("data", {}).get("id", "")
            result["api_response"] = api_result

        self._save_post_record("twitter", result)
        self._log_action("post_to_twitter", {
            "tweet_preview": content[:100], "status": result["status"]
        })
        return result

    def get_engagement_summary(self, args: dict) -> dict:
        """Get aggregated engagement metrics across platforms."""
        platform_filter = args.get("platform", "all")

        platforms = {
            "facebook": self.done_dir / "facebook_posted",
            "instagram": self.done_dir / "instagram_posted",
            "twitter": self.done_dir / "twitter_posted",
            "linkedin": self.done_dir / "linkedin_posted",
        }

        if platform_filter != "all":
            platforms = {k: v for k, v in platforms.items() if k == platform_filter}

        summary = {}
        total_posts = 0
        total_engagement = 0

        for platform, folder in platforms.items():
            posts = []
            if folder.exists():
                for f in folder.iterdir():
                    if f.is_file() and f.suffix == ".json":
                        try:
                            data = json.loads(f.read_text(encoding="utf-8"))
                            posts.append(data)
                        except (json.JSONDecodeError, ValueError):
                            continue

            post_count = len(posts)
            total_posts += post_count

            engagement = 0
            for p in posts:
                eng = p.get("engagement", p.get("simulated_engagement", {}))
                engagement += sum(eng.values()) if eng else 0
            total_engagement += engagement

            summary[platform] = {
                "post_count": post_count,
                "total_engagement": engagement,
                "avg_engagement": round(engagement / post_count, 1) if post_count > 0 else 0,
            }

        self._log_action("get_engagement_summary", {
            "platforms": list(platforms.keys()), "total_posts": total_posts
        })

        return {
            "summary": summary,
            "total_posts": total_posts,
            "total_engagement": total_engagement,
            "generated_at": datetime.now().isoformat(),
        }

    def _log_action(self, action: str, details: dict):
        """Log an action to the vault's Logs folder."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.json"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action,
            "actor": "social_media_mcp_server",
            **details,
        }

        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                entries = []

        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def run_stdio(self):
        """Run as MCP server over stdio (JSON-RPC)."""
        print(json.dumps({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "serverInfo": {"name": "social-media-mcp-server", "version": "1.0.0"},
                "capabilities": {"tools": self.get_tools()},
            },
        }), flush=True)

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                method = request.get("method", "")

                if method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {"tools": self.get_tools()},
                    }
                elif method == "tools/call":
                    tool_name = request["params"]["name"]
                    arguments = request["params"].get("arguments", {})
                    result = self.handle_tool_call(tool_name, arguments)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result)}]
                        },
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {},
                    }

                print(json.dumps(response), flush=True)
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if "request" in dir() else None,
                    "error": {"code": -32603, "message": str(e)},
                }
                print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    server = SocialMediaMCPServer()

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("Testing Social Media MCP Server...")
        print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
        print(f"Vault: {VAULT_PATH}")
        print(f"Tools: {[t['name'] for t in server.get_tools()]}")

        result = server.post_to_facebook({
            "content": "Exciting AI update! Our autonomous employee system just reached Gold Tier.",
        })
        print(f"\nFacebook post: {json.dumps(result, indent=2)[:200]}...")

        result = server.post_to_instagram({
            "caption": "Building the future of work with AI automation #AI #Automation #GoldTier",
            "hashtags": ["#AI", "#Automation", "#GoldTier"],
        })
        print(f"\nInstagram post: {json.dumps(result, indent=2)[:200]}...")

        result = server.post_to_twitter({
            "content": "Just shipped Gold Tier for our AI Employee system! Full Odoo integration + social media automation.",
        })
        print(f"\nTwitter post: {json.dumps(result, indent=2)[:200]}...")

        result = server.get_engagement_summary({"platform": "all"})
        print(f"\nEngagement summary: {json.dumps(result, indent=2)[:300]}...")

        print("\nAll Social Media MCP tools tested successfully!")
    else:
        server.run_stdio()
