// Port of rp2040js src/utils/fifo.ts (with the cupc8 dual-core patch: resize()).
#pragma once

#include <cstdint>
#include <vector>

namespace rp2040js {

class FIFO {
 public:
  std::vector<uint32_t> buffer;

  explicit FIFO(uint32_t size);

  uint32_t size() const { return static_cast<uint32_t>(buffer.size()); }
  uint32_t itemCount() const { return used; }

  void push(uint32_t value);
  uint32_t pull();
  uint32_t peek() const;
  void reset();

  /** New depth (PIO FIFO join); empties the FIFO */
  void resize(uint32_t size);

  bool empty() const { return used == 0; }
  bool full() const { return used == buffer.size(); }
  std::vector<uint32_t> items() const;

 private:
  uint32_t start = 0;
  uint32_t used = 0;
};

}  // namespace rp2040js
