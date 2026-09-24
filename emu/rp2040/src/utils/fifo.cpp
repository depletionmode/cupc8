// Port of rp2040js src/utils/fifo.ts
#include "fifo.h"

namespace rp2040js {

FIFO::FIFO(uint32_t size) : buffer(size), length(size) {}

void FIFO::push(uint32_t value) {
  const uint32_t start = this->start, used = this->used;
  if (this->used < length) {
    // `(start + used) % length`, with start, used < length
    const uint32_t at = start + used;
    buffer[at >= length ? at - length : at] = value;
    this->used++;
  }
}

uint32_t FIFO::pull() {
  const uint32_t start = this->start, used = this->used;
  if (used) {
    this->start = start + 1 == length ? 0 : start + 1;  // `(start + 1) % length`
    this->used--;
    if (onPull) onPull(buffer[start]);
    return buffer[start];
  }
  if (onPull) onPull(0);
  return 0;
}

uint32_t FIFO::peek() const { return used ? buffer[start] : 0; }

void FIFO::reset() { used = 0; }

void FIFO::resize(uint32_t size) {
  buffer.assign(size, 0);
  length = size;
  start = 0;
  used = 0;
}

std::vector<uint32_t> FIFO::items() const {
  const uint32_t length = static_cast<uint32_t>(buffer.size());
  std::vector<uint32_t> result(used);
  for (uint32_t i = 0; i < used; i++) {
    result[i] = buffer[(start + i) % length];
  }
  return result;
}

}  // namespace rp2040js
