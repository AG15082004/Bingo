// BINGO CLIENT APP LOGIC

// 1. STATE VARIABLES
let socket = null;
let currentRoom = null;
let myPlayerId = localStorage.getItem('bingo_player_id');
let myPlayerName = localStorage.getItem('bingo_player_name') || '';
let drawIntervalTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// Fallback to random string if no playerId is found
if (!myPlayerId) {
    myPlayerId = 'usr_' + Math.random().toString(36).substring(2, 11) + Math.random().toString(36).substring(2, 11);
    localStorage.setItem('bingo_player_id', myPlayerId);
}

// 2. DOM ELEMENTS
const dom = {
    appContainer: document.getElementById('app-container'),
    // Views
    lobbyView: document.getElementById('lobby-view'),
    gameView: document.getElementById('game-view'),
    // Lobby inputs & buttons
    usernameInput: document.getElementById('username-input'),
    createRoomBtn: document.getElementById('create-room-btn'),
    roomCodeInput: document.getElementById('room-code-input'),
    joinRoomBtn: document.getElementById('join-room-btn'),
    lobbyError: document.getElementById('lobby-error'),
    // Header
    roomCodeDisplay: document.getElementById('room-code-display'),
    copyLinkBtn: document.getElementById('copy-link-btn'),
    copyTooltip: document.getElementById('copy-tooltip'),
    playerCountDisplay: document.getElementById('player-count-display'),
    leaveRoomBtn: document.getElementById('leave-room-btn'),
    // Game elements
    bingoGrid: document.getElementById('bingo-grid'),
    cardOwnerBadge: document.getElementById('card-owner-badge'),
    timerText: document.getElementById('timer-text'),
    timerProgress: document.getElementById('timer-progress'),
    currentBall: document.getElementById('current-ball'),
    startGameBtn: document.getElementById('start-game-btn'),
    waitingForHost: document.getElementById('waiting-for-host'),
    calledNumbersList: document.getElementById('called-numbers-list'),
    totalDrawsCount: document.getElementById('total-draws-count'),
    playersListContainer: document.getElementById('players-list-container'),
    floatingReactionContainer: document.getElementById('floating-reaction-container'),
    // Chat elements
    chatMessages: document.getElementById('chat-messages'),
    chatInput: document.getElementById('chat-input'),
    sendChatBtn: document.getElementById('send-chat-btn'),
    emojiButtons: document.querySelectorAll('.emoji-btn'),
    // Overlays & Modals
    reconnectOverlay: document.getElementById('reconnect-overlay'),
    winnerModal: document.getElementById('winner-modal'),
    winnerNameDisplay: document.getElementById('winner-name-display'),
    statRoomCode: document.getElementById('stat-room-code'),
    statCalls: document.getElementById('stat-calls'),
    statDuration: document.getElementById('stat-duration'),
    playAgainBtn: document.getElementById('play-again-btn'),
    hostRestartMsg: document.getElementById('host-restart-msg'),
    winnerHomeBtn: document.getElementById('winner-home-btn'),
    confettiCanvas: document.getElementById('confetti-canvas')
};

// SVG stroke length calculation for timer ring (2 * PI * r) where r=52 -> 326.7
const TIMER_CIRCUMFERENCE = 326.72;
dom.timerProgress.style.strokeDasharray = TIMER_CIRCUMFERENCE;
dom.timerProgress.style.strokeDashoffset = TIMER_CIRCUMFERENCE;

// 3. INITIALIZATION & ROUTING
window.addEventListener('DOMContentLoaded', () => {
    // Fill saved name
    if (myPlayerName) {
        dom.usernameInput.value = myPlayerName;
    }

    // Check if the URL has a room code preloaded (e.g. /room/AB12CD)
    const code = getRoomCodeFromUrl();
    if (code) {
        dom.roomCodeInput.value = code;
    }

    setupEventListeners();
});

