import asyncio
import json
import unittest

from main import app


class DocumentUploadEndpointTests(unittest.TestCase):
    def test_csv_upload_returns_preview_without_persisting_file(self):
        boundary = "RetrofitProofTestBoundary"
        filename = "io.csv"
        content = b"Tag,Signal,Address\nLS1,Clamp extended,I0.0\n"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        messages = []
        body_sent = False

        async def receive():
            nonlocal body_sent
            if body_sent:
                return {"type": "http.disconnect"}
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/documents/extract",
            "raw_path": b"/documents/extract",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
            ],
            "client": ("testclient", 1234),
            "server": ("testserver", 80),
        }

        asyncio.run(app(scope, receive, send))
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        response = json.loads(response_body)

        self.assertEqual(status, 200)
        self.assertFalse(response["stored"])
        self.assertEqual(response["documents"][0]["filename"], filename)
        self.assertEqual(response["documents"][0]["status"], "text_extracted")
        self.assertIn("LS1", response["documents"][0]["extracted_text"])


if __name__ == "__main__":
    unittest.main()
