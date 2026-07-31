from __future__ import annotations

import base64
import importlib.util
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "generate_image.py"
SPEC = importlib.util.spec_from_file_location("generate_image", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 10), "gray").save(buffer, format="PNG")
    return buffer.getvalue()


class GeminiReferenceImageTests(unittest.TestCase):
    def test_text_to_image_keeps_single_text_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output.png"
            config = root / "config.json"
            config.write_text(json.dumps({
                "default_api": "gemini",
                "gemini": {
                    "api_key": "test-key",
                    "model": "gemini-test-image",
                    "api_url": "https://example.test/generateContent",
                }
            }), encoding="utf-8")
            response = mock.Mock()
            response.json.return_value = {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(png_bytes()).decode("ascii"),
                            }
                        }]
                    }
                }]
            }
            generator = module.ImageGenerator(config_path=config)
            with mock.patch.object(module.requests, "post", return_value=response) as post:
                generator.generate("new image", output_path=str(output))
            parts = post.call_args.kwargs["json"]["contents"][0]["parts"]
            self.assertEqual(len(parts), 1)
            self.assertIn("new image", parts[0]["text"])

    def test_reference_image_is_sent_inline_and_response_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.png"
            output = root / "output.png"
            config = root / "config.json"
            reference.write_bytes(png_bytes())
            config.write_text(json.dumps({
                "default_api": "gemini",
                "gemini": {
                    "api_key": "test-key",
                    "model": "gemini-test-image",
                    "api_url": "https://example.test/generateContent",
                    "timeout": 10
                }
            }), encoding="utf-8")
            response = mock.Mock()
            response.json.return_value = {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(png_bytes()).decode("ascii"),
                            }
                        }]
                    }
                }]
            }
            generator = module.ImageGenerator(config_path=config)
            with mock.patch.object(module.requests, "post", return_value=response) as post:
                result = generator.generate(
                    "preserve identity",
                    output_path=str(output),
                    size="1024x1280",
                    reference_images=[str(reference)],
                )
            self.assertEqual(Path(result), output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (8, 10))
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["generationConfig"]["imageConfig"]["aspectRatio"], "4:5")
            self.assertEqual(
                payload["contents"][0]["parts"][1]["inlineData"]["mimeType"],
                "image/png",
            )

    def test_missing_reference_is_rejected_before_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text(json.dumps({
                "default_api": "gemini",
                "gemini": {"api_key": "test-key", "model": "gemini-test-image"}
            }), encoding="utf-8")
            generator = module.ImageGenerator(config_path=config)
            with self.assertRaises(FileNotFoundError):
                generator.generate("edit", reference_images=[str(Path(tmp) / "missing.png")])


if __name__ == "__main__":
    unittest.main()
