#!/usr/bin/env python3
"""
Verify MCP authentication by calculating the correct endpoint URL
"""

import hashlib
import os
import sys


def _mask(value: str, show: int = 4) -> str:
    """Mask a secret, keeping only the first and last few characters."""
    if not value:
        return ""
    if len(value) <= show * 2:
        return "*" * len(value)
    return f"{value[:show]}...{value[-show:]}"


def redact_result(result: dict) -> dict:
    """Return a copy of the result dict with secret values masked."""
    masked_key = _mask(result["api_key"])
    masked_hash = _mask(result["api_key_hash"], show=8)
    redacted = dict(result)
    redacted["api_key"] = masked_key
    redacted["api_key_hash"] = masked_hash
    redacted["endpoints"] = {
        "mcp": result["endpoints"]["mcp"]
        .replace(result["api_key"], masked_key)
        .replace(result["api_key_hash"], masked_hash),
        "health": result["endpoints"]["health"],
    }
    return redacted


def calculate_mcp_url(
    api_key: str, domain: str = "your-domain.com", https: bool = True, md5_salt: str = ""
) -> dict:
    """Calculate MCP endpoint URLs with dual-factor authentication"""

    # Calculate hash of API key with optional salt
    hash_input = f"{md5_salt}{api_key}" if md5_salt else api_key

    # Use SHA-256 to match server_remote.py and avoid weak-hash usage
    api_key_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    # Build URLs
    protocol = "https" if https else "http"
    base_url = f"{protocol}://{domain}"

    return {
        "api_key": api_key,
        "api_key_hash": api_key_hash,
        "md5_salt_used": bool(md5_salt),
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
  export MD5_SALT="your-salt"
  python verify_auth.py --domain your-domain.com

  # From command line with salt
  python verify_auth.py --api-key your-api-key --md5-salt your-salt --domain your-domain.com

  # Without salt (legacy mode)
  python verify_auth.py --api-key your-api-key --domain your-domain.com

  # Local testing (HTTP)
  python verify_auth.py --api-key test-key --md5-salt test-salt --domain localhost:8080 --no-https
        """
    )

    parser.add_argument(
        "--api-key",
        help="API key (or set MCP_API_KEY environment variable)",
        default=os.getenv("MCP_API_KEY")
    )
    parser.add_argument(
        "--md5-salt",
        help="MD5 salt (or set MD5_SALT environment variable)",
        default=os.getenv("MD5_SALT", "")
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
    parser.add_argument(
        "--show-secrets",
        help="Print the full API key, hash, and endpoint URL instead of redacted values",
        action="store_true"
    )

    args = parser.parse_args()

    if not args.api_key:
        parser.print_help()
        print("\n❌ Error: API key required (use --api-key or set MCP_API_KEY)", file=sys.stderr)
        sys.exit(1)

    # Calculate URLs; redact secrets unless explicitly requested otherwise
    result = calculate_mcp_url(args.api_key, args.domain, not args.no_https, args.md5_salt)
    output = result if args.show_secrets else redact_result(result)

    # Output
    if args.json:
        import json
        print(json.dumps(output, indent=2))
    else:
        print()
        print("═" * 70)
        print("  Todoist MCP Endpoint URL Calculator")
        print("═" * 70)
        print()
        print(f"API Key:         {output['api_key']}")
        print(f"API Key Hash:    {output['api_key_hash']}")
        print(f"MD5 Salt:        {'Yes (configured)' if output['md5_salt_used'] else 'No (using legacy mode)'}")
        print(f"Domain:          {output['domain']}")
        print(f"Protocol:        {output['protocol']}")
        print()
        print("Endpoints:")
        print(f"  MCP (authenticated):  {output['endpoints']['mcp']}")
        print(f"  Health (public):      {output['endpoints']['health']}")
        print()
        if args.show_secrets:
            print("⚠️  Keep the MCP URL confidential. It contains authentication credentials.")
        else:
            print("🔒  Secrets are redacted. Re-run with --show-secrets to print the full URL.")
        if not result['md5_salt_used']:
            print("⚠️  Consider setting MD5_SALT environment variable for enhanced security.")
        print()


if __name__ == "__main__":
    main()
