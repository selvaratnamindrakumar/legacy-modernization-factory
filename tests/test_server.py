import json
import threading
import unittest
from http.client import HTTPConnection

from modernization_factory.server import Handler, load_plan
from http.server import ThreadingHTTPServer


class ServerTests(unittest.TestCase):
    def test_health_and_plan_endpoints(self):
        Handler.plan = load_plan(None)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", "/health")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["status"], "ok")
            connection.request("GET", "/api/plan")
            response = connection.getresponse()
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(body["application"]["name"], "demo-order-service")
            self.assertEqual(body["application"]["tags"]["environment"], "sandbox")
            connection.request("GET", "/api/data?tags=8888")
            response = connection.getresponse()
            data = json.loads(response.read())
            self.assertEqual(data["count"], 2)
            self.assertEqual({record["source"] for record in data["records"]}, {"S3", "RDS"})
            connection.request("GET", "/api/data?source=rds&tacs=8888")
            response = connection.getresponse()
            data = json.loads(response.read())
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["records"][0]["source"], "RDS")
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
