import unittest

import operations_dashboard_server as dashboard


class PartialWriter:
    def __init__(self, chunk_size: int):
        self.chunk_size = chunk_size
        self.body = bytearray()
        self.calls = 0

    def write(self, payload):
        chunk = bytes(payload[: self.chunk_size])
        self.body.extend(chunk)
        self.calls += 1
        return len(chunk)


class DashboardHttpWriteTests(unittest.TestCase):
    def test_write_all_retries_partial_socket_writes(self):
        writer = PartialWriter(chunk_size=7)
        payload = b'x' * 31

        dashboard.write_all(writer, payload)

        self.assertEqual(bytes(writer.body), payload)
        self.assertGreater(writer.calls, 1)


if __name__ == '__main__':
    unittest.main()
