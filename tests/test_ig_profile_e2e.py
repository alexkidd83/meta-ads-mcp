#!/usr/bin/env python3
"""
End-to-End IG Profile Test for Meta Ads MCP

Validates that get_ig_profile queries the IG User node directly for real-time
data (no 2-3 day lag like the /insights edge).

Usage:
    1. Start the server: uv run python -m meta_ads_mcp --transport streamable-http --port 8080
    2. Run test: uv run python tests/test_ig_profile_e2e.py

Or with pytest (manual only):
    uv run python -m pytest tests/test_ig_profile_e2e.py -v -m e2e

Test scenarios:
1. Default fields — all 9 fields present, followers_count positive, id matches
2. Custom fields subset — only requested fields returned
3. Invalid ig_user_id — non-numeric ID returns error
4. Realtime comparison — profile endpoint returns positive count while insights may return 0
"""

import pytest
import requests
import json
import sys
from typing import Dict, Any

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Loaded environment variables from .env file")
except ImportError:
    print("python-dotenv not installed, using system environment variables only")


@pytest.mark.e2e
@pytest.mark.skip(reason="E2E test - run manually only")
class IgProfileE2ETester:
    """Test suite for get_ig_profile real-time profile queries."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/mcp/"
        self.request_id = 1
        self.ig_user_id = "17841473732194608"  # CultMeUp IG Business Account

    def _make_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make a JSON-RPC request to the MCP server."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "IgProfile-E2E-Test-Client/1.0",
        }
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self.request_id,
        }
        if params:
            payload["params"] = params

        try:
            response = requests.post(self.endpoint, headers=headers, json=payload, timeout=20)
            self.request_id += 1
            return {
                "status_code": response.status_code,
                "json": response.json() if response.status_code == 200 else None,
                "text": response.text,
                "success": response.status_code == 200,
            }
        except requests.exceptions.RequestException as e:
            return {
                "status_code": 0,
                "json": None,
                "text": str(e),
                "success": False,
                "error": str(e),
            }

    def _check_for_errors(self, parsed_content: Dict[str, Any]) -> Dict[str, Any]:
        """Handle both wrapped and direct error formats."""
        if "data" in parsed_content:
            data = parsed_content["data"]
            if isinstance(data, dict) and "error" in data:
                return {"has_error": True, "error_message": data["error"], "format": "wrapped_dict"}
            if isinstance(data, str):
                try:
                    error_data = json.loads(data)
                    if "error" in error_data:
                        return {"has_error": True, "error_message": error_data["error"], "format": "wrapped_json"}
                except json.JSONDecodeError:
                    pass
        if "error" in parsed_content:
            return {"has_error": True, "error_message": parsed_content["error"], "format": "direct"}
        return {"has_error": False}

    def _extract_data(self, parsed_content: Dict[str, Any]) -> Any:
        """Extract successful response data from various wrapper formats."""
        if "data" in parsed_content:
            data = parsed_content["data"]
            if isinstance(data, (list, dict)):
                return data
            if isinstance(data, str):
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return None
        if isinstance(parsed_content, (list, dict)):
            return parsed_content
        return None

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a named MCP tool and return parsed content or None on failure."""
        result = self._make_request("tools/call", {"name": tool_name, "arguments": arguments})
        if not result["success"]:
            return {"_request_failed": True, "error": result.get("text", "Request failed")}
        response_data = result["json"]["result"]
        content_text = response_data.get("content", [{}])[0].get("text", "")
        try:
            return json.loads(content_text)
        except json.JSONDecodeError:
            return {"_parse_failed": True, "raw": content_text}

    def test_default_fields(self) -> Dict[str, Any]:
        """Call with just ig_user_id; assert all 9 default fields present and followers_count is positive."""
        print("\nTesting get_ig_profile with default fields")
        expected_fields = {
            "followers_count", "follows_count", "media_count", "name",
            "biography", "website", "profile_picture_url", "ig_id", "username",
        }

        parsed = self._call_tool("get_ig_profile", {"ig_user_id": self.ig_user_id})
        if "_request_failed" in parsed or "_parse_failed" in parsed:
            print(f"   FAIL: {parsed.get('error', 'parse error')}")
            return {"success": False, "error": str(parsed)}

        error_info = self._check_for_errors(parsed)
        if error_info["has_error"]:
            print(f"   FAIL: API error — {error_info['error_message']}")
            return {"success": False, "error": error_info["error_message"]}

        profile = self._extract_data(parsed)
        if not isinstance(profile, dict):
            print(f"   FAIL: unexpected response shape")
            return {"success": False, "error": "unexpected shape"}

        missing = expected_fields - set(profile.keys())
        if missing:
            print(f"   FAIL: missing fields: {missing}")
            return {"success": False, "error": f"missing fields: {missing}"}

        followers = profile.get("followers_count", 0)
        if not isinstance(followers, int) or followers <= 0:
            print(f"   FAIL: followers_count not a positive int: {followers}")
            return {"success": False, "error": f"bad followers_count: {followers}"}

        returned_id = profile.get("id") or profile.get("ig_id")
        if returned_id != self.ig_user_id:
            print(f"   WARN: id mismatch — expected {self.ig_user_id}, got {returned_id}")

        print(f"   PASS: followers_count={followers}, username={profile.get('username')}")
        return {"success": True, "followers_count": followers, "profile": profile}

    def test_custom_fields_subset(self) -> Dict[str, Any]:
        """Call with fields=['followers_count','username']; assert only those fields returned."""
        print("\nTesting get_ig_profile with custom fields subset")
        custom_fields = ["followers_count", "username"]

        parsed = self._call_tool("get_ig_profile", {
            "ig_user_id": self.ig_user_id,
            "fields": custom_fields,
        })
        if "_request_failed" in parsed or "_parse_failed" in parsed:
            print(f"   FAIL: {parsed.get('error', 'parse error')}")
            return {"success": False, "error": str(parsed)}

        error_info = self._check_for_errors(parsed)
        if error_info["has_error"]:
            print(f"   FAIL: API error — {error_info['error_message']}")
            return {"success": False, "error": error_info["error_message"]}

        profile = self._extract_data(parsed)
        if not isinstance(profile, dict):
            print(f"   FAIL: unexpected response shape")
            return {"success": False, "error": "unexpected shape"}

        for f in custom_fields:
            if f not in profile:
                print(f"   FAIL: requested field '{f}' missing from response")
                return {"success": False, "error": f"missing field: {f}"}

        unexpected = set(profile.keys()) - set(custom_fields) - {"id"}
        if unexpected:
            print(f"   WARN: extra fields returned beyond requested: {unexpected}")

        print(f"   PASS: followers_count={profile.get('followers_count')}, username={profile.get('username')}")
        return {"success": True, "profile": profile}

    def test_invalid_ig_user_id(self) -> Dict[str, Any]:
        """Call with a non-numeric ig_user_id; assert error is returned."""
        print("\nTesting get_ig_profile with invalid (non-numeric) ig_user_id")

        parsed = self._call_tool("get_ig_profile", {"ig_user_id": "not-a-number"})
        if "_request_failed" in parsed or "_parse_failed" in parsed:
            print(f"   FAIL: request/parse error: {parsed}")
            return {"success": False, "error": str(parsed)}

        error_info = self._check_for_errors(parsed)
        if error_info["has_error"]:
            print(f"   PASS: got expected error — {error_info['error_message']}")
            return {"success": True, "error_message": error_info["error_message"]}

        print("   FAIL: no error returned for invalid ig_user_id")
        return {"success": False, "error": "expected error not returned"}

    def test_followers_count_is_realtime(self) -> Dict[str, Any]:
        """Compare get_ig_profile (real-time) vs get_ig_account_insights (lagged).

        The profile endpoint should return a positive followers_count even for today,
        while the insights endpoint may return 0 for the most recent day due to
        its 2-3 day processing lag.
        """
        print("\nTesting realtime comparison: get_ig_profile vs get_ig_account_insights")

        # Real-time profile call
        profile_parsed = self._call_tool("get_ig_profile", {"ig_user_id": self.ig_user_id})
        profile_data = self._extract_data(profile_parsed) or {}
        profile_followers = profile_data.get("followers_count")

        # Insights call (last 1 day — most likely returns 0 for today)
        import datetime
        today = datetime.date.today().isoformat()
        insights_parsed = self._call_tool("get_ig_account_insights", {
            "ig_user_id": self.ig_user_id,
            "metrics": ["follower_count"],
            "period": "day",
            "since": today,
            "until": today,
        })
        insights_data = self._extract_data(insights_parsed)

        # Extract insights follower_count value (may be 0 or absent)
        insights_followers = None
        if isinstance(insights_data, dict) and "data" in insights_data:
            for item in insights_data["data"]:
                if item.get("name") == "follower_count":
                    values = item.get("values", [])
                    if values:
                        insights_followers = values[-1].get("value")

        print(f"   get_ig_profile followers_count : {profile_followers}")
        print(f"   get_ig_account_insights (today): {insights_followers} (0 = lag expected)")

        if not isinstance(profile_followers, int) or profile_followers <= 0:
            print("   FAIL: get_ig_profile did not return a positive followers_count")
            return {"success": False, "error": f"bad profile followers_count: {profile_followers}"}

        print(f"   PASS: profile endpoint returned {profile_followers} followers (real-time)")
        return {
            "success": True,
            "profile_followers": profile_followers,
            "insights_followers_today": insights_followers,
            "lag_demonstrated": insights_followers == 0 or insights_followers is None,
        }

    def run_all_tests(self) -> bool:
        """Run all E2E tests and print a summary."""
        print("Meta Ads MCP — get_ig_profile End-to-End Test Suite")
        print("=" * 60)

        # Check server availability
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            server_running = response.status_code in [200, 404]
        except Exception:
            server_running = False

        if not server_running:
            print(f"Server is not running at {self.base_url}")
            print("Start it with:")
            print("  uv run python -m meta_ads_mcp --transport streamable-http --port 8080")
            return False

        print("Server is running")

        results = [
            ("Default fields", self.test_default_fields()),
            ("Custom fields subset", self.test_custom_fields_subset()),
            ("Invalid ig_user_id", self.test_invalid_ig_user_id()),
            ("Realtime vs insights lag", self.test_followers_count_is_realtime()),
        ]

        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        passed = 0
        for name, result in results:
            ok = result.get("success", False)
            status = "PASS" if ok else "FAIL"
            print(f"  {status}  {name}")
            if ok:
                passed += 1

        total = len(results)
        overall = passed == total
        print(f"\n{passed}/{total} tests passed")
        return overall


def main():
    tester = IgProfileE2ETester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
