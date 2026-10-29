"""Offline regression tests for independent news sources (no network or Telegram calls)."""
import io
import os
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from contextlib import redirect_stdout
from unittest.mock import patch

import news


class NewsFallbackTests(unittest.TestCase):
    def test_gdelt_429_uses_cryptopanic_without_leaking_key(self):
        def fake_get_json(url):
            if 'gdeltproject.org' in url:
                raise urllib.error.HTTPError(url, 429, 'Too Many Requests', {}, None)
            return {'results': [{'title': 'Solana upgrade announced',
                                 'url': 'https://example.com/sol', 'domain': 'Example'}]}
        out = io.StringIO()
        with patch.dict(os.environ, {'CRYPTOPANIC_API_KEY': 'SECRET_NEVER_LOG', 'CRYPTOPANIC_PLAN': 'developer'}), \
             patch.object(news, 'get_json', side_effect=fake_get_json), redirect_stdout(out):
            result = news.articles('SOLUSDT')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source'], 'CryptoPanic')
        self.assertIn('HTTP 429', out.getvalue())
        self.assertNotIn('SECRET_NEVER_LOG', out.getvalue())

    def test_gdelt_success_works_even_when_optional_provider_fails(self):
        def fake_get_json(url):
            if 'gdeltproject.org' in url:
                return {'articles': [{'title': 'Ethereum upgrade', 'url': 'https://example.com/eth'}]}
            raise urllib.error.HTTPError(url, 429, 'Too Many Requests', {}, None)
        with patch.dict(os.environ, {'CRYPTOPANIC_API_KEY': 'SECRET_NEVER_LOG', 'CRYPTOPANIC_PLAN': 'developer'}), \
             patch.object(news, 'get_json', side_effect=fake_get_json):
            result = news.articles('ETHUSDT')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source'], 'GDELT')

    def test_all_providers_unavailable_is_not_misreported_as_no_news(self):
        with patch.dict(os.environ, {'CRYPTOPANIC_API_KEY': '', 'CRYPTOPANIC_PLAN': 'developer'}), \
             patch.object(news, 'get_json', side_effect=urllib.error.HTTPError(
                 'https://example.com', 429, 'Too Many Requests', {}, None)), \
             patch.object(news, 'get_xml', side_effect=ValueError('RSS unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'No news provider available'):
                news.articles('BTCUSDT')


    def test_gdelt_429_falls_back_to_public_rss_without_key(self):
        published = format_datetime(datetime.now(timezone.utc), usegmt=True)
        xml = ('<rss><channel><item><title>Ethereum upgrade announced</title>'
               '<link>https://www.coindesk.com/markets/ethereum-upgrade</link>'
               '<pubDate>' + published + '</pubDate></item></channel></rss>')
        def fake_xml(url):
            if 'coindesk.com' in url:
                return ET.fromstring(xml)
            raise ValueError('Other feed unavailable')
        with patch.dict(os.environ, {'CRYPTOPANIC_API_KEY': '', 'CRYPTOPANIC_PLAN': 'developer'}), \
             patch.object(news, 'get_json', side_effect=urllib.error.HTTPError(
                 'https://example.com', 429, 'Too Many Requests', {}, None)), \
             patch.object(news, 'get_xml', side_effect=fake_xml):
            result = news.articles('ETHUSDT')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source'], 'CoinDesk')

    def test_rss_rejects_stale_and_off_domain_articles(self):
        old = format_datetime(datetime.now(timezone.utc) - timedelta(days=2), usegmt=True)
        recent = format_datetime(datetime.now(timezone.utc), usegmt=True)
        xml = ('<rss><channel>'
               '<item><title>Bitcoin old headline</title><link>https://www.coindesk.com/old</link><pubDate>' + old + '</pubDate></item>'
               '<item><title>Bitcoin suspicious headline</title><link>https://not-coindesk.example/news</link><pubDate>' + recent + '</pubDate></item>'
               '</channel></rss>')
        with patch.object(news, 'get_xml', return_value=ET.fromstring(xml)):
            items, healthy = news.rss_fallback()
        self.assertEqual(healthy, 2)
        self.assertEqual(items, [])



if __name__ == '__main__':
    unittest.main()
