"""
Test script for Gemini 2.5 Flash Image generation

This script tests the image generation functionality in isolation to verify:
1. API key is configured correctly
2. Gemini API is accessible
3. Image generation works with the system prompt
4. Image data is returned correctly

Usage:
    export GEMINI_API_KEY="your-api-key"
    python nanobanana_test.py
"""

import os
import mimetypes
from google import genai
from google.genai import types


def save_binary_file(file_name, data):
    """Save binary data to a file."""
    with open(file_name, "wb") as f:
        f.write(data)
    print(f"✅ File saved to: {file_name}")


def test_image_generation(topic: str):
    """
    Test image generation with Gemini 2.5 Flash Image model.

    Args:
        topic: The debate topic to visualize
    """
    print(f"🎨 Testing image generation for topic: '{topic}'")
    print("=" * 60)

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY environment variable not set!")
        return

    print(f"✅ API key found (length: {len(api_key)})")

    # Initialize client
    client = genai.Client(api_key=api_key)
    print("✅ Gemini client initialized")

    # Define the content and configuration
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=topic)],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        response_modalities=[
            "IMAGE",
        ],
        system_instruction=[
            types.Part.from_text(
                text="""Generate a scene according to the user's prompt in South Park's cartoonish style. The user's prompt is going to be a debate topic, so identify the best prompt to achieve it. Exclude any commentary or description, just the image will do."""
            ),
        ],
    )

    print(f"📤 Sending request to Gemini API (model: gemini-2.5-flash-image)...")

    try:
        # Stream response and look for image data
        chunk_count = 0
        image_found = False

        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash-image",
            contents=contents,
            config=generate_content_config,
        ):
            chunk_count += 1
            print(f"📦 Received chunk {chunk_count}")

            # Check chunk structure
            if chunk.candidates is None:
                print(f"   ⚠️  Chunk {chunk_count}: candidates is None")
                continue

            if chunk.candidates[0].content is None:
                print(f"   ⚠️  Chunk {chunk_count}: content is None")
                continue

            if chunk.candidates[0].content.parts is None:
                print(f"   ⚠️  Chunk {chunk_count}: parts is None")
                continue

            # Check for inline data (image)
            part = chunk.candidates[0].content.parts[0]

            if hasattr(part, 'inline_data') and part.inline_data:
                if part.inline_data.data:
                    print(f"   ✅ Found image data in chunk {chunk_count}!")

                    image_data = part.inline_data.data
                    mime_type = part.inline_data.mime_type

                    print(f"   📊 Image size: {len(image_data)} bytes")
                    print(f"   📊 MIME type: {mime_type}")

                    # Determine file extension
                    file_extension = mimetypes.guess_extension(mime_type) or '.png'

                    # Save the image
                    output_filename = f"test_output_{topic.replace(' ', '_')[:20]}{file_extension}"
                    save_binary_file(output_filename, image_data)

                    image_found = True
                    break

            # Check for text (shouldn't happen with IMAGE-only modality, but good to debug)
            if hasattr(chunk, 'text') and chunk.text:
                print(f"   ⚠️  Chunk {chunk_count} contains text: {chunk.text[:100]}")

        print("=" * 60)

        if image_found:
            print("✅ SUCCESS! Image generated and saved.")
            print(f"📁 Check the file: {output_filename}")
        else:
            print("❌ FAILURE: No image data found in response")
            print(f"   Total chunks received: {chunk_count}")

    except Exception as e:
        print(f"❌ ERROR during image generation: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test with a simple debate topic
    test_topic = "climate change"

    print("=" * 60)
    print("Gemini 2.5 Flash Image - Test Script")
    print("=" * 60)
    print()

    test_image_generation(test_topic)

    print()
    print("=" * 60)
    print("Test complete!")
    print("=" * 60)
