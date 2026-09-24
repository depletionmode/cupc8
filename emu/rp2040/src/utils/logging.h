// Port of rp2040js src/utils/logging.ts
#pragma once

#include <string>

namespace rp2040js {

class Logger {
 public:
  virtual ~Logger() = default;
  virtual void debug(const std::string &componentName, const std::string &message) = 0;
  virtual void warn(const std::string &componentName, const std::string &message) = 0;
  virtual void error(const std::string &componentName, const std::string &message) = 0;
  virtual void info(const std::string &componentName, const std::string &message) = 0;
};

enum class LogLevel {
  Debug,
  Info,
  Warn,
  Error,
};

/**
 * Prints "HH:MM:SS.mmm [component] message" to stderr (all levels: node sends
 * debug/info to stdout, but stdout is the UART here). With throwOnError,
 * error() throws std::runtime_error("[component] message") after printing, as
 * the TS throws Error: it is fatal to the run, not control flow.
 */
class ConsoleLogger : public Logger {
 public:
  LogLevel currentLogLevel;

  explicit ConsoleLogger(LogLevel currentLogLevel, bool throwOnError = true);

  void debug(const std::string &componetName, const std::string &message) override;
  void warn(const std::string &componetName, const std::string &message) override;
  void error(const std::string &componentName, const std::string &message) override;
  void info(const std::string &componentName, const std::string &message) override;

 private:
  bool throwOnError;

  bool aboveLogLevel(LogLevel logLevel) const;
  std::string formatMessage(const std::string &componentName, const std::string &message) const;
};

}  // namespace rp2040js
