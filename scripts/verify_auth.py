#!/usr/bin/env python3
"""
Verify MCP authentication by calculating the correct endpoint URL
"""

import sys
import hashlib
import os


def calculate_mcp_url(api_key: str, domain: str = "your-domain.com", https: bool = True) -> dict:
    """Calculate MCP endpoint URLs with dual-factor authentication"""

    # Calculate MD5 hash of API key
    api_key_hash = hashlib.md5(api_key.encode()).hexdigest()

    # Build URLs
    protocol = "https" if https else "http"
    base_url = f"{protocol}://{domain}"

    return {
        "api_key": api_key,
        "api_key_hash": api_key_hash,
        "domain": domain,
        "protocol": protocol,
        "endpoints": {
            "mcp": f"{base_url}/app/{api_key}/{api_key_hash}/mcp",
            "health": f"{base_url}/app/health"
        }
    }


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Calculate MCP endpoint URLs with dual-factor authentication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From environment variable
  export MCP_API_KEY="your-api-key"
  python verify_auth.py --domain your-domain.com

  # From command line
  python verify_auth.py --api-key your-api-key --domain your-domain.com

  # Local testing (HTTP)
  python verify_auth.py --api-key test-key --domain localhost:8080 --no-https
        """
    )

    parser.add_argument(
        "--api-key",
        help="API key (or set MCP_API_KEY environment variable)",
        default=os.getenv("MCP_API_KEY")
    )
    parser.add_argument(
        "--domain",
        help="Domain name (default: your-domain.com)",
        default="your-domain.com"
    )
    parser.add_argument(
        "--no-https",
        help="Use HTTP instead of HTTPS",
        action="store_true"
    )
    parser.add_argument(
        "--json",
        help="Output as JSON",
        action="store_true"
    )

    args = parser.parse_args()

    if not args.api_key:
        parser.print_help()
        print("\n❌ Error: API key required (use --api-key or set MCP_API_KEY)", file=sys.stderr)
        sys.exit(1)

    # Calculate URLs
    result = calculate_mcp_url(args.api_key, args.domain, not args.no_https)

    # Output
    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        print()
        print("═" * 70)
        print("  Todoist MCP Endpoint URL Calculator")
        print("═" * 70)
        print()
        print(f"API Key:         {result['api_key']}")
        print(f"API Key Hash:    {result['api_key_hash']}")
        print(f"Domain:          {result['domain']}")
        print(f"Protocol:        {result['protocol']}")
        print()
        print("Endpoints:")
        print(f"  MCP (authenticated):  {result['endpoints']['mcp']}")
        print(f"  Health (public):      {result['endpoints']['health']}")
        print()
        print("⚠️  Keep the MCP URL confidential. It contains authentication credentials.")
        print()


if __name__ == "__main__":
    main()
