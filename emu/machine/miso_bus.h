#pragma once
#include <cstdint>
#include <stdexcept>

// Digital push-pull/OE resolution. Passive bias applies only when every
// buffer is released; it never participates as another active driver.
class MisoBus {
 public:
  explicit MisoBus(uint8_t passiveIdle) : passive_(passiveIdle & 1u) {}
  void drive(bool outputEnabled, uint8_t bit) {
    if (!outputEnabled) return;
    bit &= 1u;
    if (drivers_) {
      multiple_ = true;
      conflict_ |= (active_ != bit);
    } else active_ = bit;
    ++drivers_;
  }
  uint8_t level() const {
    if (multiple_) throw std::runtime_error(conflict_ ? "MISO conflicting active drivers" : "MISO multiple enabled drivers");
    return drivers_ ? active_ : passive_;
  }
  bool multipleDrivers() const { return multiple_; }
  bool conflictingDrivers() const { return conflict_; }
 private:
  uint8_t passive_, active_ = 0;
  unsigned drivers_ = 0;
  bool multiple_ = false, conflict_ = false;
};
