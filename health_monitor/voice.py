"""
Voice input pipeline:
  1. record_audio()  — capture mic input until Enter is pressed
  2. transcribe()    — local Whisper model (faster-whisper, base model ~145 MB)
  3. parse_events()  — Claude API turns transcribed text into structured events
"""

import json
import tempfile
import threading
from pathlib import Path
from typing import List, Dict, Optional

# Whisper model cached next to the package so it's not re-downloaded each run
_WHISPER_CACHE = Path(__file__).parent.parent / ".whisper_cache"


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_audio(stop_event: threading.Event, sample_rate: int = 16000) -> Path:
    """
    Stream audio from the default microphone until stop_event is set.
    Returns path to a temporary WAV file (caller must delete it).
    """
    import sounddevice as sd
    import soundfile as sf
    import numpy as np

    chunks: List = []

    def callback(indata, frames, time, status):
        if not stop_event.is_set():
            chunks.append(indata.copy())

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32",
                        callback=callback):
        stop_event.wait()

    audio = np.concatenate(chunks, axis=0) if chunks else np.zeros((sample_rate,), dtype="float32")
    tmp = Path(tempfile.mktemp(suffix=".wav"))
    sf.write(tmp, audio, sample_rate)
    return tmp


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe(audio_path: Path, language: Optional[str] = None) -> str:
    """
    Transcribe a WAV file with faster-whisper (runs locally, no API key needed).
    Downloads the 'base' model (~145 MB) on first use into .whisper_cache/.
    Handles Polish and English well; leave language=None for auto-detect.
    """
    from faster_whisper import WhisperModel

    _WHISPER_CACHE.mkdir(exist_ok=True)
    model = WhisperModel("base", download_root=str(_WHISPER_CACHE), device="cpu",
                         compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), language=language,
                                   vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You parse health diary entries into structured events for a health tracker.

Return a JSON array of event objects. Each object has these fields:
  tag      — one of: food, activity, symptom, mood, stress, sleep, other
  category — subcategory relevant to the tag. Examples:
               food:     regular, junk, simple_carbs, alcohol, allergenic
               activity: gaming, workout, walk, work, social
               symptom:  face_redness, headache, fatigue
               mood:     relaxed, anxious, happy, tired
               stress:   (use a 1-10 number as value instead of category)
               sleep:    quality (use a 1-10 number as value)
  value    — specific item or score (e.g. "avocado", "7", "2h")
  notes    — any extra context, or null

Rules:
- Split compound entries: "avocado and egg" → two food events
- Infer reasonable defaults for Polish or English input
- For scores/ratings mentioned without context, use tag=symptom or stress
- Return ONLY a valid JSON array, no explanation or markdown
- If nothing health-related is found, return []

Examples:
  Input:  "zjadłem awokado i jajko na śniadanie, grałem 2 godziny"
  Output: [{"tag":"food","category":"regular","value":"awokado","notes":"śniadanie"},
           {"tag":"food","category":"regular","value":"jajko","notes":"śniadanie"},
           {"tag":"activity","category":"gaming","value":"2h","notes":null}]

  Input:  "redness is about 7, had a beer and felt stressed at work all day"
  Output: [{"tag":"symptom","category":"face_redness","value":"7","notes":null},
           {"tag":"food","category":"alcohol","value":"beer","notes":null},
           {"tag":"stress","category":"work","value":"high","notes":"all day"}]
"""


def parse_events(text: str) -> List[Dict]:
    """Call Claude to turn free text into a list of structured event dicts."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    if not raw:
        return []

    return json.loads(raw)
