"""Exercise the installed client against a local metadata API and real SQLite.

No music, real account, external request, credential extraction or terminal UI.
"""
import json
import pathlib
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from importlib import metadata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import requests
from packaging.requirements import Requirement
from qobuz_dl.commands import qobuz_dl_args
from qobuz_dl.db import create_db, handle_download_id
from qobuz_dl.exceptions import AuthenticationError, IneligibleError, InvalidAppIdError
from qobuz_dl.qopy import Client
from qobuz_dl.utils import PartialFormatter, get_url_info, smart_discography_filter


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        seen = self.requests

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                url = urlsplit(self.path)
                params = parse_qs(url.query)
                seen.append((url.path, params))
                status = 200
                if url.path == '/album/get':
                    body = {'id': params['album_id'][0], 'title': 'Fixture album'}
                elif url.path == '/playlist/get':
                    offset = int(params['offset'][0])
                    body = {'tracks_count': 501, 'tracks': {'items': [{'id': offset}]}}
                elif url.path == '/user/login':
                    status = {'invalid': 401, 'bad-app': 400}.get(params['email'][0], 200)
                    body = {'user': {'credential': {'parameters': {}}}}
                else:
                    status, body = 503, {'error': 'fixture unavailable'}
                raw = json.dumps(body).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        # Construct only the metadata transport; constructor authentication and
        # app-secret discovery are deliberately outside this offline test.
        self.client = Client.__new__(Client)
        self.client.session = requests.Session()
        self.client.session.trust_env = False
        self.client.base = 'http://127.0.0.1:%d/' % self.server.server_port
        self.client.id = 'fixture-app'

    def tearDown(self):
        self.client.session.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_album_metadata_uses_real_http_and_encoded_id(self):
        metadata = self.client.get_album_meta('album&other=value')
        self.assertEqual(metadata['id'], 'album&other=value')
        self.assertEqual(metadata['title'], 'Fixture album')
        self.assertEqual(self.requests, [('/album/get', {'album_id': ['album&other=value']})])

    def test_playlist_pagination_fetches_both_pages(self):
        pages = list(self.client.get_plist_meta('playlist-1'))
        self.assertEqual([p['tracks']['items'][0]['id'] for p in pages], [0, 500])
        self.assertEqual([p['offset'] for _, p in self.requests], [['0'], ['500']])
        self.assertTrue(all(p['limit'] == ['500'] for _, p in self.requests))

    def test_http_failure_is_propagated(self):
        with self.assertRaises(requests.HTTPError):
            self.client.api_call('fixture/unavailable')

    def test_invalid_credentials_remain_rejected(self):
        with self.assertRaises(AuthenticationError):
            self.client.api_call('user/login', email='invalid', pwd='fixture')

    def test_invalid_app_remains_rejected(self):
        with self.assertRaises(InvalidAppIdError):
            self.client.api_call('user/login', email='bad-app', pwd='fixture')

    def test_ineligible_account_remains_rejected(self):
        with self.assertRaises(IneligibleError):
            self.client.auth('free-fixture', 'fixture')

    def test_sqlite_ids_survive_reopen_and_remain_parameterized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'downloads.db'
            create_db(str(path))
            item = "x'); DROP TABLE downloads; --"
            handle_download_id(str(path), item, add_id=True)
            create_db(str(path))
            self.assertEqual(handle_download_id(str(path), item), (item,))
            self.assertIsNone(handle_download_id(str(path), 'missing'))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM downloads').fetchone()[0], 1)
            # Windows rejects deletion while any helper's connection is open.
            path.unlink()

    def test_supported_url_forms_preserve_entity_and_id(self):
        for url in ('https://www.qobuz.com/us-en/album/name/123', 'https://open.qobuz.com/album/123', '/us-en/album/-/123'):
            with self.subTest(url=url):
                self.assertEqual(get_url_info(url), ('album', '123'))

    def test_discography_filter_selects_quality_and_excludes_other_artists(self):
        def album(identity, artist, bits, rate):
            return {'id': identity, 'title': 'Fixture', 'artist': {'name': artist}, 'maximum_bit_depth': bits, 'maximum_sampling_rate': rate}
        contents = [{'name': 'Fixture Artist', 'albums': {'items': [album('low', 'Fixture Artist', 16, 44.1), album('best', 'Fixture Artist', 24, 96), album('smaller', 'Fixture Artist', 24, 48), album('other', 'Other Artist', 24, 96)]}}]
        self.assertEqual([a['id'] for a in smart_discography_filter(contents)], ['best'])
        self.assertEqual([a['id'] for a in smart_discography_filter(contents, save_space=True)], ['smaller'])

    def test_cli_parser_and_filename_templates_load_from_installed_package(self):
        args = qobuz_dl_args().parse_args(['dl', 'https://open.qobuz.com/album/123'])
        self.assertEqual(args.command, 'dl')
        self.assertEqual(args.SOURCE, ['https://open.qobuz.com/album/123'])
        self.assertEqual(PartialFormatter().format('{artist} - {missing}', artist='Fixture'), 'Fixture - n/a')

    def test_declared_requirements_match_the_installed_wheel(self):
        declared = pathlib.Path(__file__).resolve().parents[1] / 'requirements.txt'
        expected = {str(Requirement(line.strip())) for line in declared.read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#')}
        actual = {str(Requirement(line)) for line in metadata.requires('qobuz-dl')}
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
