"""S2S voice pipeline — natural TTS via edge-tts + STT via faster-whisper.

Replaces robotic macOS 'say' with:
- TTS: Microsoft Edge neural voices (natural, free, unlimited)
- STT: faster-whisper (local, fast, accurate)

Usage:
    from plotlot.harness.s2s_voice import speak, listen

    await speak("Hello, this is Earl with ESP & ME LLC.")
    transcript = await listen()  # records mic and transcribes
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile


# Available Edge TTS voices (natural neural voices)
VOICES: dict[str, str] = {
    "male": "en-US-GuyNeural",
    "female": "en-US-AriaNeural",
    "british_male": "en-GB-RyanNeural",
    "british_female": "en-GB-SoniaNeural",
    "australian": "en-AU-NatashaNeural",
}


async def speak(text: str, voice: str = "male", output_path: str | None = None, engine: str = "edge") -> str:
    """Convert text to speech. Supports edge-tts (cloud, natural) and piper (local, fast).

    Args:
        text: Text to speak
        voice: Voice name (male/female/british_male etc for edge, or piper model path)
        output_path: Save to file. If None, auto-generates temp path
        engine: 'edge' (default, natural) or 'piper' (local, fast)

    Returns path to audio file.
    """
    if engine == "piper":
        return await _speak_piper(text, output_path)
    return await _speak_edge(text, voice, output_path)


async def _speak_edge(text: str, voice: str, output_path: str | None) -> str:
    voice_id = VOICES.get(voice, VOICES["male"])
    path = output_path or tempfile.mktemp(suffix=".mp3")
    cmd = ["edge-tts", "--voice", voice_id, "--text", text, "--write-media", path]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await proc.wait()
    if not output_path:
        subprocess.run(["afplay", path], capture_output=True)
    return path


async def _speak_piper(text: str, output_path: str | None) -> str:
    """Use Piper native binary — local, fast, free."""
    model = os.path.expanduser("~/.local/share/piper-tts/en_US-lessac-medium.onnx")
    path = output_path or tempfile.mktemp(suffix=".wav")
    if not os.path.exists(model):
        raise FileNotFoundError(f"Piper model not found at {model}. Download from piper-tts.")
    cmd = ["piper", "--model", model, "--output_file", path]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    await proc.communicate(input=text.encode())
    await proc.wait()
    if not output_path:
        subprocess.run(["afplay", path], capture_output=True)
    return path


async def speak_batch(phrases: list[tuple[str, str]], output_dir: str) -> list[str]:
    """Generate audio for multiple phrases in parallel. Returns file paths."""
    tasks = []
    for i, (text, voice) in enumerate(phrases):
        path = os.path.join(output_dir, f"step{i+1:02d}.mp3")
        tasks.append(speak(text, voice, path))
    paths = await asyncio.gather(*tasks)
    return list(paths)


async def speak_call_flow(lead_name: str, property_address: str, lot_acres: float, offer: float, output_dir: str = "/tmp/plotlot_voice") -> list[str]:
    """Generate a complete outbound call flow with natural voice.

    Steps: intro → questions → first hold → follow-up → second hold → offer → close
    """
    import urllib.request, csv, io
    os.makedirs(output_dir, exist_ok=True)

    phrases = [
        ("intro", f"Hi, this is Earl with ESP and ME LLC. I'm calling about the property at {property_address}. Is this a good time to talk?"),
        ("q1", f"What is the full address or parcel number?"),
        ("q2", f"About how many acres is the lot?"),
        ("q3", f"Has the lot been surveyed? And if so, do you have access to that survey?"),
        ("q4", f"Are city sewer and water taps already in place? Or does it just have access to water and sewer?"),
        ("hold1", f"One moment please. I'm going to check with the underwriters to see if they approved this lot."),
        ("q5", f"If there's no city sewer or water, has the land ever been perc tested? Do you have the results?"),
        ("q6", f"Did a house ever sit on this lot, or is the land virgin?"),
        ("q7", f"Was this a previous dump site at any point?"),
        ("q8", f"Are there any known easements?"),
        ("hold2", f"One more moment. I'm coming back with our offer on the lot."),
        ("offer", f"Our offer for your property is {int(offer)} dollars. If your asking price is significantly lower, we can work with you."),
        ("close", f"We can send the paperwork today if you're ready to move forward. Thank you for your time."),
    ]

    paths = []
    for i, (label, text) in enumerate(phrases):
        path = os.path.join(output_dir, f"step{i+1:02d}_{label}.mp3")
        await speak(text, "male", path)
        paths.append(path)
        print(f"  🎧 {label:8s}: '{text[:70]}...'")

    return paths


async def listen(duration: int = 5, output_path: str | None = None) -> str | None:
    """Record audio from microphone and transcribe using faster-whisper.

    Returns transcribed text or None if STT unavailable.
    """
    try:
        import faster_whisper
        path = output_path or tempfile.mktemp(suffix=".wav")
        # Record audio
        subprocess.run(
            ["sox", "-d", path, "trim", "0", str(duration)],
            capture_output=True, timeout=duration + 2,
        )
        # Transcribe
        model = faster_whisper.WhisperModel("tiny.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(path)
        text = " ".join(s.text for s in segments)
        return text.strip()
    except Exception:
        return None
