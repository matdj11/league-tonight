import requests
import logging
import os
import base64

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elevenlabs.io/v1"

_voices_cache = None
_voices_cache_time = 0
VOICES_CACHE_TTL = 300  # 5 minutes


def get_available_voices(force_refresh=False):
    global _voices_cache, _voices_cache_time
    import time
    now = time.time()

    if not force_refresh and _voices_cache is not None and (now - _voices_cache_time) < VOICES_CACHE_TTL:
        return _voices_cache

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        logger.warning("ELEVENLABS_API_KEY not set")
        return []
    try:
        response = requests.get(f"{BASE_URL}/voices", headers={"xi-api-key": api_key}, timeout=10)
        response.raise_for_status()
        data = response.json()
        _voices_cache = data.get("voices", [])
        _voices_cache_time = now
        return _voices_cache
    except Exception as e:
        logger.warning(f"Could not fetch ElevenLabs voices: {str(e)}")
        return _voices_cache if _voices_cache is not None else []


def _find_voice_by_name(voices, name_query):
    if not name_query:
        return None
    query = name_query.lower().strip()
    for v in voices:
        if query in v.get("name", "").lower():
            return v["voice_id"]
    return None


def pick_two_voice_ids():
    voices = get_available_voices()
    if not voices:
        return None, None

    preferred_a = os.getenv("ELEVENLABS_VOICE_A")
    preferred_b = os.getenv("ELEVENLABS_VOICE_B")

    voice_a_id = _find_voice_by_name(voices, preferred_a)
    voice_b_id = _find_voice_by_name(voices, preferred_b)

    if not voice_a_id:
        voice_a_id = voices[0]["voice_id"]
    if not voice_b_id:
        fallback = next((v for v in voices if v["voice_id"] != voice_a_id), voices[0])
        voice_b_id = fallback["voice_id"]

    return voice_a_id, voice_b_id


def synthesize_speech(text, voice_id):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key or not voice_id:
        return None
    try:
        url = f"{BASE_URL}/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        audio_bytes = response.content
        return base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"ElevenLabs synthesis failed: {str(e)}")
        return None


def synthesize_script(script, voice_a_id, voice_b_id):
    """Given script [{speaker, line}], synthesize audio for each line,
    alternating between two voices by speaker name. Returns list of
    {speaker, line, audio_base64 (or None if synthesis failed)}."""
    speaker_voice_map = {}
    results = []
    voice_pool = [voice_a_id, voice_b_id]
    next_voice_idx = 0

    for item in script:
        speaker = item.get("speaker")
        line = item.get("line", "")
        if not line:
            continue
        if speaker not in speaker_voice_map:
            speaker_voice_map[speaker] = voice_pool[next_voice_idx % len(voice_pool)]
            next_voice_idx += 1
        voice_id = speaker_voice_map[speaker]
        audio_b64 = synthesize_speech(line, voice_id)
        results.append({
            "speaker": speaker,
            "line": line,
            "audio_base64": audio_b64
        })
    return results
