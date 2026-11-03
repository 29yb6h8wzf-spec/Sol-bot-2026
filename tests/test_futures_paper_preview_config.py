"""Regression guard: Cloudflare preview cannot reuse production state or run scans."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PreviewConfigTests(unittest.TestCase):
    def test_preview_has_explicit_isolated_config(self):
        config = json.loads((ROOT / 'wrangler.jsonc').read_text(encoding='utf-8'))
        self.assertIn('previews', config)
        self.assertEqual(config['previews']['kv_namespaces'], [])
        self.assertEqual(config['previews']['vars']['SIGNALPILOT_PREVIEW_NO_TRADING'], '1')
        self.assertNotIn('triggers', config['previews'])
        self.assertNotIn('routes', config['previews'])
        self.assertNotIn('secrets', config['previews'])
        self.assertNotIn('BINANCE_API_KEY', str(config['previews']))
        self.assertNotIn('BINANCE_API_SECRET', str(config['previews']))
        prod_ids = {binding['id'] for binding in config['kv_namespaces']}
        preview_ids = {binding['id'] for binding in config['previews']['kv_namespaces']}
        self.assertFalse(prod_ids & preview_ids)

    def test_worker_scheduled_handler_exits_in_preview(self):
        source = (ROOT / 'cloudflare' / 'worker.js').read_text(encoding='utf-8')
        handler = source.split('async scheduled(event,env,ctx){', 1)[1]
        guard = "if(env.SIGNALPILOT_PREVIEW_NO_TRADING==='1')"
        self.assertTrue(handler.startswith(guard))
        self.assertIn("return;", handler[:180])


if __name__ == '__main__':
    unittest.main()
