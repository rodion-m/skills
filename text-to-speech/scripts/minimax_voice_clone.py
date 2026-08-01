#!/usr/bin/env python3
"""Create and activate a MiniMax cloned voice with explicit cost gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_PROFILE = Path("~/.config/duanku/minimax-voice.json").expanduser()
DEFAULT_SECRETS = Path("~/.config/duanku/secrets.env").expanduser()
CLONE_FEE_USD = Decimal("1.50")
HD_RATE_PER_MILLION_CHARS = Decimal("100")
SUPPORTED_SUFFIXES = {".mp3", ".m4a", ".wav"}


def load_local_secrets() -> None:
    path = Path(os.environ.get("DUANKU_SECRETS_FILE", DEFAULT_SECRETS)).expanduser()
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def ffprobe_audio(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels:format=duration,size",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise ValueError(f"ffprobe failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def inspect_sample(path: Path) -> dict:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"sample not found: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("sample format must be mp3, m4a, or wav")
    info = ffprobe_audio(path)
    streams = info.get("streams") or []
    if not streams:
        raise ValueError("sample has no audio stream")
    duration = Decimal(str((info.get("format") or {}).get("duration", "0")))
    size = int((info.get("format") or {}).get("size", path.stat().st_size))
    if duration < Decimal("10") or duration > Decimal("300"):
        raise ValueError(f"sample duration must be 10-300 seconds, got {duration}")
    if size > 20 * 1024 * 1024:
        raise ValueError(f"sample must be <=20 MiB, got {size} bytes")
    stream = streams[0]
    return {
        "ok": True,
        "path": str(path),
        "duration_seconds": str(duration),
        "size_bytes": size,
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": int(stream.get("channels", 0)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_voice_id(voice_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{6,254}[A-Za-z0-9]", voice_id):
        raise ValueError(
            "voice_id must be 8-256 chars, start with a letter, end with a letter/digit, "
            "and contain only letters, digits, '-' or '_'"
        )
    return voice_id


def build_quote(voice_id: str, text: str, model: str = "speech-2.8-hd") -> dict:
    text_cost = (Decimal(len(text)) * HD_RATE_PER_MILLION_CHARS / Decimal("1000000")).quantize(
        Decimal("0.0001")
    )
    total = CLONE_FEE_USD + text_cost
    body = {
        "schema_version": 1,
        "provider": "minimax",
        "voice_id": validate_voice_id(voice_id),
        "model": model,
        "clone_activation_fee_usd": str(CLONE_FEE_USD),
        "preview_characters": len(text),
        "tts_rate_usd_per_million_characters": str(HD_RATE_PER_MILLION_CHARS),
        "preview_tts_estimate_usd": str(text_cost),
        "estimated_total_usd": str(total.quantize(Decimal("0.0001"))),
        "pricing_source": "https://platform.minimax.io/docs/guides/pricing-paygo",
        "pricing_verified_on": "2026-08-01",
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    body["quote_id"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return body


def api_key() -> str:
    load_local_secrets()
    value = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not value:
        raise ValueError("MINIMAX_API_KEY is missing")
    return value


def api_host() -> str:
    configured = os.environ.get("MINIMAX_API_HOST", "").strip().rstrip("/")
    if configured:
        return configured
    config_path = Path(__file__).parent.parent / "config" / "tts_config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        endpoint = str(config.get("minimax_tts", {}).get("endpoint", ""))
        parts = urlsplit(endpoint)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    except (OSError, json.JSONDecodeError):
        pass
    return "https://api.minimax.io"


def check_response(response, action: str) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{action} returned non-JSON HTTP {response.status_code}") from exc
    base = data.get("base_resp") or {}
    if response.status_code >= 400 or base.get("status_code") not in (None, 0):
        raise RuntimeError(
            f"{action} failed: HTTP {response.status_code}, "
            f"{base.get('status_code')} {base.get('status_msg') or data.get('message') or ''}"
        )
    return data


def upload_clone_sample(path: Path, token: str, host: str | None = None) -> int:
    import requests

    with path.open("rb") as handle:
        response = requests.post(
            f"{host or api_host()}/v1/files/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"purpose": "voice_clone"},
            files={"file": (path.name, handle)},
            timeout=180,
        )
    data = check_response(response, "sample upload")
    file_id = (data.get("file") or {}).get("file_id")
    if not file_id:
        raise RuntimeError("sample upload returned no file_id")
    return int(file_id)


def create_voice(file_id: int, voice_id: str, token: str, host: str | None = None) -> None:
    import requests

    response = requests.post(
        f"{host or api_host()}/v1/voice_clone",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "file_id": file_id,
            "voice_id": voice_id,
            "need_noise_reduction": True,
            "need_volume_normalization": True,
            "aigc_watermark": False,
        },
        timeout=180,
    )
    check_response(response, "voice clone")


def write_profile(path: Path, payload: dict) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def load_profile(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"local clone profile not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def activate_voice(args, profile: dict) -> Path:
    load_local_secrets()
    if not os.environ.get("MINIMAX_API_KEY", "").strip():
        raise ValueError("MINIMAX_API_KEY is missing")
    quote = build_quote(profile["voice_id"], args.text, args.model)
    if args.confirm_quote_id != quote["quote_id"]:
        raise ValueError("confirmation quote_id does not match the current activation quote")
    try:
        confirmed = Decimal(args.confirm_amount_usd)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("--confirm-amount-usd must be a decimal amount") from exc
    if confirmed != Decimal(quote["estimated_total_usd"]):
        raise ValueError(
            f"confirmed amount {confirmed} does not match {quote['estimated_total_usd']}"
        )
    output = args.output.expanduser().resolve()
    tts_script = Path(__file__).with_name("text_to_speech.py")
    env = os.environ.copy()
    env["MINIMAX_VOICE_ID"] = profile["voice_id"]
    proc = subprocess.run(
        [
            sys.executable, str(tts_script), args.text, "--engine", "minimax",
            "--delivery-profile", args.delivery_profile, "--output", str(output),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if proc.returncode != 0 or not output.exists():
        raise RuntimeError(f"activation TTS failed: {(proc.stdout + proc.stderr)[-1500:]}")
    profile.update({
        "active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "activation_quote": quote,
        "delivery_profile": args.delivery_profile,
    })
    write_profile(args.profile, profile)
    return output


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MiniMax voice clone with rights and cost gates")
    sub = result.add_subparsers(dest="action", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--sample", type=Path, required=True)

    quote = sub.add_parser("quote")
    quote.add_argument("--voice-id", required=True)
    quote.add_argument("--text", required=True)
    quote.add_argument("--model", default="speech-2.8-hd")

    clone = sub.add_parser("clone")
    clone.add_argument("--sample", type=Path, required=True)
    clone.add_argument("--voice-id", required=True)
    clone.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    clone.add_argument("--rights-confirmed", action="store_true")

    activate = sub.add_parser("activate")
    activate.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    activate.add_argument("--text", required=True)
    activate.add_argument("--output", type=Path, required=True)
    activate.add_argument("--model", default="speech-2.8-hd")
    activate.add_argument("--delivery-profile", default="commercial_narration")
    activate.add_argument("--confirm-quote-id")
    activate.add_argument("--confirm-amount-usd")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.action == "inspect":
            print(json.dumps(inspect_sample(args.sample), ensure_ascii=False, indent=2))
            return 0
        if args.action == "quote":
            print(json.dumps(build_quote(args.voice_id, args.text, args.model), ensure_ascii=False, indent=2))
            return 0
        if args.action == "clone":
            if not args.rights_confirmed:
                raise ValueError("--rights-confirmed is required before uploading biometric voice audio")
            sample = inspect_sample(args.sample)
            voice_id = validate_voice_id(args.voice_id)
            token = api_key()
            host = api_host()
            file_id = upload_clone_sample(Path(sample["path"]), token, host)
            create_voice(file_id, voice_id, token, host)
            profile = {
                "schema_version": 1,
                "provider": "minimax",
                "voice_id": voice_id,
                "active": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_sample": sample,
                "remote_file_id": file_id,
                "api_host": host,
                "note": "Clone created but not activated. First T2A use incurs the clone fee.",
            }
            write_profile(args.profile, profile)
            print(json.dumps({"ok": True, "profile": str(args.profile), "voice": profile}, ensure_ascii=False, indent=2))
            return 0
        profile = load_profile(args.profile.expanduser())
        output = activate_voice(args, profile)
        print(json.dumps({"ok": True, "output": str(output), "voice_id": profile["voice_id"]}, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