// Parse window.location path to extract room code
function getRoomCodeFromUrl() {
    const paths = window.location.pathname.split('/');
    const roomIdx = paths.indexOf('room');
    if (roomIdx !== -1 && paths[roomIdx + 1]) {
        return paths[roomIdx + 1].toUpperCase();
    }
    return null;
}

// 4. EVENT LISTENERS SETUP
function setupEventListeners() {
    // Home/Lobby Events
    dom.createRoomBtn.addEventListener('click', handleCreateRoom);
    dom.joinRoomBtn.addEventListener('click', handleJoinRoomClick);

    // Game view Events
    dom.leaveRoomBtn.addEventListener('click', handleLeaveRoom);
    dom.copyLinkBtn.addEventListener('click', copyInviteLink);
    dom.startGameBtn.addEventListener('click', startGame);
    dom.playAgainBtn.addEventListener('click', restartGame);
    
    // Chat & reactions
    dom.sendChatBtn.addEventListener('click', sendChatMessage);
    dom.chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });
    
    dom.emojiButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const emoji = btn.getAttribute('data-emoji');
            sendEmojiReaction(emoji);
        });
    });

    // Modals
    dom.winnerHomeBtn.addEventListener('click', handleLeaveRoom);
}

// 5. REST ACTIONS
async function handleCreateRoom() {
    const name = dom.usernameInput.value.trim();
    if (!name) {
        showLobbyError("Please enter your name first!");
        return;
    }
    myPlayerName = name;
    localStorage.setItem('bingo_player_name', name);

    try {
        const res = await fetch('/api/create-room', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ draw_interval: 5 })
        });
        
        if (!res.ok) throw new Error("Failed to create room server-side.");
        
        const data = await res.json();
        const roomCode = data.room_code;
        
        // Push clean SPA URL to address bar
        const shortCode = roomCode.replace('ROOM-', '');
        history.pushState(null, '', `/room/${shortCode}`);
        
        connectWebSocket(roomCode);
    } catch (e) {
        showLobbyError("Connection error: " + e.message);
    }
}

async function handleJoinRoomClick() {
    const name = dom.usernameInput.value.trim();
    if (!name) {
        showLobbyError("Please enter your name first!");
        return;
    }
    myPlayerName = name;
    localStorage.setItem('bingo_player_name', name);

    const inputCode = dom.roomCodeInput.value.trim().toUpperCase();
    if (!inputCode) {
        showLobbyError("Please enter a room code!");
        return;
    }

    // Format input (ensure ROOM- prefix)
    const formattedCode = inputCode.startsWith('ROOM-') ? inputCode : `ROOM-${inputCode}`;

    // Verify room existence before joining
    try {
        const res = await fetch(`/api/check-room/${formattedCode}`);
        if (!res.ok) throw new Error("Failed to verify room.");
        
        const data = await res.json();
        if (!data.exists) {
            showLobbyError("Room not found! Check your code.");
            return;
        }

        // Push SPA URL to address bar
        const shortCode = formattedCode.replace('ROOM-', '');
        history.pushState(null, '', `/room/${shortCode}`);
        
        connectWebSocket(formattedCode);
    } catch (e) {
        showLobbyError("Error joining room: " + e.message);
    }
}

function showLobbyError(msg) {
    dom.lobbyError.textContent = msg;
    dom.lobbyError.classList.remove('hidden');
    setTimeout(() => {
        dom.lobbyError.classList.add('hidden');
    }, 4000);
}

