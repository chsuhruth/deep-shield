package com.deepshield.audio

import android.util.Log

/**
 * JNI Bridge to the native C++ Oboe / AAudio 16kHz PCM DSP engine.
 * Computes real-time FFT spectrograms targeting acoustic resonance in the 1.2 kHz - 3.5 kHz
 * speaker chamber band to differentiate authentic merchant soundboxes from smartphone speaker replays.
 */
class AudioRecorder {

    interface AcousticListener {
        fun onAcousticUpdate(resonanceScore: Float, isReplayDetected: Boolean)
    }

    private var listener: AcousticListener? = null
    private var isRecording = false

    companion object {
        private const val TAG = "DeepShield_AudioRecorder"

        init {
            try {
                System.loadLibrary("audio_processor")
                Log.i(TAG, "Successfully loaded native libaudio_processor.so")
            } catch (e: UnsatisfiedLinkError) {
                Log.e(TAG, "Failed to load native library audio_processor: ${e.message}")
            }
        }
    }

    // Native JNI functions
    private external fun nativeInit(): Boolean
    private external fun nativeStart(): Boolean
    private external fun nativeStop()
    private external fun nativeGetResonanceScore(): Float
    private external fun nativeIsReplayDetected(): Boolean
    private external fun nativeDestroy()

    fun initialize(listener: AcousticListener): Boolean {
        this.listener = listener
        return try {
            nativeInit()
        } catch (e: Exception) {
            Log.e(TAG, "Error initializing native audio: ${e.message}", e)
            false
        }
    }

    fun startListening(): Boolean {
        if (isRecording) return true
        return try {
            val started = nativeStart()
            if (started) {
                isRecording = true
                Log.i(TAG, "Acoustic verification stream started")
            }
            started
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start native audio stream: ${e.message}", e)
            false
        }
    }

    fun stopListening() {
        if (!isRecording) return
        try {
            nativeStop()
            isRecording = false
            Log.i(TAG, "Acoustic verification stream stopped")
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping native audio: ${e.message}", e)
        }
    }

    fun release() {
        stopListening()
        try {
            nativeDestroy()
            listener = null
        } catch (e: Exception) {
            Log.e(TAG, "Error destroying native audio resources: ${e.message}", e)
        }
    }

    fun getResonanceScore(): Float {
        return try {
            nativeGetResonanceScore()
        } catch (e: Exception) {
            0.0f
        }
    }

    fun isReplayDetected(): Boolean {
        return try {
            nativeIsReplayDetected()
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Invoked directly by C++ thread via JNI callback.
     * signature: (FZ)V
     */
    @androidx.annotation.Keep
    fun onAcousticAnalysisResult(score: Float, isReplay: Boolean) {
        listener?.onAcousticUpdate(score, isReplay)
    }
}
