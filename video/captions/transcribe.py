"""
Transcribe audio from video using OpenAI Whisper.
Outputs word-level timestamps in Remotion Caption[] JSON format.
"""
import json
import sys
from pathlib import Path

import whisper


def transcribe_video(video_path: str, model_name: str = "base.en") -> list[dict]:
    """
    Transcribe video audio and return word-level timestamps.

    Args:
        video_path: Path to the video file
        model_name: Whisper model ('tiny.en', 'base.en', 'small.en', 'medium.en')

    Returns:
        List of Caption objects: [{text, startMs, endMs, timestampMs, confidence}]
    """
    print(f"Loading Whisper model: {model_name}...", flush=True)
    model = whisper.load_model(model_name)

    print(f"Transcribing: {video_path}...", flush=True)
    result = model.transcribe(
        video_path,
        word_timestamps=True,
        language="en",
    )

    captions = []
    for segment in result["segments"]:
        for word in segment.get("words", []):
            captions.append({
                "text": word["word"],
                "startMs": int(word["start"] * 1000),
                "endMs": int(word["end"] * 1000),
                "timestampMs": int(word["start"] * 1000),
                "confidence": round(word.get("probability", 1.0), 3),
            })

    print(f"Found {len(captions)} words", flush=True)
    return captions


def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <video_path> [output_path] [model]")
        sys.exit(1)

    video_path = sys.argv[1]

    # Default output: same name but .json, in the Remotion public folder
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        output_path = str(Path(video_path).with_suffix(".json"))

    model_name = sys.argv[3] if len(sys.argv) >= 4 else "base.en"

    captions = transcribe_video(video_path, model_name)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(captions, f, indent=2)

    print(f"Captions saved to: {output_path}", flush=True)

    # Print first few for verification
    for cap in captions[:10]:
        print(f"  [{cap['startMs']:5d}-{cap['endMs']:5d}ms] {cap['text']}", flush=True)
    if len(captions) > 10:
        print(f"  ... and {len(captions) - 10} more words", flush=True)


if __name__ == "__main__":
    main()