// 6. WEBSOCKET MANAGING
function connectWebSocket(roomCode) {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws/${roomCode}`;
    
    if (socket) {
        socket.close();
    }
    
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        reconnectAttempts = 0;
        dom.reconnectOverlay.classList.add('hidden');
        
        // Handshake Payload
        socket.send(JSON.stringify({
            type: 'join_room',
            player_name: myPlayerName,
            player_id: myPlayerId
        }));
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerEvent(data);
    };

    socket.onclose = (event) => {
        logger("WebSocket closed: " + event.reason);
        // If not intentional, attempt reconnect
        if (currentRoom) {
            triggerReconnection(roomCode);
        }
    };

    socket.onerror = (err) => {
        logger("WebSocket Error: " + err);
    };
}

function triggerReconnection(roomCode) {
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        dom.reconnectOverlay.classList.add('hidden');
        alert("Unable to reconnect. Returning to Home.");
        handleLeaveRoom();
        return;
    }
    
    dom.reconnectOverlay.classList.remove('hidden');
    reconnectAttempts++;
    
    const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
    logger(`Reconnection attempt ${reconnectAttempts} in ${timeout}ms...`);
    
    setTimeout(() => {
        connectWebSocket(roomCode);
    }, timeout);
}

function handleLeaveRoom() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'leave_room' }));
    }
    
    if (socket) {
        socket.close();
        socket = null;
    }
    
    // Clear loop state
    clearInterval(drawIntervalTimer);
    stopConfetti();
    currentRoom = null;
    
    // Reset view url
    history.pushState(null, '', '/');
    
    // Toggle view layout
    dom.gameView.classList.add('hidden');
    dom.winnerModal.classList.add('hidden');
    dom.lobbyView.classList.remove('hidden');
    dom.lobbyView.classList.add('active');
    dom.roomCodeInput.value = '';
}

// 7. WEBSOCKET EVENTS HANDLER
function handleServerEvent(data) {
    const event = data.event;
    
    switch (event) {
        case 'room_state':
            updateRoomState(data.room);
            break;
            
        case 'player_joined':
            addSystemChatMessage(`${data.player_name} joined the room!`);
            updateRoomState(data.room);
            break;
            
        case 'player_left':
            addSystemChatMessage(`${data.player_name} left the room.`);
            updateRoomState(data.room);
            break;
            
        case 'game_started':
            addSystemChatMessage(`Host started the game! Game on!`);
            stopConfetti();
            dom.winnerModal.classList.add('hidden');
            updateRoomState(data.room);
            break;
            
        case 'number_drawn':
            animateBallDraw(data.number);
            updateRoomState(data.room);
            break;
            
        case 'winner_detected':
            updateRoomState(data.room);
            showWinnerOverlay(data.room);
            break;
            
        case 'chat_message':
            appendChatMessage(data.chat);
            break;
            
        case 'reaction':
            spawnFloatingReaction(data.player_name, data.emoji);
            break;
            
        case 'room_deleted':
            alert("Room has been automatically removed.");
            handleLeaveRoom();
            break;
            
        case 'error':
            alert(data.message);
            break;
    }
}

// Update local state and redraw screen panels
function updateRoomState(room) {
    currentRoom = room;
    
    // Switch views if not done
    if (dom.gameView.classList.contains('hidden')) {
        dom.lobbyView.classList.remove('active');
        dom.lobbyView.classList.add('hidden');
        dom.gameView.classList.remove('hidden');
        dom.gameView.classList.add('active');
    }
    
    // Display Room header information
    const shortCode = room.code.replace('ROOM-', '');
    dom.roomCodeDisplay.textContent = room.code;
    
    // Render Players list
    renderPlayersList(room.players);
    const pCount = Object.keys(room.players).length;
    dom.playerCountDisplay.textContent = `👥 ${pCount} Player${pCount !== 1 ? 's' : ''}`;
    
    // Find my player identity
    const me = room.players[myPlayerId];
    if (me) {
        dom.cardOwnerBadge.textContent = me.is_host ? '👑 Host' : '👤 Player';
        dom.cardOwnerBadge.className = me.is_host ? 'badge badge-primary' : 'badge';
        renderBingoCard(me.card);
        
        // Host Action Panel control
        if (me.is_host) {
            dom.startGameBtn.classList.toggle('hidden', room.state !== 'lobby');
            dom.playAgainBtn.classList.toggle('hidden', room.state !== 'game_over');
            dom.waitingForHost.classList.add('hidden');
            dom.hostRestartMsg.classList.add('hidden');
        } else {
            dom.startGameBtn.classList.add('hidden');
            dom.playAgainBtn.classList.add('hidden');
            dom.waitingForHost.classList.toggle('hidden', room.state !== 'lobby');
            dom.hostRestartMsg.classList.toggle('hidden', room.state !== 'game_over');
        }
    }
    
    // Draw List History & Counter
    renderCalledNumbers(room.draw_history);
    dom.totalDrawsCount.textContent = `${room.draw_history.length} / 75`;
    
    // State-specific panel renderings
    if (room.state === 'playing') {
        startLocalTimer(room.last_draw_time, room.draw_interval);
    } else {
        clearInterval(drawIntervalTimer);
        resetTimerRing();
    }
    
    // Set Current Drawn ball view
    if (room.current_draw) {
        const ball = dom.currentBall;
        ball.className = `bingo-ball ball-${getLetterForNumber(room.current_draw)}`;
        ball.querySelector('.ball-letter').textContent = getLetterForNumber(room.current_draw);
        ball.querySelector('.ball-number').textContent = room.current_draw;
    } else {
        const ball = dom.currentBall;
        ball.className = 'bingo-ball idle';
        ball.querySelector('.ball-letter').textContent = '';
        ball.querySelector('.ball-number').textContent = '--';
    }
}

// 8. RENDER SUB-COMPONENTS
function renderBingoCard(card) {
    dom.bingoGrid.innerHTML = '';
    
    for (let r = 0; r < 5; r++) {
        for (let c = 0; c < 5; c++) {
            const val = card.matrix[r][c];
            const isMarked = card.marked[r][c];
            
            const cell = document.createElement('div');
            cell.className = 'bingo-cell';
            
            const span = document.createElement('span');
            span.textContent = val;
            cell.appendChild(span);
            
            if (val === 'FREE') {
                cell.classList.add('free-space');
            }
            
            if (isMarked) {
                cell.classList.add('marked');
            }
            
            // Highlight cell if it is part of the winning pattern
            if (currentRoom.state === 'game_over' && currentRoom.winning_pattern) {
                const cells = currentRoom.winning_pattern.cells;
                const isWinningCell = cells.some(coord => coord[0] === r && coord[1] === c);
                if (isWinningCell) {
                    cell.classList.add('winning-cell');
                }
            }
            
            dom.bingoGrid.appendChild(cell);
        }
    }
}

function renderPlayersList(players) {
    dom.playersListContainer.innerHTML = '';
    
    Object.values(players).forEach(p => {
        const row = document.createElement('div');
        row.className = 'player-row';
        
        const infoLeft = document.createElement('div');
        infoLeft.className = 'player-info-left';
        
        const dot = document.createElement('span');
        dot.className = p.is_connected ? 'player-status-dot' : 'player-status-dot disconnected';
        
        const name = document.createElement('span');
        name.className = 'player-name-label';
        name.textContent = p.name;
        if (p.id === myPlayerId) {
            name.textContent += ' (You)';
        }
        
        infoLeft.appendChild(dot);
        infoLeft.appendChild(name);
        
        const badges = document.createElement('div');
        badges.className = 'player-meta-badges';
        
        if (p.is_host) {
            const hostBadge = document.createElement('span');
            hostBadge.className = 'badge badge-primary';
            hostBadge.textContent = 'Host';
            badges.appendChild(hostBadge);
        }
        
        // Count marked cells (excluding FREE)
        let marksCount = 0;
        for (let r = 0; r < 5; r++) {
            for (let c = 0; c < 5; c++) {
                if (p.card.marked[r][c] && p.card.matrix[r][c] !== 'FREE') {
                    marksCount++;
                }
            }
        }
        
        const marksBadge = document.createElement('span');
        marksBadge.className = 'badge';
        marksBadge.textContent = `🎯 ${marksCount}`;
        badges.appendChild(marksBadge);
        
        row.appendChild(infoLeft);
        row.appendChild(badges);
        dom.playersListContainer.appendChild(row);
    });
}

function renderCalledNumbers(history) {
    dom.calledNumbersList.innerHTML = '';
    
    // Sort in reverse order to see recent calls first or keep in order?
    // User request: "Display all previously drawn numbers. Sorted in draw order. Highlight latest draw."
    // Draw order means oldest to newest (or newest first?). Let's draw them in drawing order:
    for (let i = 0; i < history.length; i++) {
        const num = history[i];
        const numDiv = document.createElement('div');
        numDiv.className = 'history-num called';
        numDiv.textContent = num;
        
        // Highlight latest
        if (i === history.length - 1) {
            numDiv.classList.add('latest');
        }
        dom.calledNumbersList.appendChild(numDiv);
    }
    
    // Scroll list to the end to always focus on the latest drawn numbers
    dom.calledNumbersList.scrollTop = dom.calledNumbersList.scrollHeight;
}

// 9. ANIMATIONS & TIMER
function animateBallDraw(num) {
    const ball = dom.currentBall;
    ball.classList.remove('animate-draw');
    // Force DOM redraw to reset animation
    void ball.offsetWidth;
    ball.classList.add('animate-draw');
}

function startLocalTimer(lastDrawTimestamp, drawInterval) {
    clearInterval(drawIntervalTimer);
    
    if (!lastDrawTimestamp) return;
    
    const updateCountdown = () => {
        const now = Date.now() / 1000;
        const elapsed = now - lastDrawTimestamp;
        const remaining = Math.max(0, drawInterval - elapsed);
        
        // Update timer UI text
        dom.timerText.textContent = Math.ceil(remaining);
        
        // Calculate offset (326.72 is full progress, 0 is finished)
        const pct = remaining / drawInterval;
        const offset = TIMER_CIRCUMFERENCE * (1 - pct);
        dom.timerProgress.style.strokeDashoffset = offset;
        
        if (remaining <= 0) {
            clearInterval(drawIntervalTimer);
        }
    };
    
    updateCountdown(); // Run immediately
    drawIntervalTimer = setInterval(updateCountdown, 100);
}

function resetTimerRing() {
    dom.timerText.textContent = '--';
    dom.timerProgress.style.strokeDashoffset = TIMER_CIRCUMFERENCE;
}

function getLetterForNumber(num) {
    if (num >= 1 && num <= 10) return 'B';
    if (num >= 11 && num <= 20) return 'I';
    if (num >= 21 && num <= 30) return 'N';
    if (num >= 31 && num <= 40) return 'G';
    if (num >= 41 && num <= 50) return 'O';
    return 'B'; // Fallback
}

// Helper to copy Invite link
function copyInviteLink() {
    const link = `${window.location.origin}/room/${currentRoom.code.replace('ROOM-', '')}`;
    
    navigator.clipboard.writeText(link).then(() => {
        dom.copyTooltip.textContent = "Copied!";
        setTimeout(() => {
            dom.copyTooltip.textContent = "Copy Link";
        }, 2000);
    }).catch(err => {
        logger("Error copying invite URL: " + err);
    });
}

// 10. HOST ACTIONS
function startGame() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'start_game' }));
    }
}

function restartGame() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'play_again' }));
    }
}

// 11. CHAT & REACTIONS LIFE
function sendChatMessage() {
    const text = dom.chatInput.value.trim();
    if (!text) return;
    
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'send_chat',
            message: text
        }));
        dom.chatInput.value = '';
    }
}

function appendChatMessage(chat) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    
    const meta = document.createElement('span');
    meta.className = 'chat-meta';
    meta.textContent = `${chat.name}:`;
    
    const txt = document.createElement('span');
    txt.className = 'chat-text';
    txt.textContent = chat.message;
    
    const time = document.createElement('span');
    time.className = 'chat-time';
    time.textContent = chat.timestamp;
    
    bubble.appendChild(meta);
    bubble.appendChild(txt);
    bubble.appendChild(time);
    
    dom.chatMessages.appendChild(bubble);
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function addSystemChatMessage(text) {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble system-msg';
    bubble.textContent = text;
    dom.chatMessages.appendChild(bubble);
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function sendEmojiReaction(emoji) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'send_reaction',
            emoji: emoji
        }));
    }
}

// Floating reaction on center panel
function spawnFloatingReaction(name, emoji) {
    const container = dom.floatingReactionContainer;
    const reaction = document.createElement('div');
    reaction.className = 'floating-reaction';
    reaction.textContent = emoji;
    
    // Random horizontal position inside center container
    const width = container.offsetWidth;
    const xPos = Math.random() * (width - 40);
    reaction.style.left = `${xPos}px`;
    reaction.style.bottom = `10px`;
    
    container.appendChild(reaction);
    
    // Self clean
    setTimeout(() => {
        reaction.remove();
    }, 2000);
}

// 12. CANVAS CONFETTI PARTICLE ANIMATOR
let confettiActive = false;
let confettiInterval = null;
const ctx = dom.confettiCanvas.getContext('2d');
let particles = [];

function resizeCanvas() {
    dom.confettiCanvas.width = window.innerWidth;
    dom.confettiCanvas.height = window.innerHeight;
}
window.addEventListener('resize', resizeCanvas);

function startConfetti() {
    if (confettiActive) return;
    confettiActive = true;
    resizeCanvas();
    particles = [];
    
    // Spawn initial particles
    for (let i = 0; i < 150; i++) {
        particles.push(createParticle());
    }
    
    confettiInterval = requestAnimationFrame(animateConfetti);
}

function stopConfetti() {
    confettiActive = false;
    cancelAnimationFrame(confettiInterval);
    ctx.clearRect(0, 0, dom.confettiCanvas.width, dom.confettiCanvas.height);
}

function createParticle() {
    const colors = ['#f1c40f', '#e67e22', '#e74c3c', '#9b59b6', '#3498db', '#2ecc71'];
    return {
        x: Math.random() * dom.confettiCanvas.width,
        y: Math.random() * -dom.confettiCanvas.height,
        size: Math.random() * 8 + 6,
        color: colors[Math.floor(Math.random() * colors.length)],
        speedX: Math.random() * 4 - 2,
        speedY: Math.random() * 5 + 3,
        rotation: Math.random() * 360,
        rotationSpeed: Math.random() * 6 - 3
    };
}

function animateConfetti() {
    if (!confettiActive) return;
    ctx.clearRect(0, 0, dom.confettiCanvas.width, dom.confettiCanvas.height);
    
    particles.forEach(p => {
        p.x += p.speedX;
        p.y += p.speedY;
        p.rotation += p.rotationSpeed;
        
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
        ctx.restore();
        
        // Loop back up if it falls past bottom
        if (p.y > dom.confettiCanvas.height) {
            p.y = -20;
            p.x = Math.random() * dom.confettiCanvas.width;
        }
    });
    
    confettiInterval = requestAnimationFrame(animateConfetti);
}

// 13. WINNER ACTIONS DISPLAY
function showWinnerOverlay(room) {
    dom.winnerNameDisplay.textContent = room.winners.join(', ');
    dom.statRoomCode.textContent = room.code.replace('ROOM-', '');
    dom.statCalls.textContent = room.total_calls;
    dom.statDuration.textContent = `${room.duration}s`;
    
    dom.winnerModal.classList.remove('hidden');
    startConfetti();
}

function logger(message) {
    console.log(`[BINGO] ${message}`);
}
