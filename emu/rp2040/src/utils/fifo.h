// Port of rp2040js src/utils/fifo.ts (with the cupc8 dual-core patch: resize()).
#pragma once

#include <cstdint>
#include <functional>
#include <vector>

namespace rp2040js {

class FIFO {
 public:
  std::vector<uint32_t> buffer;

  /** Test-harness hook, not in rp2040js: called with every value pull()
   * returns (what test/emu/tmds.mjs gets by wrapping fifo.pull). */
  std::function<void(uint32_t)> onPull;
  /** Not in rp2040js: set when onPull only records (it neither reads nor
   * changes the chip), so that the PIO fast path may call it from a lazy
   * cycle (RPPIO::sync). */
  bool onPullRecordsOnly = false;

  explicit FIFO(uint32_t size);

  uint32_t size() const { return length; }
  uint32_t itemCount() const { return used; }

  void push(uint32_t value);
  uint32_t pull();
  uint32_t peek() const;
  void reset();

  /** New depth (PIO FIFO join); empties the FIFO */
  void resize(uint32_t size);

  bool empty() const { return used == 0; }
  bool full() const { return used == length; }
  std::vector<uint32_t> items() const;

 private:
  uint32_t start = 0;
  uint32_t used = 0;
  uint32_t length;  // buffer.size()
};

}  // namespace rp2040js
