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
    document.body.appendChild(app.view);

    // ========================================
    // LOAD OBAMA SPRITE CHARACTER (LEFT SIDE)
    // ========================================
    // Define the Obama image paths for gesture cycling
    const obamaImagePaths = [
        'obama.png',
        'obama_gesture1.png',
        'obama_gesture2.png',
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
        'trump.png',
        'trump_gesture1.png',
        'trump_gesture2.png',
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
    // Reposition both characters when window is resized
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
    });

    // ========================================
    // DEBATE SYSTEM - WEBSOCKET CLIENT
    // ========================================
    /**
     * DebateClient manages the WebSocket connection to the Python backend debate server.
     * It handles:
     * - Real-time audio streaming from both AI debaters (Obama and Trump)
     * - Audio playback using the Web Audio API
     * - Text transcript display
     * - Visual feedback when each speaker is talking
     *
     * The class uses a queue-based playback system to ensure smooth, gapless audio
     * even with network latency. Audio from Gemini arrives as 16-bit PCM at 24kHz,
     * which we convert to AudioBuffers for browser playback.
     */
    class DebateClient {
        constructor() {
            // WebSocket connection to Python backend
            this.ws = null;

            // Web Audio API context for playback
            // Must be initialized after user interaction (browser security requirement)
            this.audioContext = null;

            // Separate audio queues for each speaker to prevent cross-talk
            // Queue-based playback ensures smooth transitions between audio chunks
            this.audioQueues = {
                'Obama': [],
                'Trump': []
            };

            // Track playback state to prevent overlapping playback of same speaker
            this.isPlaying = {
                'Obama': false,
                'Trump': false
            };
        }

        /**
         * Establishes WebSocket connection to the debate server and initializes audio
         * Must be called from a user interaction (button click) due to browser autoplay policies
         *
         * @param {string} topic - The debate topic to send to the server
         */
        async connect(topic) {
            // Initialize Web Audio API
            // AudioContext must be created after user gesture (browser security requirement)
            this.audioContext = new AudioContext();

            // Connect to Python WebSocket server on localhost:8765
            this.ws = new WebSocket('ws://localhost:8765');

            this.ws.onopen = () => {
                console.log('✅ Connected to debate server');

                // Send the debate topic to the server to initialize the debate
                // Server will use this to create system instructions for both AIs
                this.ws.send(JSON.stringify({
                    type: 'start_debate',
                    topic: topic
                }));
            };

            this.ws.onmessage = (event) => {
                // All messages from server are JSON-encoded
                const msg = JSON.parse(event.data);
                this.handleMessage(msg);
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
         * - 'audio': PCM audio data from a speaker
         * - 'text': Transcript text from a speaker
         * - 'speaking': Speaking state change (for visual feedback)
         */
        handleMessage(msg) {
            switch(msg.type) {
                case 'init':
                    console.log('🎤 Debate topic:', msg.topic);
                    break;

                case 'audio':
                    // Queue audio for playback
                    this.handleAudio(msg.speaker, msg.data);
                    break;

                case 'text':
                    // Display transcript in UI
                    this.handleTranscript(msg.speaker, msg.text);
                    break;

                case 'speaking':
                    // Update sprite visuals based on speaking state
                    this.handleSpeakingState(msg.speaker, msg.is_speaking);
                    break;
            }
        }

        /**
         * Processes incoming audio data and queues it for playback
         * Audio arrives as hex-encoded PCM bytes which we convert to Uint8Array
         *
         * @param {string} speaker - "Obama" or "Trump"
         * @param {string} hexData - Hex-encoded audio data (e.g., "0a1b2c3d...")
         */
        handleAudio(speaker, hexData) {
            // Convert hex string to Uint8Array
            // Each pair of hex characters represents one byte (e.g., "0a" = 10)
            const bytes = new Uint8Array(
                hexData.match(/.{1,2}/g).map(byte => parseInt(byte, 16))
            );

            // Add audio chunk to speaker's queue
            this.audioQueues[speaker].push(bytes);

            // Start playback if not already playing
            // This ensures continuous playback without gaps
            if (!this.isPlaying[speaker]) {
                this.playAudioQueue(speaker);
            }
        }

        /**
         * Continuously plays queued audio chunks for a given speaker
         * Uses async/await to ensure sequential playback without gaps
         *
         * @param {string} speaker - "Obama" or "Trump"
         */
        async playAudioQueue(speaker) {
            this.isPlaying[speaker] = true;

            // Process queue until empty
            while (this.audioQueues[speaker].length > 0) {
                const audioData = this.audioQueues[speaker].shift();

                // Convert raw PCM data to Web Audio API format
                const audioBuffer = this.pcmToAudioBuffer(audioData);

                // Play the audio chunk and wait for it to finish
                // The 'await' ensures gapless sequential playback
                await this.playAudioBuffer(audioBuffer);
            }

            this.isPlaying[speaker] = false;
        }

        /**
         * Converts 16-bit PCM audio data to an AudioBuffer for Web Audio API playback
         *
         * Gemini Live API outputs:
         * - 16-bit signed integer PCM (Int16)
         * - 24kHz sample rate
         * - Mono (1 channel)
         *
         * Web Audio API requires:
         * - 32-bit float samples (Float32)
         * - Range: -1.0 to +1.0
         *
         * @param {Uint8Array} pcmData - Raw PCM bytes from Gemini
         * @returns {AudioBuffer} - AudioBuffer ready for playback
         */
        pcmToAudioBuffer(pcmData) {
            // Gemini sends 16-bit PCM at 24kHz mono
            const sampleRate = 24000;
            const numChannels = 1;

            // Convert Uint8Array to Int16Array (16-bit samples)
            // This reinterprets the byte buffer as signed 16-bit integers
            const int16Data = new Int16Array(pcmData.buffer);

            // Create AudioBuffer with appropriate dimensions
            const audioBuffer = this.audioContext.createBuffer(
                numChannels,
                int16Data.length,
                sampleRate
            );

            // Convert Int16 samples to Float32 (Web Audio API format)
            const channelData = audioBuffer.getChannelData(0);
            for (let i = 0; i < int16Data.length; i++) {
                // Normalize 16-bit PCM (-32768 to +32767) to Float32 (-1.0 to +1.0)
                // Divide by 32768 (2^15) to map the range
                channelData[i] = int16Data[i] / 32768.0;
            }

            return audioBuffer;
        }

        /**
         * Plays an AudioBuffer through the speakers
         * Returns a Promise that resolves when playback completes
         *
         * @param {AudioBuffer} audioBuffer - The audio to play
         * @returns {Promise} - Resolves when audio finishes playing
         */
        playAudioBuffer(audioBuffer) {
            return new Promise((resolve) => {
                // Create a buffer source node (one-time use)
                const source = this.audioContext.createBufferSource();
                source.buffer = audioBuffer;

                // Connect to speakers
                source.connect(this.audioContext.destination);

                // Resolve promise when playback ends
                source.onended = resolve;

                // Start playback immediately
                source.start();
            });
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
         * Updates visual feedback when a speaker starts/stops talking
         *
         * @param {string} speaker - "Obama" or "Trump"
         * @param {boolean} isSpeaking - Whether the speaker is currently talking
         */
        handleSpeakingState(speaker, isSpeaking) {
            this.updateSpeakerVisuals(speaker, isSpeaking);
        }

        /**
         * Adds a transcript entry to the UI display
         * Creates both a chat bubble and a compact transcript entry
         *
         * Design decisions:
         * - Chat bubbles: Large, prominent, positioned like a conversation
         * - Transcript: Compact log at bottom for full history reference
         *
         * @param {string} speaker - "Obama" or "Trump"
         * @param {string} text - Transcript text
         */
        updateTranscriptUI(speaker, text) {
            // Create chat bubble (main visual element)
            this.createChatBubble(speaker, text);

            // Also add to compact transcript log at bottom
            const transcriptDiv = document.getElementById('transcript');
            if (transcriptDiv) {
                const entry = document.createElement('div');
                entry.className = `transcript-entry ${speaker.toLowerCase()}`;
                entry.innerHTML = `<strong>${speaker}:</strong> ${text}`;
                transcriptDiv.appendChild(entry);

                // Auto-scroll to bottom to show latest message
                transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
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
    window.debateClient = new DebateClient();

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
     */
    document.getElementById('stopBtn').addEventListener('click', () => {
        if (window.debateClient.ws) {
            window.debateClient.ws.close();
        }

        // Clear chat bubbles and transcript for fresh start
        const chatBubblesDiv = document.getElementById('chatBubbles');
        if (chatBubblesDiv) {
            chatBubblesDiv.innerHTML = '';
        }

        const transcriptDiv = document.getElementById('transcript');
        if (transcriptDiv) {
            transcriptDiv.innerHTML = '';
        }

        // Update UI state
        document.getElementById('startBtn').disabled = false;
        document.getElementById('stopBtn').disabled = true;
        document.getElementById('topicInput').disabled = false;  // Re-enable for next debate
    });
});
