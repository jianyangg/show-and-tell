"""
Debug script to test the full image generation and WebSocket integration

This script simulates what the debate server does:
1. Generate image
2. Base64 encode it
3. Send via WebSocket message (simulated)

This helps verify the integration code is correct.
"""

import os
import base64
import json
import asyncio
from google import genai
from google.genai import types


async def test_full_integration():
    """Test the complete flow from image generation to WebSocket message."""

    print("=" * 60)
    print("Testing Full Integration Flow")
    print("=" * 60)

    # Step 1: Generate image (same as in debate_server.py)
    topic = "climate change"
    print(f"\n1️⃣  Generating image for topic: '{topic}'...")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set!")
        return

    client = genai.Client(api_key=api_key)

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=topic)],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        system_instruction=[
            types.Part.from_text(
                text="""Generate a scene according to the user's prompt in South Park's cartoonish style. The user's prompt is going to be a debate topic, so identify the best prompt to achieve it. Exclude any commentary or description, just the image will do."""
            ),
        ],
    )

    def _generate_image():
        """Synchronous wrapper for Gemini API call."""
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash-image",
            contents=contents,
            config=generate_content_config,
        ):
            if (
                chunk.candidates is not None
                and chunk.candidates[0].content is not None
                and chunk.candidates[0].content.parts is not None
            ):
                if (
                    chunk.candidates[0].content.parts[0].inline_data
                    and chunk.candidates[0].content.parts[0].inline_data.data
                ):
                    inline_data = chunk.candidates[0].content.parts[0].inline_data
                    image_bytes = inline_data.data
                    mime_type = inline_data.mime_type
                    return image_bytes, mime_type
        return None, None

    # Generate image
    image_bytes, mime_type = await asyncio.to_thread(_generate_image)

    if not image_bytes:
        print("❌ Image generation failed!")
        return

    print(f"✅ Image generated: {len(image_bytes)} bytes, type: {mime_type}")

    # Step 2: Base64 encode (same as in debate_server.py)
    print("\n2️⃣  Base64 encoding image...")
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    print(f"✅ Encoded to base64: {len(image_base64)} characters")

    # Step 3: Create WebSocket message (same as in debate_server.py)
    print("\n3️⃣  Creating WebSocket message...")
    image_format = mime_type.split('/')[-1] if mime_type else 'png'

    message = {
        'type': 'background_image',
        'data': image_base64,
        'format': image_format,
        'topic': topic
    }

    message_json = json.dumps(message)
    print(f"✅ Message created: {len(message_json)} bytes JSON")

    # Step 4: Verify message can be parsed
    print("\n4️⃣  Verifying message can be parsed...")
    try:
        parsed = json.loads(message_json)
        print(f"✅ Message type: {parsed['type']}")
        print(f"✅ Image format: {parsed['format']}")
        print(f"✅ Topic: {parsed['topic']}")
        print(f"✅ Base64 data length: {len(parsed['data'])}")

        # Verify we can decode the base64 back
        decoded_bytes = base64.b64decode(parsed['data'])
        print(f"✅ Decoded back to {len(decoded_bytes)} bytes")

        if len(decoded_bytes) == len(image_bytes):
            print("✅ Decoded size matches original!")
        else:
            print(f"⚠️  Size mismatch: original={len(image_bytes)}, decoded={len(decoded_bytes)}")

    except Exception as e:
        print(f"❌ Error parsing/decoding: {e}")
        return

    # Step 5: Save a test HTML file to verify frontend can decode
    print("\n5️⃣  Creating test HTML file to verify frontend decoding...")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Image Decode Test</title>
</head>
<body>
    <h1>Image Decode Test</h1>
    <p>If you see an image below, the base64 encoding/decoding works correctly:</p>

    <img id="testImage" style="max-width: 100%; border: 2px solid green;" />

    <script>
        // This simulates what main.js does
        const base64Data = `{image_base64[:100]}...`; // (truncated for display)
        const format = '{image_format}';

        console.log('Testing image decoding...');
        console.log('Base64 length:', {len(image_base64)});
        console.log('Format:', format);

        // Full data for actual test
        const fullBase64 = {json.dumps(image_base64)};

        try {{
            // Decode base64 to binary
            const binaryString = atob(fullBase64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {{
                bytes[i] = binaryString.charCodeAt(i);
            }}

            // Create blob and display
            const blob = new Blob([bytes], {{ type: `image/${{format}}` }});
            const url = URL.createObjectURL(blob);

            document.getElementById('testImage').src = url;
            console.log('✅ Image loaded successfully!');
        }} catch (error) {{
            console.error('❌ Error loading image:', error);
        }}
    </script>
</body>
</html>"""

    test_html_path = "/Users/jianyang/Documents/Documents - Jian Yang's MacBook Pro/cursor-hackathon/chat/test_image_decode.html"
    with open(test_html_path, 'w') as f:
        f.write(html_content)

    print(f"✅ Test HTML created: {test_html_path}")
    print(f"   Open this file in a browser to verify frontend decoding works!")

    print("\n" + "=" * 60)
    print("✅ ALL CHECKS PASSED!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Open test_image_decode.html in a browser")
    print("2. Check browser console for any errors")
    print("3. If image displays, the integration code is correct")
    print("4. If not, there may be an issue with the frontend JavaScript")


if __name__ == "__main__":
    asyncio.run(test_full_integration())
