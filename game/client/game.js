'use strict'
const Game = (() => {
    const game = {
        onLoading: null,
        onRunning: null,
        onFinish: null,
        onError: null,

        start: async (canvas, host, tokens) => {
            if (mStatus !== kStatus_None && mStatus !== kStatus_Finished && mStatus !== kStatus_Error)
                throw errorWithMessage('Attempt to start game multiple times');
            mStatus = kStatus_Loading;
            try {
                game.onLoading && game.onLoading();
            } catch {}

            try {
                if (location.protocol !== 'https:' && location.protocol !== 'http:')
                    throw errorWithMessage('Unsupported protocol');
                let address = location.protocol.replace('http', 'ws')
                    .concat(
                        '//', host, '/game',
                        ...tokens.map((token, index) =>
                            `${index === 0 ? "?" : "&"}with_token=${token}`
                        )
                    );

                mCanvas = canvas;
                mContext = canvas.getContext('2d');
                if (mContext === null || mContext === undefined)
                    throw errorWithMessage('Unable to get 2D drawing context');

                mInputState = 0;
                mLastInputState = 0;
                mReadyCallback = null;
                mLastUpdateTime = null;
                mNextUpdateTime = null;
                mAverageUpdateDelta = null;

                await new Promise((resolve, reject) => {
                    const timeout = setTimeout(() => {
                        reject(errorWithMessage('Timeout during connection attempt'));
                        try {
                            mSocket.close();
                        } catch {}
                    }, 2500);

                    mSocket = new WebSocket(address);
                    mSocket.binaryType = 'arraybuffer';
                    mSocket.onmessage = event => {
                        clearTimeout(timeout);
                        resolve(mSocket);
                        onSocketMessage(event);
                    };
                    mSocket.onclose = () => {
                        clearTimeout(timeout);
                        reject(errorWithMessage('Unable to connect to server'));
                    };
                });
                mSocket.onmessage = onSocketMessage;
                mSocket.onclose = null;

                await new Promise((resolve, reject) => {
                    const timeout = setTimeout(() => {
                        mSocket.onmessage = null;
                        mSocket.onclose = null;
                        try {
                            mSocket.close();
                        } catch {}
                        reject(errorWithMessage('Server is not responding'));
                    }, 1000);

                    mSocket.onclose = () => {
                        reject(errorWithMessage('Connection to server was lost'));
                    };
                    mReadyCallback = () => {
                        clearTimeout(timeout);
                        resolve();
                    };
                });

                if (mPhase == kPhase_Finished) {
                    mStatus = kStatus_Finished;
                    try {
                        game.onFinish && game.onFinish(mScoreA, mScoreB);
                    } catch {}
                    try {
                        mSocket.close();
                    } catch {}
                } else {
                    mSocket.onclose = onSocketClose;
                    addEventListener('keyup', onKeyUp);
                    addEventListener('keydown', onKeyDown);
                    requestAnimationFrame(onAnimationFrame);
                }
            } catch (error) {
                mStatus = kStatus_Error;
                try {
                    if (error instanceof Error && error.withMessage === true)
                        game.onError && game.onError(error.message);
                    else
                        game.onError && game.onError('Unable to start game');
                } catch {}
            }
        }
    };

    const kPhase_Waiting = 0, kPhase_Playing = 1, kPhase_Intermission = 2, kPhase_Finished = 3;
    const kStatus_None = 0, kStatus_Loading = 1, kStatus_Running = 2, kStatus_Finished = 3, kStatus_Error = 4;
    const kWorldAspect = 4.0 / 3.0, kWorldHeight = 40.0, kWorldWidth = kWorldHeight * kWorldAspect, kPaddleHeight = 8.0;

    const kButton_PrimaryUp = 1 << 0, kButton_PrimaryDown = 1 << 1, kButton_SecondaryUp = 1 << 2, kButton_SecondaryDown = 1 << 3;
    const kButtonMap = {
        'w': kButton_PrimaryUp, 's': kButton_PrimaryDown, 'ArrowUp': kButton_PrimaryUp, 'ArrowDown': kButton_PrimaryDown,
        'o': kButton_SecondaryUp, 'l': kButton_SecondaryDown
    };

    const kScoreFont = [
        0x0e9d72e, 0x0842988, 0x1f1322e, 0x0f83a0f,
        0x0847d4c, 0x0f83c3f, 0x0e8bc2e, 0x011111f,
        0x0e8ba2e, 0x0e87a2e
    ];

    let mCanvas;
    let mContext;
    let mSocket;

    let mStatus = kStatus_None;
    let mInputState;
    let mLastInputState;
    let mReadyCallback;

    let mViewClip;
    let mViewWidth;
    let mViewHeight;
    let mViewMatrix = {b: 0.0, c: 0.0};

    let mPhase;
    let mBallX, mBallY;
    let mScoreA, mScoreB;
    let mPaddleA, mPaddleB;

    let mLastUpdateTime;
    let mNextUpdateTime;
    let mAverageUpdateDelta;
    let mLastBallX, mLastBallY;
    let mLastPaddleA, mLastPaddleB;
    let mNextBallX, mNextBallY;
    let mNextPaddleA, mNextPaddleB;

    function errorWithMessage(message) {
        const error = new Error(message);
        error.withMessage = true;
        return error;
    }

    function interpolate() {
        let time = (performance.now() - mNextUpdateTime) / mAverageUpdateDelta;
        if (time < 0.0) time = 0.0;
        if (time > 1.0) time = 1.0;

        function linear(lhs, rhs) {
            return lhs + (rhs - lhs) * time;
        }

        mBallX = linear(mLastBallX, mNextBallX);
        mBallY = linear(mLastBallY, mNextBallY);
        mPaddleA = linear(mLastPaddleA, mNextPaddleA);
        mPaddleB = linear(mLastPaddleB, mNextPaddleB);
    }

    function draw() {
        mContext.fillStyle = '#2e2e2e';
        mContext.fillRect(0, 0, mViewWidth, mViewHeight);

        mContext.save();
        mContext.setTransform(mViewMatrix);
        mContext.clip(mViewClip);

        mContext.fillStyle = 'black';
        mContext.fillRect(-kWorldWidth / 2.0, -kWorldHeight / 2.0, kWorldWidth, kWorldHeight);

        mContext.fillStyle = 'white';
        for (let y = 0; y < Math.floor(kWorldHeight / 2.0); y++) {
            if ((y % 6) === 0) {
                mContext.fillRect(-0.1, -3.0 - y - 1.0, 0.2, 1.0);
                mContext.fillRect(-0.1,  3.0 + y,       0.2, 1.0);
            }
        }

        mContext.fillRect(mBallX - 0.5, mBallY - 0.5, 1.0, 1.0);
        mContext.fillRect(-kWorldWidth / 2.0, mPaddleA - kPaddleHeight / 2.0, 1.0, kPaddleHeight);
        mContext.fillRect(kWorldWidth / 2.0 - 1.0, mPaddleB - kPaddleHeight / 2.0, 1.0, kPaddleHeight);

        if (mPhase === kPhase_Intermission || mPhase === kPhase_Finished) {
            drawNumber(mScoreA, -kWorldWidth / 2.0 + 8.0, -3.75, 1.5, false);
            drawNumber(mScoreB, kWorldWidth / 2.0 - 8.0, -3.75, 1.5, true);
        }

        mContext.restore();
    }

    function drawNumber(number, x, y, scale, anchorRight) {
        if (!Number.isInteger(number) || number < 0)
            return;
        let bitmaps = [];
        do {
            bitmaps.push(kScoreFont[number % 10]);
            number = ~~(number / 10);
        } while (number != 0);
        bitmaps.reverse();

        if (anchorRight)
            x -= (bitmaps.length * 6.0 - 1.0) * scale;
        const stepX = 6.0 * scale;
        const rectSize = scale * 1.05;

        for (let bitmap of bitmaps) {
            for (let offsetY = 0; offsetY < 5; offsetY++) {
                for (let offsetX = 0; offsetX < 5; offsetX++) {
                    if ((bitmap & 1) !== 0) {
                        mContext.fillRect(
                            x + offsetX * scale,
                            y + offsetY * scale,
                            rectSize, rectSize
                        );
                    }
                    bitmap >>= 1;
                }
            }
            x += stepX;
        }
    }

    function onAnimationFrame() {
        if (mStatus !== kStatus_Loading && mStatus !== kStatus_Running)
            return;

        if (mCanvas.clientWidth !== mViewWidth || mCanvas.clientHeight !== mViewHeight) {
            mViewWidth = mCanvas.width = mCanvas.clientWidth;
            mViewHeight = mCanvas.height = mCanvas.clientHeight;

            const viewAspect = mViewWidth / mViewHeight;
            if (viewAspect > kWorldAspect)
                mViewMatrix.a = mViewMatrix.d = mViewHeight / kWorldHeight;
            else
                mViewMatrix.a = mViewMatrix.d = mViewWidth / (kWorldHeight * kWorldAspect);
            mViewMatrix.e = mViewWidth / 2.0;
            mViewMatrix.f = mViewHeight / 2.0;

            mViewClip = new Path2D();
            mViewClip.rect(-kWorldWidth / 2.0, -kWorldHeight / 2.0, kWorldWidth, kWorldHeight);
        }

        interpolate();
        draw();

        if (mStatus === kStatus_Loading) {
            mStatus = kStatus_Running;
            try {
                game.onRunning && game.onRunning();
            } catch {}
        }
        if (mStatus === kStatus_Running)
            requestAnimationFrame(onAnimationFrame);
    }

    function onKey(event, isDown) {
        const mask = kButtonMap[event.key];
        if (mask === undefined)
            return;
        event.preventDefault();
        if (isDown)
            mInputState |= mask;
        else
            mInputState &= ~mask;
    }
    const onKeyUp = event => onKey(event, false);
    const onKeyDown = event => onKey(event, true);

    function onSocketMessage(event) {
        const view = new DataView(event.data);
        const flags = view.getUint8(0);

        mLastBallX = mNextBallX;
        mLastBallY = mNextBallY;
        mLastPaddleA = mNextPaddleA;
        mLastPaddleB = mNextPaddleB;
        mLastUpdateTime = mNextUpdateTime;
        mNextUpdateTime = performance.now();

        for (let offset = 1, bit = 0; bit < 8; bit++) {
            if ((flags & (1 << bit)) === 0)
                continue;
            switch (bit) {
                case 0: mPhase = view.getUint8(offset++); break;
                case 1:
                    mNextBallX = view.getFloat32(offset + 0, true);
                    mNextBallY = view.getFloat32(offset + 4, true);
                    offset += 8;
                    break;
                case 2: mScoreA = view.getUint8(offset++); break;
                case 3: mScoreB = view.getUint8(offset++); break;
                case 4:
                    mNextPaddleA = view.getFloat32(offset, true);
                    offset += 4;
                    break;
                case 5:
                    mNextPaddleB = view.getFloat32(offset, true);
                    offset += 4;
                    break;
            }
        }

        if (flags & (1 << 6)) {
            mLastBallX = mNextBallX;
            mLastBallY = mNextBallY;
        }

        if (mLastUpdateTime !== null && mNextUpdateTime !== null) {
            const updateDelta = mNextUpdateTime - mLastUpdateTime;
            if (mAverageUpdateDelta !== null)
                mAverageUpdateDelta = (mAverageUpdateDelta + updateDelta) / 2.0;
            else {
                mAverageUpdateDelta = updateDelta;
                if (mReadyCallback !== null) {
                    mReadyCallback();
                    mReadyCallback = null;
                }
            }
        }

        if (mInputState !== mLastInputState) {
            mSocket.send(new Uint8Array([mInputState]));
            mLastInputState = mInputState;
        }

        if (mStatus === kStatus_Running && mPhase === kPhase_Finished) {
            try {
                mSocket.close();
            } catch {}
            removeEventListener('keyup', onKeyUp);
            removeEventListener('keydown', onKeyDown);

            mStatus = kStatus_Finished;
            try {
                game.onFinish && game.onFinish(mScoreA, mScoreB);
            } catch {}
        }
    }

    function onSocketClose() {
        if (mStatus !== kStatus_Loading && mStatus !== kStatus_Running)
            return;
        removeEventListener('keyup', onKeyUp);
        removeEventListener('keydown', onKeyDown);
        mStatus = kStatus_Error;
        try {
            game.onError && game.onError('Connection to server was lost');
        } catch {}
    }

    return game;
})();
