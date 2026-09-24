// Port of rp2040js src/utils/time.ts
#pragma once

#include <cstdint>
#include <ctime>
#include <string>

namespace rp2040js {

/** Math.floor(performance.now() * 1000): microseconds on a monotonic clock. */
double getCurrentMicroseconds();

/**
 * formatTime(new Date()): local "HH:MM:SS.mmm". Reproduces the TS padding
 * exactly (leftPad/rightPad add at most one pad character).
 */
std::string formatTime();

}  // namespace rp2040js
