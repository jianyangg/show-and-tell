// Wait for PIXI to be fully loaded before initializing
// Both Trump and Obama will be 2D sprites with gesture cycling
window.addEventListener('load', async function() {
    // Verify that PIXI.js is loaded
    if (typeof PIXI === 'undefined') {
        console.error('PIXI.js failed to load');
        return;
    }

    // Initialize PIXI application
    const app = new PIXI.Application({
        width: window.innerWidth,
        height: window.innerHeight,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
        resizeTo: window,
        backgroundColor: 0x333333
    });
    // Ensure the canvas sits BEHIND overlays (chat bubbles, controls, transcript)
    // Without explicit positioning/z-index, some browsers may paint the canvas above
    // absolutely positioned overlays depending on DOM order.
    app.view.style.position = 'fixed';
    app.view.style.top = '0';
    app.view.style.left = '0';
    app.view.style.width = '100%';
    app.view.style.height = '100%';
    app.view.style.zIndex = '0';

    document.body.appendChild(app.view);

    // ========================================
    // BACKGROUND IMAGE SPRITE
    // ========================================
    // This sprite will be dynamically loaded when the server sends a generated
    // background image based on the debate topic. If no image is received,
    // the default gray background (backgroundColor: 0x333333) remains visible.
    //
    // z-index management:
    // - Background sprite: addChildAt(sprite, 0) ensures it's behind everything
    // - Character sprites: addChild() adds them on top
    // - HTML overlays: z-index in CSS ensures they're above canvas
    let backgroundSprite = null;

    // ========================================
    // LOAD OBAMA SPRITE CHARACTER (LEFT SIDE)
    // ========================================
    // Define the Obama image paths for gesture cycling
    const obamaImagePaths = [
        'assets/obama.png',
        'assets/obama_gesture1.png',
        'assets/obama_gesture2.png',
    ];

    let currentObamaIndex = 0;
    let obamaSprites = [];

    // Load all Obama gesture images
    for (const path of obamaImagePaths) {
        try {
            const texture = await PIXI.Assets.load(path);
            const sprite = new PIXI.Sprite(texture);

            // Hide all except first sprite initially
            sprite.visible = (obamaSprites.length === 0);

            // Set anchor to center for easier positioning
            sprite.anchor.set(0.5, 0.5);

            obamaSprites.push(sprite);
            app.stage.addChild(sprite);
        } catch (error) {
            console.error(`Failed to load Obama image: ${path}`, error);
        }
    }

    if (obamaSprites.length === 0) {
        console.error('No Obama images loaded. Please ensure obama.png exists.');
        return;
    }

    // Get reference to currently visible Obama sprite
    let currentObamaSprite = obamaSprites[0];

    // Scale and position Obama on the LEFT side of screen
    // Target height that all Obama sprites should display at
    const obamaTargetHeight = window.innerHeight * 0.6;

    // Scale each sprite individually based on its own texture dimensions
    // This ensures all sprites appear the same size regardless of source image dimensions
    obamaSprites.forEach(sprite => {
        const scaleForThisSprite = obamaTargetHeight / sprite.texture.height;
        sprite.scale.set(scaleForThisSprite);
        // Position on left side, facing right toward Trump
        sprite.x = window.innerWidth * 0.25;  // Left quarter
        sprite.y = window.innerHeight / 2;
    });

    // Make Obama sprites draggable
    let obamaDragging = false;
    let obamaDragOffset = { x: 0, y: 0 };

    obamaSprites.forEach(sprite => {
        sprite.interactive = true;
        sprite.buttonMode = true;

        sprite.on('pointerdown', (event) => {
            obamaDragging = true;
            obamaDragOffset.x = event.data.global.x - sprite.x;
            obamaDragOffset.y = event.data.global.y - sprite.y;
        });
    });

    // ========================================
    // LOAD TRUMP SPRITE CHARACTER (RIGHT SIDE)
    // ========================================
    // Define the Trump image paths for gesture cycling
    const trumpImagePaths = [
        'assets/trump1.png',
        'assets/trumpTalk.png',
        'assets/trump2.png',
        'assets/trumpTalk2.png',
        'assets/trump3.png',
    ];

    let currentTrumpIndex = 0;
    let trumpSprites = [];

    // Load all Trump gesture images
    for (const path of trumpImagePaths) {
        try {
            const texture = await PIXI.Assets.load(path);
            const sprite = new PIXI.Sprite(texture);

            // Hide all except first sprite initially
            sprite.visible = (trumpSprites.length === 0);

            // Set anchor to center for easier positioning
            sprite.anchor.set(0.5, 0.5);

            trumpSprites.push(sprite);
            app.stage.addChild(sprite);
        } catch (error) {
            console.error(`Failed to load Trump image: ${path}`, error);
        }
    }

    if (trumpSprites.length === 0) {
        console.error('No Trump images loaded. Please ensure trump.png exists.');
        return;
    }

    // Get reference to currently visible Trump sprite
    let currentTrumpSprite = trumpSprites[0];

    // Scale and position Trump on the RIGHT side of screen
    // Target height that all Trump sprites should display at
    const trumpTargetHeight = window.innerHeight * 0.6;

    // Scale each sprite individually based on its own texture dimensions
    // This ensures all sprites appear the same size regardless of source image dimensions
    trumpSprites.forEach(sprite => {
        const scaleForThisSprite = trumpTargetHeight / sprite.texture.height;
        sprite.scale.set(scaleForThisSprite);
        // Position on right side, facing left toward Obama
        sprite.x = window.innerWidth * 0.75;  // Right quarter
        sprite.y = window.innerHeight / 2;
    });

    // Store base positions for breathing animations
    const trumpBaseY = window.innerHeight / 2;
    const obamaBaseY = window.innerHeight / 2;

    // ========================================
    // BREATHING ANIMATION (BOTH CHARACTERS)
    // ========================================
    // Add subtle breathing/bobbing to both sprites
    // Use phase offset so they breathe at different times (more natural conversation feel)
    let breathingTime = 0;
    const BREATHING_SPEED = 0.02;
    const BREATHING_Y_AMOUNT = 8;
    const BREATHING_SCALE_AMOUNT = 0.015;

    app.ticker.add(() => {
        breathingTime += BREATHING_SPEED;

        // Trump breathes normally
        const trumpBreathingOffset = Math.sin(breathingTime);

        // Obama breathes with phase offset (180 degrees out of sync)
        const obamaBreathingOffset = Math.sin(breathingTime + Math.PI);

        // Apply breathing to Trump
        // Calculate base scale from target height and actual texture dimensions for each sprite
        trumpSprites.forEach(sprite => {
            if (!trumpDragging) {
                sprite.y = trumpBaseY + (trumpBreathingOffset * BREATHING_Y_AMOUNT);

                // Calculate the base scale for this specific sprite based on its texture
                const baseScale = trumpTargetHeight / sprite.texture.height;
                const breathingScale = baseScale + (trumpBreathingOffset * BREATHING_SCALE_AMOUNT * baseScale);
                sprite.scale.set(breathingScale);
            }
        });

        // Apply breathing to Obama
        // Calculate base scale from target height and actual texture dimensions for each sprite
        obamaSprites.forEach(sprite => {
            if (!obamaDragging) {
                sprite.y = obamaBaseY + (obamaBreathingOffset * BREATHING_Y_AMOUNT);

                // Calculate the base scale for this specific sprite based on its texture
                const baseScale = obamaTargetHeight / sprite.texture.height;
                const breathingScale = baseScale + (obamaBreathingOffset * BREATHING_SCALE_AMOUNT * baseScale);
                sprite.scale.set(breathingScale);
            }
        });
    });

    // ========================================
    // AUTOMATIC GESTURE CYCLING (BOTH CHARACTERS)
    // ========================================
    // Cycle through Trump's different gesture images
    if (trumpSprites.length > 1) {
        const TRUMP_GESTURE_INTERVAL = 3000;  // Switch every 3 seconds

        setInterval(() => {
            currentTrumpSprite.visible = false;
            currentTrumpIndex = (currentTrumpIndex + 1) % trumpSprites.length;
            currentTrumpSprite = trumpSprites[currentTrumpIndex];
            currentTrumpSprite.visible = true;
        }, TRUMP_GESTURE_INTERVAL);
    }

    // Cycle through Obama's different gesture images
    // Use different interval so they don't sync up (more natural)
    if (obamaSprites.length > 1) {
        const OBAMA_GESTURE_INTERVAL = 2500;  // Slightly faster than Trump

        setInterval(() => {
            currentObamaSprite.visible = false;
            currentObamaIndex = (currentObamaIndex + 1) % obamaSprites.length;
            currentObamaSprite = obamaSprites[currentObamaIndex];
            currentObamaSprite.visible = true;
        }, OBAMA_GESTURE_INTERVAL);
    }

    // ========================================
    // TRUMP DRAGGING FUNCTIONALITY
    // ========================================
    let trumpDragging = false;
    let trumpDragOffset = { x: 0, y: 0 };

    trumpSprites.forEach(sprite => {
        sprite.interactive = true;
        sprite.buttonMode = true;

        sprite.on('pointerdown', (event) => {
            trumpDragging = true;
            trumpDragOffset.x = event.data.global.x - sprite.x;
            trumpDragOffset.y = event.data.global.y - sprite.y;
        });
    });

    // ========================================
    // UNIFIED DRAG HANDLING
    // ========================================
    // Handle dragging for both characters in a single event handler
    app.stage.on('pointermove', (event) => {
        if (obamaDragging) {
            const newX = event.data.global.x - obamaDragOffset.x;
            const newY = event.data.global.y - obamaDragOffset.y;

            obamaSprites.forEach(sprite => {
                sprite.x = newX;
                sprite.y = newY;
            });
        }
        if (trumpDragging) {
            const newX = event.data.global.x - trumpDragOffset.x;
            const newY = event.data.global.y - trumpDragOffset.y;

            trumpSprites.forEach(sprite => {
                sprite.x = newX;
                sprite.y = newY;
            });
        }
    });

    app.stage.on('pointerup', () => {
        obamaDragging = false;
        trumpDragging = false;
    });

    app.stage.on('pointerupoutside', () => {
        obamaDragging = false;
        trumpDragging = false;
    });

    // ========================================
    // WINDOW RESIZE HANDLING
    // ========================================
    // Reposition both characters and background when window is resized
    window.addEventListener('resize', () => {
        // Recalculate Obama's position (left side)
        const newObamaTargetHeight = window.innerHeight * 0.6;
        const newObamaScale = newObamaTargetHeight / (obamaSprites[0].texture.height);

        obamaSprites.forEach(sprite => {
            sprite.scale.set(newObamaScale);
            sprite.x = window.innerWidth * 0.25;
            sprite.y = window.innerHeight / 2;
        });

        // Recalculate Trump's position (right side)
        const newTrumpTargetHeight = window.innerHeight * 0.6;
        const newTrumpScale = newTrumpTargetHeight / (trumpSprites[0].texture.height);

        trumpSprites.forEach(sprite => {
            sprite.scale.set(newTrumpScale);
            sprite.x = window.innerWidth * 0.75;
            sprite.y = window.innerHeight / 2;
        });

        // Recalculate background sprite scale and position if it exists
        // This ensures the background always covers the full screen after resize
        if (backgroundSprite) {
            // Calculate new scale to cover screen (same logic as initial load)
            const scaleX = app.screen.width / backgroundSprite.texture.width;
            const scaleY = app.screen.height / backgroundSprite.texture.height;
            const scale = Math.max(scaleX, scaleY); // Cover mode

            backgroundSprite.scale.set(scale);

            // Re-center on the new screen dimensions
            backgroundSprite.x = app.screen.width / 2;
            backgroundSprite.y = app.screen.height / 2;
        }
    });

    // ========================================
    // DEBATE SYSTEM - WEBSOCKET CLIENT
    // ========================================
    /**
     * DebateClient manages the WebSocket connection to the Python backend debate server.
     * It handles:
     * - Real-time MP3 audio streaming from both AI debaters (Obama and Trump)
     * - Audio playback using HTML5 Audio elements
     * - Text transcript display
     * - Visual feedback when each speaker is talking
     *
     * The server streams MP3 audio as binary WebSocket frames.
     * We assemble these chunks into Blob objects and play them using HTML5 <audio> elements.
     */
    class DebateClient {
        constructor(pixiApp) {
            // Store reference to PIXI app for background image manipulation
            this.app = pixiApp;

            // WebSocket connection to Python backend
            this.ws = null;

            // Track current audio buffers being assembled from binary chunks
            this.audioBuffers = {
                'Obama': [],
                'Trump': []
            };

            // Track which speaker is currently receiving audio chunks
            this.currentlyReceivingAudio = null;

            // HTML5 Audio elements for playback (one per speaker)
            this.audioPlayers = {
                'Obama': new Audio(),
                'Trump': new Audio()
            };

            // Setup audio player event handlers
            this.setupAudioPlayers();
        }

        /**
         * Configure audio players with event handlers for playback lifecycle
         */
        setupAudioPlayers() {
            ['Obama', 'Trump'].forEach(speaker => {
                const player = this.audioPlayers[speaker];

                // When audio finishes playing, send playback_complete to server
                player.onended = () => {
                    console.log(`✅ ${speaker}'s audio playback completed`);
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send(JSON.stringify({
                            type: 'playback_complete',
                            speaker: speaker
                        }));
                    }
                    // Update visual state
                    this.updateSpeakerVisuals(speaker, false);
                };

                // Handle playback errors
                player.onerror = (e) => {
                    console.error(`❌ Audio playback error for ${speaker}:`, e);
                };

                // Log and update visuals when playback starts
                player.onplay = () => {
                    console.log(`🔊 Started playing ${speaker}'s audio`);
                    this.updateSpeakerVisuals(speaker, true);
                };
            });
        }

        /**
         * Establishes WebSocket connection to the debate server
         * Must be called from a user interaction (button click) due to browser autoplay policies
         *
         * @param {string} topic - The debate topic to send to the server
         */
        async connect(topic) {
            // Connect to Python WebSocket server on localhost:8765
            // Set binaryType to 'arraybuffer' to receive binary audio chunks
            this.ws = new WebSocket('ws://localhost:8765');
            this.ws.binaryType = 'arraybuffer';

            this.ws.onopen = () => {
                console.log('✅ Connected to debate server');

                // Send the debate topic to the server to initialize the debate
                this.ws.send(JSON.stringify({
                    type: 'start_debate',
                    topic: topic
                }));
            };

            this.ws.onmessage = (event) => {
                // Check if this is binary data (audio chunk) or text (JSON message)
                if (event.data instanceof ArrayBuffer) {
                    // Binary audio chunk - add to current speaker's buffer
                    this.handleBinaryAudio(event.data);
                } else {
                    // Text JSON message
                    const msg = JSON.parse(event.data);
                    this.handleMessage(msg);
                }
            };

            this.ws.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
            };

            this.ws.onclose = () => {
                console.log('🔌 Disconnected from debate server');
            };
        }

        /**
         * Routes incoming messages to appropriate handlers based on message type
         * Message types:
         * - 'init': Debate initialization with topic
         * - 'audio_start': Speaker's audio is about to stream
         * - 'audio_complete': Speaker's audio streaming finished
         * - 'text': Transcript text from a speaker
         * - 'background_image': Generated background image from server
         */
        handleMessage(msg) {
            switch(msg.type) {
                case 'init':
                    console.log('🎤 Debate topic:', msg.topic);
                    break;

                case 'background_image':
                    // Handle dynamically generated background image from server
                    this.loadBackgroundImage(msg.data, msg.format);
                    break;

                case 'audio_start':
                    // Start buffering audio for this speaker
                    console.log(`🎵 Starting audio reception for ${msg.speaker}`);
                    this.currentlyReceivingAudio = msg.speaker;
                    this.audioBuffers[msg.speaker] = []; // Clear previous buffer
                    break;

                case 'audio_complete':
                    // All audio chunks received - assemble and play
                    console.log(`🎵 Audio reception complete for ${msg.speaker}`);
                    this.playBufferedAudio(msg.speaker);
                    this.currentlyReceivingAudio = null;
                    break;

                case 'text':
                    // Display transcript in UI
                    this.handleTranscript(msg.speaker, msg.text);
                    break;
            }
        }

        /**
         * Handle incoming binary audio chunk from WebSocket
         *
         * @param {ArrayBuffer} arrayBuffer - Binary MP3 audio data
         */
        handleBinaryAudio(arrayBuffer) {
            if (!this.currentlyReceivingAudio) {
                console.warn('Received audio chunk but no speaker is active');
                return;
            }

            // Add binary chunk to the current speaker's buffer
            this.audioBuffers[this.currentlyReceivingAudio].push(arrayBuffer);
            console.log(
                `Added ${arrayBuffer.byteLength} bytes to ${this.currentlyReceivingAudio}'s buffer`
            );
        }

        /**
         * Assemble buffered audio chunks into a Blob and play it
         *
         * @param {string} speaker - "Obama" or "Trump"
         */
        playBufferedAudio(speaker) {
            const chunks = this.audioBuffers[speaker];
            if (!chunks || chunks.length === 0) {
                console.warn(`No audio chunks buffered for ${speaker}`);
                return;
            }

            // Create a Blob from all audio chunks
            // Browser natively handles MP3 decoding
            const audioBlob = new Blob(chunks, { type: 'audio/mpeg' });
            const audioUrl = URL.createObjectURL(audioBlob);

            console.log(
                `🎧 Playing ${speaker}'s audio (${audioBlob.size} bytes, ${chunks.length} chunks)`
            );

            // Set the audio source and play
            const player = this.audioPlayers[speaker];
            player.src = audioUrl;
            player.play().catch(error => {
                console.error(`Failed to play audio for ${speaker}:`, error);
            });

            // Clean up object URL after playback to free memory
            player.onended = () => {
                URL.revokeObjectURL(audioUrl);
                console.log(`✅ ${speaker}'s audio playback completed`);
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: 'playback_complete',
                        speaker: speaker
                    }));
                }
                this.updateSpeakerVisuals(speaker, false);
            };
        }

        /**
         * Displays speaker transcript in the UI
         *
         * @param {string} speaker - "Obama" or "Trump"
         * @param {string} text - Transcript text to display
         */
        handleTranscript(speaker, text) {
            console.log(`[${speaker}] ${text}`);
            this.updateTranscriptUI(speaker, text);
        }

        /**
         * Adds a transcript entry to the UI display
         * Creates a chat bubble for visual display
         *
         * @param {string} speaker - "Obama" or "Trump"
         * @param {string} text - Transcript text
         */
        updateTranscriptUI(speaker, text) {
            // Create chat bubble (main visual element)
            this.createChatBubble(speaker, text);
        }

        /**
         * Load and display a dynamically generated background image
         *
         * This method receives a base64-encoded image from the server (generated by Gemini),
         * decodes it, and loads it as a PIXI.Sprite background layer behind all characters.
         *
         * Architecture:
         * - Image arrives asynchronously after debate starts (non-blocking)
         * - Replaces any existing background sprite
         * - Scales to cover full screen while maintaining aspect ratio
         * - Positioned at z-index 0 (behind character sprites)
         *
         * Trade-offs:
         * - Cover scaling may crop image edges (better than letterboxing for fullscreen background)
         * - Base64 decoding is synchronous but fast enough for typical image sizes
         * - No loading spinner (image appears when ready, gray background until then)
         *
         * @param {string} base64Data - Base64-encoded image data from server
         * @param {string} format - Image format (png, jpeg, etc.)
         */
        async loadBackgroundImage(base64Data, format) {
            console.log(`🎨 Loading background image (${base64Data.length} chars base64, format: ${format})`);

            try {
                // Remove existing background sprite if present
                // This handles the case where a new debate starts while an old image is displayed
                if (backgroundSprite) {
                    console.log('🗑️  Removing old background sprite');
                    this.app.stage.removeChild(backgroundSprite);
                    backgroundSprite.destroy(true); // true = destroy texture too
                    backgroundSprite = null;
                }

                // Decode base64 to binary ArrayBuffer
                // atob() converts base64 string to binary string, then we convert to Uint8Array
                const binaryString = atob(base64Data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }

                // Create Blob from binary data
                // Blob is required to create an object URL that PIXI can load
                const blob = new Blob([bytes], { type: `image/${format}` });
                const imageUrl = URL.createObjectURL(blob);

                console.log(`📥 Loading image texture from blob URL: ${imageUrl}`);
                console.log(`📊 Blob size: ${blob.size} bytes, type: ${blob.type}`);

                // Load image using native Image element first, then convert to PIXI texture
                // This is more reliable than PIXI.Assets.load for blob URLs
                const img = new Image();
                const imageLoadPromise = new Promise((resolve, reject) => {
                    img.onload = () => {
                        console.log('🎉 Image onload event fired!');
                        resolve(img);
                    };
                    img.onerror = (e) => {
                        console.error('❌ Image onerror event fired:', e);
                        reject(new Error(`Failed to load image: ${e}`));
                    };
                });
                img.src = imageUrl;
                console.log(`📤 Image src set, waiting for load...`);

                // Wait for image to load
                await imageLoadPromise;
                console.log(`✅ Image loaded successfully: ${img.width}x${img.height}`);

                // Create PIXI texture from loaded image
                const texture = PIXI.Texture.from(img);
                console.log(`✅ PIXI Texture created: ${texture.width}x${texture.height}`);

                // Create sprite from texture
                const sprite = new PIXI.Sprite(texture);

                // Ensure sprite is fully opaque and visible
                sprite.alpha = 1.0;
                sprite.visible = true;

                // Calculate scale to cover full screen (similar to CSS background-size: cover)
                // This ensures no empty space, though it may crop edges
                const scaleX = this.app.screen.width / texture.width;
                const scaleY = this.app.screen.height / texture.height;
                const scale = Math.max(scaleX, scaleY); // max = cover (min = contain)

                console.log(`📊 Screen size: ${this.app.screen.width}x${this.app.screen.height}`);
                console.log(`📊 Texture size: ${texture.width}x${texture.height}`);
                console.log(`📊 Calculated scale: ${scale} (scaleX=${scaleX}, scaleY=${scaleY})`);

                sprite.scale.set(scale);

                // Center the sprite on screen
                sprite.anchor.set(0.5, 0.5);
                sprite.x = this.app.screen.width / 2;
                sprite.y = this.app.screen.height / 2;

                // Add at index 0 to place behind all existing sprites (characters)
                // This is crucial - characters were added with addChild() so they're already on top
                console.log(`📊 Stage children before adding background: ${this.app.stage.children.length}`);
                this.app.stage.addChildAt(sprite, 0);
                console.log(`📊 Stage children after adding background: ${this.app.stage.children.length}`);
                console.log(`📊 Background sprite added at index 0`);
                console.log(`📊 Sprite properties: x=${sprite.x}, y=${sprite.y}, scale=${sprite.scale.x}, visible=${sprite.visible}, alpha=${sprite.alpha}`);

                // Store reference for cleanup and resizing
                backgroundSprite = sprite;

                // Clean up object URL to free memory
                // Can be called immediately after texture loads
                URL.revokeObjectURL(imageUrl);

                console.log('✅ Background image loaded and displayed');
                console.log(`📊 Final stage children:`, this.app.stage.children);

            } catch (error) {
                // Graceful failure - log error but don't disrupt debate
                console.error('❌ Failed to load background image:', error);
                // Gray background remains visible if this fails
            }
        }

        /**
         * Creates an animated chat bubble for the speaker
         * Bubbles appear on the left (Obama) or right (Trump) side
         * with smooth slide-in animation
         *
         * @param {string} speaker - "Obama" or "Trump"
         * @param {string} text - Message text to display
         */
        createChatBubble(speaker, text) {
            const chatBubblesDiv = document.getElementById('chatBubbles');
            if (!chatBubblesDiv) return;

            // Create bubble container
            const bubble = document.createElement('div');
            bubble.className = `chat-bubble ${speaker.toLowerCase()}`;

            // Add speaker name badge
            const speakerName = document.createElement('span');
            speakerName.className = 'speaker-name';
            speakerName.textContent = speaker;

            // Add message text
            const messageText = document.createElement('div');
            messageText.className = 'message-text';
            messageText.textContent = text;

            // Assemble bubble
            bubble.appendChild(speakerName);
            bubble.appendChild(messageText);

            // Add to DOM
            chatBubblesDiv.appendChild(bubble);

            // Auto-scroll to show latest bubble
            // Use smooth scrolling for better UX
            chatBubblesDiv.scrollTo({
                top: chatBubblesDiv.scrollHeight,
                behavior: 'smooth'
            });
        }

        /**
         * Updates sprite visuals based on speaking state
         * Makes the speaking character brighter/more prominent
         *
         * Trade-offs:
         * - Alpha change: Simple but may be too subtle
         * - Scale pulse: More noticeable but can be distracting
         * - Tint/glow: Good middle ground (current implementation)
         *
         * @param {string} speaker - "Obama" or "Trump"
         * @param {boolean} isSpeaking - Whether the speaker is talking
         */
        updateSpeakerVisuals(speaker, isSpeaking) {
            // Get sprite array for the speaker
            const sprites = speaker === 'Obama' ? obamaSprites : trumpSprites;

            sprites.forEach(sprite => {
                if (isSpeaking) {
                    // Make brighter and fully opaque when speaking
                    sprite.alpha = 1.0;
                    sprite.tint = 0xFFFFFF;  // Full brightness
                } else {
                    // Dim slightly when not speaking
                    sprite.alpha = 0.8;
                    sprite.tint = 0xCCCCCC;  // Slightly dimmed
                }
            });
        }
    }

    // Initialize debate client instance
    // Will be connected when user clicks "Start Debate" button
    // Pass app reference so DebateClient can manipulate background sprite
    window.debateClient = new DebateClient(app);

    // ========================================
    // DEBATE CONTROLS
    // ========================================
    /**
     * Start button event handler
     * Browser requires user interaction before playing audio (autoplay policy)
     * This click handler satisfies that requirement and initializes the AudioContext
     */
    document.getElementById('startBtn').addEventListener('click', async () => {
        // Get the debate topic from the input field
        const topicInput = document.getElementById('topicInput');
        const topic = topicInput.value.trim();

        // Validate that user entered a topic
        if (!topic) {
            alert('Please enter a debate topic before starting!');
            topicInput.focus();
            return;
        }

        // Connect to server and send topic
        await window.debateClient.connect(topic);

        // Update UI state
        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;
        topicInput.disabled = true;  // Prevent changes during active debate
    });

    /**
     * Stop button event handler
     * Cleanly closes the WebSocket connection to the debate server
     * and clears the UI for the next debate
     *
     * This performs a complete cleanup so that a new debate can start fresh:
     * - Closes WebSocket connection
     * - Stops all audio playback
     * - Clears audio buffers
     * - Clears all UI elements (chat bubbles)
     * - Removes background sprite and frees memory
     * - Re-enables the topic input for the next debate
     */
    document.getElementById('stopBtn').addEventListener('click', () => {
        // Close WebSocket connection
        if (window.debateClient.ws) {
            window.debateClient.ws.close();
            window.debateClient.ws = null;
        }

        // Stop all audio playback
        ['Obama', 'Trump'].forEach(speaker => {
            const player = window.debateClient.audioPlayers[speaker];
            player.pause();
            player.src = '';  // Clear audio source
        });

        // Clear audio buffers
        window.debateClient.audioBuffers = {
            'Obama': [],
            'Trump': []
        };
        window.debateClient.currentlyReceivingAudio = null;

        // Clear chat bubbles for fresh start
        const chatBubblesDiv = document.getElementById('chatBubbles');
        if (chatBubblesDiv) {
            chatBubblesDiv.innerHTML = '';
        }

        // Clean up background sprite to prevent memory leaks
        // This ensures the next debate starts with a clean slate
        if (backgroundSprite) {
            console.log('🗑️  Cleaning up background sprite');
            app.stage.removeChild(backgroundSprite);
            backgroundSprite.destroy(true); // true = destroy texture and free GPU memory
            backgroundSprite = null;
        }

        // Update UI state - re-enable all controls for next debate
        document.getElementById('startBtn').disabled = false;
        document.getElementById('stopBtn').disabled = true;
        document.getElementById('topicInput').disabled = false;

        console.log('✅ Debate stopped and all state cleared');
    });
});
