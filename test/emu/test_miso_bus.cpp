#include "miso_bus.h"
#include <cassert>
#include <iostream>
int main() {
  // Passive bias changes idle only; every actively transmitted bit survives.
  for (uint8_t idle : {0,1}) for (uint8_t bit : {0,1}) {
    MisoBus bus(idle); bus.drive(true,bit); assert(bus.level()==bit);
  }
  // Disabled buffers cannot hold the bus high or low.
  MisoBus fitted(0); fitted.drive(false,1); fitted.drive(false,0); assert(fitted.level()==0);
  MisoBus none(1); assert(none.level()==1);
  // Arbitrary bytes, including high bits, are not masked by passive low.
  for (uint8_t byte : {0x00,0xff,0xa5,0x5a}) {
    unsigned observed=0;
    for (int bit=7;bit>=0;--bit) { MisoBus bus(0); bus.drive(true,(byte>>bit)&1); observed=(observed<<1)|bus.level(); }
    assert(observed==byte);
  }
  // Opposing drivers and two identical drivers are distinct wiring faults.
  MisoBus opposing(0); opposing.drive(true,0);opposing.drive(true,1);
  assert(opposing.multipleDrivers()&&opposing.conflictingDrivers());
  bool caught=false;try { opposing.level(); } catch(const std::runtime_error&) {caught=true;}assert(caught);
  MisoBus duplicate(0);duplicate.drive(true,1);duplicate.drive(true,1);
  assert(duplicate.multipleDrivers()&&!duplicate.conflictingDrivers());
  caught=false;try {duplicate.level();}catch(const std::runtime_error&){caught=true;}assert(caught);
  std::cout << "MISO passive/active/OE/byte/contention checks passed\n";
}
