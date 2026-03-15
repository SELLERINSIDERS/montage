"""
Transcribe video using OpenAI Whisper API.
Outputs word-level timestamps in Remotion Caption[] JSON format.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def transcribe_video(video_path: str) -> list[dict]:
    """
    Transcribe video using OpenAI Whisper API with word-level timestamps.
    If file exceeds 25MB, extracts audio first via ffmpeg.

    Returns:
        List of Caption objects: [{text, startMs, endMs, timestampMs, confidence}]
    """
    import subprocess
    import tempfile

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Whisper API has 25MB limit — extract audio if file is too large
    file_size = os.path.getsize(video_path)
    actual_path = video_path
    tmp_audio = None

    if file_size > 25 * 1024 * 1024:
        print(f"File is {file_size / 1024 / 1024:.1f}MB (>25MB), extracting audio...", flush=True)
        tmp_audio = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_audio.close()
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", tmp_audio.name, "-y"],
            capture_output=True,
        )
        actual_path = tmp_audio.name
        print(f"Audio extracted: {os.path.getsize(actual_path) / 1024:.0f}KB", flush=True)

    print(f"Transcribing via OpenAI API: {actual_path}...", flush=True)

    with open(actual_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
            language="en",
        )

    captions = []
    for word in result.words:
        captions.append({
            "text": " " + word.word if not word.word.startswith(" ") else word.word,
            "startMs": int(word.start * 1000),
            "endMs": int(word.end * 1000),
            "timestampMs": int(word.start * 1000),
            "confidence": 1.0,
        })

    # Fix first word — no leading space
    if captions:
        captions[0]["text"] = captions[0]["text"].lstrip()

    # Clean up temp audio file
    if tmp_audio and os.path.exists(tmp_audio.name):
        os.unlink(tmp_audio.name)

    print(f"Found {len(captions)} words", flush=True)
    return captions


def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe_api.py <video_path> [output_path]")
        sys.exit(1)

    video_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) >= 3 else str(Path(video_path).with_suffix(".json"))

    captions = transcribe_video(video_path)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(captions, f, indent=2)

    print(f"Captions saved to: {output_path}", flush=True)

    # Print for verification
    for cap in captions[:15]:
        print(f"  [{cap['startMs']:5d}-{cap['endMs']:5d}ms] {cap['text']}", flush=True)
    if len(captions) > 15:
        print(f"  ... and {len(captions) - 15} more words", flush=True)


if __name__ == "__main__":
    main()
