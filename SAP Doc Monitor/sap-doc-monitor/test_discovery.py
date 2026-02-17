"""
Test script to verify URL auto-discovery functionality
Run this to see which pages will be discovered from your base URL
"""

from fetcher.discover_urls import discover_documentation_urls
from config import settings

def main():
    print("\n" + "="*80)
    print("SAP Documentation URL Discovery Test")
    print("="*80 + "\n")
    
    base_url = settings.BASE_DOCUMENTATION_URL
    print(f"Base URL: {base_url}\n")
    
    # Discover URLs
    discovered_urls = discover_documentation_urls(base_url)
    
    if discovered_urls:
        print(f"\n{'='*80}")
        print(f"RESULTS: {len(discovered_urls)} pages discovered")
        print(f"{'='*80}\n")
        
        print("Discovered Documentation Pages:")
        print("-" * 80)
        for number, title, url in discovered_urls:
            print(f"\n{number}. {title}")
            print(f"   URL: {url}")
        
        print(f"\n{'='*80}")
        print(f"[+] These {len(discovered_urls)} pages will be monitored for changes")
        print(f"{'='*80}\n")
    else:
        print("\n[X] No pages discovered!")
        print("Possible reasons:")
        print("  1. The base URL might not contain a table of contents")
        print("  2. The page structure might be different than expected")
        print("  3. Network/access issues\n")
        print("Try checking the BASE_DOCUMENTATION_URL in settings.py\n")

if __name__ == "__main__":
    main()
