import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "minimax_voice_clone.py"
SPEC = importlib.util.spec_from_file_location("minimax_voice_clone", SCRIPT)
clone = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clone)


class MiniMaxVoiceCloneTests(unittest.TestCase):
    def test_activation_loads_local_secret_before_launch(self):
        args = mock.Mock(
            text="试听", model="speech-2.8-hd", confirm_quote_id="bad",
            confirm_amount_usd="0", output=Path("preview.mp3"),
            delivery_profile="commercial_narration",
        )
        with (
            mock.patch.object(clone, "load_local_secrets") as load,
            mock.patch.dict(clone.os.environ, {"MINIMAX_API_KEY": "fixture"}, clear=True),
            self.assertRaisesRegex(ValueError, "quote_id"),
        ):
            clone.activate_voice(args, {"voice_id": "DuankuClone001"})
        load.assert_called_once()

    def test_api_host_inherits_tts_endpoint_region(self):
        self.assertEqual(clone.api_host(), "https://api.minimaxi.com")

    def test_quote_contains_clone_fee_and_character_estimate(self):
        quote = clone.build_quote("DuankuClone001", "这是试听。")
        self.assertEqual(quote["clone_activation_fee_usd"], "1.50")
        self.assertEqual(quote["preview_characters"], 5)
        self.assertEqual(Decimal(quote["estimated_total_usd"]), Decimal("1.5005"))
        self.assertEqual(len(quote["quote_id"]), 64)

    def test_voice_id_contract(self):
        self.assertEqual(clone.validate_voice_id("DuankuClone001"), "DuankuClone001")
        for invalid in ("short", "1startsWrong", "ends_", "bad space"):
            with self.assertRaises(ValueError):
                clone.validate_voice_id(invalid)

    def test_sample_gate_accepts_valid_three_minute_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.wav"
            sample.write_bytes(b"wav")
            probe = {
                "streams": [{"codec_name": "pcm_s16le", "sample_rate": "32000", "channels": 1}],
                "format": {"duration": "180", "size": "11520078"},
            }
            with mock.patch.object(clone, "ffprobe_audio", return_value=probe):
                result = clone.inspect_sample(sample)
        self.assertTrue(result["ok"])
        self.assertEqual(result["duration_seconds"], "180")

    def test_profile_is_private_and_inactive_until_paid_tts(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "voice.json"
            clone.write_profile(profile, {
                "provider": "minimax", "voice_id": "DuankuClone001", "active": False
            })
            loaded = json.loads(profile.read_text(encoding="utf-8"))
            self.assertFalse(loaded["active"])
            self.assertEqual(profile.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
