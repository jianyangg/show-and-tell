"""
Simple test to verify the background image is generated and sent correctly.

This creates a minimal WebSocket server that:
1. Receives topic from client
2. Generates background image
3. Sends it back

Run this instead of debate_server.py to isolate the background generation feature.
"""

import asyncio
import json
import base64
import os
import logging
from google import genai
from google.genai import types
import websockets

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Gemini client
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)


async def generate_background(topic: str):
    """Generate background image."""
    logger.info(f"🎨 Generating background for: {topic}")

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=topic)],
        ),
    ]

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        system_instruction=[
            types.Part.from_text(
                text="""Generate a scene according to the user's prompt in South Park's cartoonish style. The user's prompt is going to be a debate topic, so identify the best prompt to achieve it. Exclude any commentary or description, just the image will do."""
            ),
        ],
    )

    def _gen():
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash-image",
            contents=contents,
            config=config,
        ):
            if (
                chunk.candidates
                and chunk.candidates[0].content
                and chunk.candidates[0].content.parts
                and chunk.candidates[0].content.parts[0].inline_data
                and chunk.candidates[0].content.parts[0].inline_data.data
            ):
                inline_data = chunk.candidates[0].content.parts[0].inline_data
                return inline_data.data, inline_data.mime_type
        return None, None

    return await asyncio.to_thread(_gen)


async def handle_client(websocket):
    """Handle WebSocket client connection."""
    logger.info("Client connected")

    try:
        # Wait for start_debate message
        message = await websocket.recv()
        data = json.loads(message)

        if data.get('type') == 'start_debate':
            topic = data.get('topic', 'test topic')
            logger.info(f"📝 Received topic: {topic}")

            # Send acknowledgment
            await websocket.send(json.dumps({
                'type': 'init',
                'topic': topic,
                'status': 'Starting background generation...'
            }))

            # Generate background image
            logger.info("🎨 Starting background generation...")
            image_bytes, mime_type = await generate_background(topic)

            if image_bytes:
                logger.info(f"✅ Image generated: {len(image_bytes)} bytes")

                # Encode and send
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                image_format = mime_type.split('/')[-1] if mime_type else 'png'

                message = json.dumps({
                    'type': 'background_image',
                    'data': image_base64,
                    'format': image_format,
                    'topic': topic
                })

                logger.info(f"📤 Sending image to client ({len(message)} bytes)")
                await websocket.send(message)
                logger.info("✅ Image sent!")

            else:
                logger.error("❌ Image generation failed")

        # Keep connection open
        await websocket.wait_closed()

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


async def main():
    """Start WebSocket server."""
    logger.info("Starting test server on ws://localhost:8765")

    # Increase max_size to handle large image messages
    async with websockets.serve(
        handle_client,
        "localhost",
        8765,
        max_size=10 * 1024 * 1024  # 10MB
    ):
        logger.info("✅ Server ready! Connect from browser...")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
