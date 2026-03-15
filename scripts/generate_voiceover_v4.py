"""Generate VSL voiceover using ElevenLabs eleven_v3.

Example script — replace the script text and voice settings for your project.
"""
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from elevenlabs import ElevenLabs

client = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

# Replace with your VSL script text (use audio tags like [calm], [pause], etc.)
script = """[calm] Your VSL script goes here. Replace this placeholder with
the narrated script from your project's copy/script_narrated.md file.

Use ElevenLabs audio tags like [pause], [deliberate], [warm] to control pacing and tone."""

# Output path — adjust for your project
OUTPUT_PATH = str(Path(__file__).resolve().parent.parent / "video/output/elevenlabs/vsl_voiceover.mp3")

# Voice settings — customize for your project
VOICE_ID = 'FGY2WhTYpPnrIDTdsKH5'  # Laura — change to your preferred voice
VOICE_NAME = 'Laura'

print("Generating voiceover...")
print(f"  Voice: {VOICE_NAME} ({VOICE_ID})")
print(f"  Model: eleven_v3")
print(f"  Speed: 1.3 | Stability: 0.65 | Similarity: 0.7 | Style: 0.2")
print(f"  Format: mp3_44100_128")
print(f"  Script length: {len(script)} chars")
print()

audio = client.text_to_speech.convert(
    voice_id=VOICE_ID,
    model_id='eleven_v3',
    text=script,
    voice_settings={
        'stability': 0.65,
        'similarity_boost': 0.7,
        'style': 0.2,
        'speed': 1.3
    },
    output_format='mp3_44100_128'
)

with open(OUTPUT_PATH, 'wb') as f:
    for chunk in audio:
        f.write(chunk)

file_size = os.path.getsize(OUTPUT_PATH)
print(f"Voiceover saved: {OUTPUT_PATH}")
print(f"File size: {file_size / 1024:.1f} KB ({file_size / (1024*1024):.2f} MB)")
print("Done!")
