#include <jni.h>
#include <android/log.h>
#include <aaudio/AAudio.h>
#include <cmath>
#include <vector>
#include <complex>
#include <atomic>
#include <thread>
#include <mutex>
#include <memory>
#include <algorithm>

#define TAG "DeepShield_NativeAudio"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, TAG, __VA_ARGS__)

namespace deepshield {

constexpr int SAMPLE_RATE = 16000;
constexpr int FFT_SIZE = 1024; // 64ms window @ 16kHz
constexpr int HOP_SIZE = 256;  // 16ms hop (sub-20ms resolution)
constexpr float PI_CONST = 3.14159265358979323846f;

// Target merchant soundbox chamber resonance frequencies: 1200 Hz - 3500 Hz
constexpr float RESONANCE_MIN_HZ = 1200.0f;
constexpr float RESONANCE_MAX_HZ = 3500.0f;

// Pre-computed FFT index bounds
constexpr int BIN_MIN = static_cast<int>((RESONANCE_MIN_HZ * FFT_SIZE) / SAMPLE_RATE);
constexpr int BIN_MAX = static_cast<int>((RESONANCE_MAX_HZ * FFT_SIZE) / SAMPLE_RATE);

// Fast Cooley-Tukey Radix-2 In-place FFT
void performFFT(std::vector<std::complex<float>>& data) {
    const size_t n = data.size();
    if (n <= 1) return;

    // Bit-reversal permutation
    for (size_t i = 1, j = 0; i < n; ++i) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            std::swap(data[i], data[j]);
        }
    }

    // Butterfly computation
    for (size_t len = 2; len <= n; len <<= 1) {
        float angle = -2.0f * PI_CONST / static_cast<float>(len);
        std::complex<float> wlen(std::cos(angle), std::sin(angle));
        for (size_t i = 0; i < n; i += len) {
            std::complex<float> w(1.0f, 0.0f);
            for (size_t j = 0; j < len / 2; ++j) {
                std::complex<float> u = data[i + j];
                std::complex<float> v = data[i + j + len / 2] * w;
                data[i + j] = u + v;
                data[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
}

class AudioProcessor {
public:
    AudioProcessor()
        : isRunning(false),
          resonanceScore(0.0f),
          isReplayFlagged(false),
          aaudioStream(nullptr),
          jvm(nullptr),
          callbackObj(nullptr),
          callbackMethodId(nullptr) {
        // Pre-compute Hann window
        hannWindow.resize(FFT_SIZE);
        for (int i = 0; i < FFT_SIZE; ++i) {
            hannWindow[i] = 0.5f * (1.0f - std::cos(2.0f * PI_CONST * i / (FFT_SIZE - 1)));
        }
        pcmBuffer.reserve(FFT_SIZE * 2);
    }

    ~AudioProcessor() {
        stop();
        cleanupJNI();
    }

    void setJNICallback(JavaVM* vm, jobject obj) {
        std::lock_guard<std::mutex> lock(callbackMutex);
        jvm = vm;
        JNIEnv* env = nullptr;
        if (jvm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) == JNI_OK) {
            if (callbackObj) {
                env->DeleteGlobalRef(callbackObj);
            }
            callbackObj = env->NewGlobalRef(obj);
            jclass clazz = env->GetObjectClass(callbackObj);
            callbackMethodId = env->GetMethodID(clazz, "onAcousticAnalysisResult", "(FZ)V");
        }
    }

    bool start() {
        if (isRunning.load()) {
            return true;
        }

        AAudioStreamBuilder* builder = nullptr;
        aaudio_result_t result = AAudio_createStreamBuilder(&builder);
        if (result != AAUDIO_OK) {
            LOGE("Failed to create AAudioStreamBuilder: %s", AAudio_convertResultToText(result));
            return false;
        }

        AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_INPUT);
        AAudioStreamBuilder_setSampleRate(builder, SAMPLE_RATE);
        AAudioStreamBuilder_setChannelCount(builder, 1);
        AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_PCM_FLOAT);
        AAudioStreamBuilder_setPerformanceMode(builder, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY);
        AAudioStreamBuilder_setSharingMode(builder, AAUDIO_SHARING_MODE_SHARED);
        AAudioStreamBuilder_setDataCallback(builder, dataCallback, this);

        result = AAudioStreamBuilder_openStream(builder, &aaudioStream);
        AAudioStreamBuilder_delete(builder);

        if (result != AAUDIO_OK) {
            LOGE("Failed to open AAudio stream: %s", AAudio_convertResultToText(result));
            return false;
        }

        result = AAudioStream_requestStart(aaudioStream);
        if (result != AAUDIO_OK) {
            LOGE("Failed to start AAudio stream: %s", AAudio_convertResultToText(result));
            AAudioStream_close(aaudioStream);
            aaudioStream = nullptr;
            return false;
        }

        isRunning.store(true);
        LOGI("AAudio stream started successfully at %d Hz low-latency", SAMPLE_RATE);
        return true;
    }

    void stop() {
        if (!isRunning.exchange(false)) {
            return;
        }

        if (aaudioStream != nullptr) {
            AAudioStream_requestStop(aaudioStream);
            AAudioStream_close(aaudioStream);
            aaudioStream = nullptr;
        }
        LOGI("AudioProcessor stopped");
    }

    float getResonanceScore() const {
        return resonanceScore.load();
    }

    bool isReplayDetected() const {
        return isReplayFlagged.load();
    }

    // Process raw PCM samples and run acoustic chamber resonance test
    void processAudioSamples(const float* samples, int numSamples) {
        std::lock_guard<std::mutex> lock(bufferMutex);
        pcmBuffer.insert(pcmBuffer.end(), samples, samples + numSamples);

        while (pcmBuffer.size() >= FFT_SIZE) {
            std::vector<std::complex<float>> fftData(FFT_SIZE);
            for (int i = 0; i < FFT_SIZE; ++i) {
                fftData[i] = std::complex<float>(pcmBuffer[i] * hannWindow[i], 0.0f);
            }

            performFFT(fftData);

            // Compute power spectral density
            float totalEnergy = 1e-7f;
            float resonanceEnergy = 0.0f;
            float highFreqDistortion = 0.0f;

            for (int k = 1; k < FFT_SIZE / 2; ++k) {
                float magnitude = std::abs(fftData[k]);
                float power = magnitude * magnitude;
                totalEnergy += power;

                if (k >= BIN_MIN && k <= BIN_MAX) {
                    resonanceEnergy += power;
                }
                // High frequency band (> 5kHz) typical in phone loudspeaker clipping
                if (k > static_cast<int>((5000.0f * FFT_SIZE) / SAMPLE_RATE)) {
                    highFreqDistortion += power;
                }
            }

            // Resonance chamber ratio: Physical merchant soundboxes concentrate >55% energy in [1.2kHz - 3.5kHz]
            float ratio = resonanceEnergy / totalEnergy;
            float distortionRatio = highFreqDistortion / totalEnergy;

            // Attack transient sharpness metric:
            float peakAmp = 0.0f;
            for (int i = 0; i < FFT_SIZE; ++i) {
                peakAmp = std::max(peakAmp, std::abs(pcmBuffer[i]));
            }

            // Flag replay attack if energy ratio is deficient OR loudspeaker clipping exceeds threshold
            // A replay over smartphone speaker exhibits diminished 1.2-3.5kHz box resonance (ratio < 0.38)
            // or high non-linear distortion (distortionRatio > 0.30)
            bool replayFlag = (ratio < 0.38f && totalEnergy > 1e-3f) || (distortionRatio > 0.28f);

            resonanceScore.store(ratio);
            isReplayFlagged.store(replayFlag);

            notifyJNI(ratio, replayFlag);

            // Advance by HOP_SIZE
            pcmBuffer.erase(pcmBuffer.begin(), pcmBuffer.begin() + HOP_SIZE);
        }
    }

private:
    static aaudio_data_callback_result_t dataCallback(
        AAudioStream* /*stream*/,
        void* userData,
        void* audioData,
        int32_t numFrames) {
        auto* processor = static_cast<AudioProcessor*>(userData);
        if (processor && audioData && numFrames > 0) {
            processor->processAudioSamples(static_cast<const float*>(audioData), numFrames);
        }
        return AAUDIO_CALLBACK_RESULT_CONTINUE;
    }

    void notifyJNI(float score, bool flagged) {
        std::lock_guard<std::mutex> lock(callbackMutex);
        if (!jvm || !callbackObj || !callbackMethodId) return;

        JNIEnv* env = nullptr;
        bool attached = false;
        jint status = jvm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
        if (status == JNI_EDETACHED) {
            if (jvm->AttachCurrentThread(&env, nullptr) != JNI_OK) {
                return;
            }
            attached = true;
        }

        if (env) {
            env->CallVoidMethod(callbackObj, callbackMethodId, score, flagged);
        }

        if (attached) {
            jvm->DetachCurrentThread();
        }
    }

    void cleanupJNI() {
        std::lock_guard<std::mutex> lock(callbackMutex);
        if (jvm && callbackObj) {
            JNIEnv* env = nullptr;
            if (jvm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) == JNI_OK) {
                env->DeleteGlobalRef(callbackObj);
            }
            callbackObj = nullptr;
            callbackMethodId = nullptr;
        }
    }

    std::atomic<bool> isRunning;
    std::atomic<float> resonanceScore;
    std::atomic<bool> isReplayFlagged;

    AAudioStream* aaudioStream;
    std::vector<float> hannWindow;
    std::vector<float> pcmBuffer;
    std::mutex bufferMutex;

    JavaVM* jvm;
    jobject callbackObj;
    jmethodID callbackMethodId;
    std::mutex callbackMutex;
};

