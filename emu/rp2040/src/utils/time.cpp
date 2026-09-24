// Port of rp2040js src/utils/time.ts
#include "time.h"

#include <chrono>
#include <cmath>

namespace rp2040js {

double getCurrentMicroseconds() {
  using namespace std::chrono;
  const double nowMs =
      duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
  return std::floor(nowMs * 1000);
}

static std::string leftPad(std::string value, size_t minLength, char padChar = ' ') {
  if (value.length() < minLength) {
    value = padChar + value;
  }
  return value;
}

static std::string rightPad(std::string value, size_t minLength, char padChar = ' ') {
  if (value.length() < minLength) {
    value += padChar;
  }
  return value;
}

std::string formatTime() {
  using namespace std::chrono;
  const auto now = system_clock::now();
  const std::time_t t = system_clock::to_time_t(now);
  std::tm date{};
  localtime_r(&t, &date);
  const long ms = static_cast<long>(duration_cast<milliseconds>(now.time_since_epoch()).count() % 1000);
  const std::string hours = leftPad(std::to_string(date.tm_hour), 2, '0');
  const std::string minutes = leftPad(std::to_string(date.tm_min), 2, '0');
  const std::string seconds = leftPad(std::to_string(date.tm_sec), 2, '0');
  const std::string milliseconds = rightPad(std::to_string(ms), 3);
  return hours + ":" + minutes + ":" + seconds + "." + milliseconds;
}

}  // namespace rp2040js
