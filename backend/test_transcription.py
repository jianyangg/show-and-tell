#!/usr/bin/env python3
"""
Test script to transcribe an existing recording using the new ElevenLabs SDK integration.

Usage:
    python test_transcription.py [recording_id]

If no recording_id is provided, uses the most recent recording.
"""

import asyncio
import sys
from pathlib import Path

# Add backend app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.storage import RecordingStore
from app.transcription import get_transcription_service


async def test_transcription(recording_id: str = None):
    """Test transcription on a specific recording."""

    # Initialize storage
    store = RecordingStore()

    # Get recording
    if recording_id:
        print(f"Loading recording: {recording_id}")
        try:
            recording = await store.get(recording_id)
        except KeyError:
            print(f"❌ Recording {recording_id} not found")
            return
    else:
        print("Loading most recent recording...")
        recordings = await store.list()
        if not recordings:
            print("❌ No recordings found")
            return
        recording = recordings[0]
        print(f"Using recording: {recording.recording_id}")

    # Check if recording has audio
    if not recording.bundle or not recording.bundle.audio_wav_base64:
        print(f"❌ Recording has no audio data")
        return

    audio_size = len(recording.bundle.audio_wav_base64)
    print(f"✓ Found audio: {audio_size:,} characters ({audio_size * 0.75 / 1024:.1f} KB)")

    # Check if already transcribed
    if recording.bundle.transcript and recording.bundle.transcript.strip():
        print(f"⚠️  Recording already has transcript:")
        print(f"   {recording.bundle.transcript[:200]}...")
        print()
        response = input("Transcribe again anyway? (y/N): ")
        if response.lower() != 'y':
            print("Skipping transcription")
            return
        print()

    # Get transcription service
    service = get_transcription_service()

    if not service.enabled:
        print("❌ Transcription service is disabled")
        print("   Make sure ELEVENLABS_API_KEY is set in your environment")
        return

    print(f"✓ Transcription service enabled")
    print(f"  Language: {service.client}")
    print()

    # Transcribe
    print("🎤 Starting transcription...")
    print("   (This may take 10-30 seconds depending on audio length)")
    print()

    result = await service.transcribe(recording.bundle.audio_wav_base64)

    if not result:
        print("❌ Transcription failed (check logs for details)")
        return

    # Display results
    print("=" * 80)
    print("✅ TRANSCRIPTION SUCCESSFUL")
    print("=" * 80)
    print()

    print(f"Language detected: {result.language_code}")
    print(f"Total words: {len(result.words)}")
    print(f"Time chunks: {len(result.chunks)}")
    print()

    print("Full transcript text:")
    print("-" * 80)
    print(result.full_text)
    print("-" * 80)
    print()

    print("Time-windowed chunks (as sent to AI):")
    print("-" * 80)
    formatted = service.format_for_prompt(result)
    print(formatted)
    print("-" * 80)
    print()

    # Optionally save transcript to recording
    response = input("Save transcript to recording? (Y/n): ")
    if response.lower() != 'n':
        recording.bundle.transcript = formatted
        await store.complete(recording.recording_id, recording.bundle)
        print(f"✓ Transcript saved to recording {recording.recording_id}")
    else:
        print("Transcript not saved (test only)")

    print()
    print("=" * 80)
    print("Test complete!")
    print("=" * 80)


if __name__ == "__main__":
    # Get recording ID from command line if provided
    recording_id = sys.argv[1] if len(sys.argv) > 1 else None

    # Run test
    asyncio.run(test_transcription(recording_id))