// Global singleton instance
static std::unique_ptr<AudioProcessor> g_audioProcessor = nullptr;
static std::mutex g_instanceMutex;

} // namespace deepshield

extern "C" {

JNIEXPORT jboolean JNICALL
Java_com_deepshield_audio_AudioRecorder_nativeInit(JNIEnv* env, jobject thiz) {
    std::lock_guard<std::mutex> lock(deepshield::g_instanceMutex);
    if (!deepshield::g_audioProcessor) {
        deepshield::g_audioProcessor = std::make_unique<deepshield::AudioProcessor>();
    }
    JavaVM* vm = nullptr;
    env->GetJavaVM(&vm);
    deepshield::g_audioProcessor->setJNICallback(vm, thiz);
    LOGI("nativeInit completed successfully");
    return JNI_TRUE;
}

JNIEXPORT jboolean JNICALL
Java_com_deepshield_audio_AudioRecorder_nativeStart(JNIEnv* /*env*/, jobject /*thiz*/) {
    std::lock_guard<std::mutex> lock(deepshield::g_instanceMutex);
    if (deepshield::g_audioProcessor) {
        return deepshield::g_audioProcessor->start() ? JNI_TRUE : JNI_FALSE;
    }
    return JNI_FALSE;
}

JNIEXPORT void JNICALL
Java_com_deepshield_audio_AudioRecorder_nativeStop(JNIEnv* /*env*/, jobject /*thiz*/) {
    std::lock_guard<std::mutex> lock(deepshield::g_instanceMutex);
    if (deepshield::g_audioProcessor) {
        deepshield::g_audioProcessor->stop();
    }
}

JNIEXPORT jfloat JNICALL
Java_com_deepshield_audio_AudioRecorder_nativeGetResonanceScore(JNIEnv* /*env*/, jobject /*thiz*/) {
    std::lock_guard<std::mutex> lock(deepshield::g_instanceMutex);
    if (deepshield::g_audioProcessor) {
        return deepshield::g_audioProcessor->getResonanceScore();
    }
    return 0.0f;
}

JNIEXPORT jboolean JNICALL
Java_com_deepshield_audio_AudioRecorder_nativeIsReplayDetected(JNIEnv* /*env*/, jobject /*thiz*/) {
    std::lock_guard<std::mutex> lock(deepshield::g_instanceMutex);
    if (deepshield::g_audioProcessor) {
        return deepshield::g_audioProcessor->isReplayDetected() ? JNI_TRUE : JNI_FALSE;
    }
    return JNI_FALSE;
}

JNIEXPORT void JNICALL
Java_com_deepshield_audio_AudioRecorder_nativeDestroy(JNIEnv* /*env*/, jobject /*thiz*/) {
    std::lock_guard<std::mutex> lock(deepshield::g_instanceMutex);
    if (deepshield::g_audioProcessor) {
        deepshield::g_audioProcessor->stop();
        deepshield::g_audioProcessor.reset();
        LOGI("nativeDestroy completed");
    }
}

} // extern "C"
