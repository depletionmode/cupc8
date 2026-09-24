// Port of rp2040js src/utils/logging.ts
#include "logging.h"

#include <cstdio>
#include <stdexcept>

#include "time.h"

namespace rp2040js {

ConsoleLogger::ConsoleLogger(LogLevel currentLogLevel, bool throwOnError)
    : currentLogLevel(currentLogLevel), throwOnError(throwOnError) {}

bool ConsoleLogger::aboveLogLevel(LogLevel logLevel) const {
  return logLevel >= currentLogLevel ? true : false;
}

std::string ConsoleLogger::formatMessage(const std::string &componentName,
                                         const std::string &message) const {
  const std::string currentTime = formatTime();
  return currentTime + " [" + componentName + "] " + message;
}

void ConsoleLogger::debug(const std::string &componetName, const std::string &message) {
  if (aboveLogLevel(LogLevel::Debug)) {
    std::fprintf(stderr, "%s\n", formatMessage(componetName, message).c_str());
  }
}

void ConsoleLogger::warn(const std::string &componetName, const std::string &message) {
  if (aboveLogLevel(LogLevel::Warn)) {
    std::fprintf(stderr, "%s\n", formatMessage(componetName, message).c_str());
  }
}

void ConsoleLogger::error(const std::string &componentName, const std::string &message) {
  if (aboveLogLevel(LogLevel::Error)) {
    std::fprintf(stderr, "%s\n", formatMessage(componentName, message).c_str());
    if (throwOnError) {
      throw std::runtime_error("[" + componentName + "] " + message);
    }
  }
}

void ConsoleLogger::info(const std::string &componentName, const std::string &message) {
  if (aboveLogLevel(LogLevel::Info)) {
    std::fprintf(stderr, "%s\n", formatMessage(componentName, message).c_str());
  }
}

}  // namespace rp2040js
