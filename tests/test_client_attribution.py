"""The existing SDK transport carries a stable program attribution."""
import json
import unittest
from unittest import mock

from shuttle import quipu_client as qc


class AttributionTests(unittest.TestCase):
    def test_client_header_preserves_auth_and_query_body(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"rows":[],"count":0,"truncated":false}'
        with mock.patch.object(qc, '_auth_token', return_value='synthetic-token'), \
                mock.patch.object(qc.urllib.request, 'urlopen', return_value=response) as send:
            status, body = qc._request('POST', '/query', {'query': 'fixture'})
        request = send.call_args.args[0]
        self.assertEqual('shuttle', request.get_header('X-quipu-client'))
        self.assertEqual('Bearer synthetic-token', request.get_header('Authorization'))
        self.assertEqual({'query': 'fixture'}, json.loads(request.data))
        self.assertEqual(200, status)
        self.assertIs(body['truncated'], False)
