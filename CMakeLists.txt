cmake_minimum_required(VERSION 3.22.1)

project("deepshield_native" LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Optimization flags for ARM Neon and fast floating point calculations
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -ffast-math -Wall -Wextra -pthread")

# If Oboe prefab package is available in Gradle, link oboe::oboe; otherwise fallback to native aaudio
find_package(oboe QUIET CONFIG)

add_library(
    audio_processor
    SHARED
    audio_processor.cpp
)

target_include_directories(
    audio_processor
    PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
)

if (oboe_FOUND)
    target_link_libraries(
        audio_processor
        oboe::oboe
        log
        aaudio
        OpenSLES
    )
else()
    target_link_libraries(
        audio_processor
        log
        aaudio
        OpenSLES
    )
endif()
