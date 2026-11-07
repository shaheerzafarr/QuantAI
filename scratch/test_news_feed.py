import requests
import xml.etree.ElementTree as ET

def test_live_news_feed():
    # 1. Test CryptoPanic public endpoint
    print("Testing CryptoPanic public API...")
    try:
        cp_resp = requests.get("https://cryptopanic.com/api/free/v1/posts/?auth_token=none&public=true", timeout=5)
        print("CryptoPanic Status:", cp_resp.status_code)
    except Exception as e:
        print("CryptoPanic Error:", e)

    # 2. Test CoinDesk RSS Feed
    print("\nTesting CoinDesk RSS feed...")
    try:
        r = requests.get("https://www.coindesk.com/arc/outboundfeeds/rss/", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        print("CoinDesk RSS Status:", r.status_code)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            print(f"CoinDesk Headlines found: {len(items)}")
            for item in items[:3]:
                title = item.find("title").text if item.find("title") is not None else ""
                print(f"  -> {title}")
    except Exception as e:
        print("CoinDesk RSS Error:", e)

    # 3. Test CoinTelegraph RSS Feed
    print("\nTesting CoinTelegraph RSS feed...")
    try:
        r2 = requests.get("https://cointelegraph.com/rss", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        print("CoinTelegraph RSS Status:", r2.status_code)
        if r2.status_code == 200:
            root2 = ET.fromstring(r2.content)
            items2 = root2.findall(".//item")
            print(f"CoinTelegraph Headlines found: {len(items2)}")
            for item in items2[:3]:
                title = item.find("title").text if item.find("title") is not None else ""
                print(f"  -> {title}")
    except Exception as e:
        print("CoinTelegraph RSS Error:", e)

if __name__ == "__main__":
    test_live_news_feed()

