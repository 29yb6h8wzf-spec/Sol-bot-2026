"""Offline regression tests for independent news sources (no network or Telegram calls)."""
import io
import os
import unittest
import urllib.error
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
                 'https://example.com', 429, 'Too Many Requests', {}, None)):
            with self.assertRaisesRegex(RuntimeError, 'No news provider available'):
                news.articles('BTCUSDT')


if __name__ == '__main__':
    unittest.main()
