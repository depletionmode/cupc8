#!/usr/bin/env python3
"""Functional fitted monitor: actual native equations, fault/reset/recovery mutations.

No claim of guaranteed analogue propagation or RP2040 whole-chip RUN response.
"""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
PROGRAM=r'''
#include "emu/machine/resetmonitor.h"
#include <cassert>
#include <cmath>
#include <iostream>
using machine::ResetMonitor;
static ResetMonitor settled(){ResetMonitor m;m.update(0,3.3,1.2,3.3);m.update(2500000,3.3,1.2,3.3);m.update(562500000,3.3,1.2,3.3);assert(m.state.por);return m;}
int main(){
 // Independent resistor-series ladder voltages (hand-calculated nominal).
 auto m=settled();assert(std::abs(m.state.tap33-1.632747455)<1e-8);
 assert(std::abs(m.state.tap12-1.156336725)<1e-8);
 assert(m.state.vref==2.5&&m.state.mr>3.2);
 for(bool high:m.state.slotHigh)assert(high);
 // Reference/cold baseline is NOT silently settled after twelve clocks.
 ResetMonitor cold;cold.update(0,3.3,1.2,3.3);assert(!cold.state.por);
 cold.update(1000,3.3,1.2,3.3);assert(cold.state.vref==0&&!cold.state.por);
 // Both rail faults assert MR and every powered open-drain clamp.
 for(int rail=0;rail<2;rail++){
  auto x=settled();auto &s=x.update(563000000,rail==0?3.1:3.3,rail==1?1.1:1.2,3.3);
  assert(!s.por);for(bool high:s.slotHigh)assert(!high);
 }
 // 3V3 monitor also acts ABOVE the independent MAX811 3.15V floor.
 auto rail33=settled();rail33.update(563000000,3.17,1.2,3.3);
 assert(rail33.state.vref==2.5&&rail33.state.out33==.05&&rail33.state.mr<.25*3.17&&!rail33.state.por);
 auto diode33=settled();diode33.config.diodeConnected[0]=false;
 diode33.update(563000000,3.17,1.2,3.3);assert(diode33.state.por);
 // Low core alone pulls MR low through correct common-anode diode.
 m.update(563000000,3.3,1.1,3.3);assert(m.state.out12==.05);
 assert(m.state.mr<.25*3.3&&!m.state.por);
 // Healthy restoration must wait 560ms continuously; a second fault restarts.
 m.update(564000000,3.3,1.2,3.3);assert(!m.state.por);
 m.update(1123999999,3.3,1.2,3.3);assert(!m.state.por);
 m.update(1124000000,3.3,1.2,3.3);assert(m.state.por);
 m.update(1125000000,3.3,1.2,3.3,true);assert(!m.state.por);
 m.update(1126000000,3.3,1.2,3.3);m.update(1685999999,3.3,1.2,3.3);assert(!m.state.por);
 m.update(1686000000,3.3,1.2,3.3);assert(m.state.por);
 // The fitted positive feedback gives history at the same rail voltage.
 auto up=settled(),down=settled();down.update(563000000,3.3,1.1,3.3);
 up.update(563000000,3.3,1.156,3.3);down.update(564000000,3.3,1.156,3.3);
 assert(up.state.out12>3 && down.state.out12<.1);
 // Removing only 1V2 diode loses 1V2 fault reset: meaningful counterexample.
 auto open=settled();open.config.diodeConnected[1]=false;
 open.update(563000000,3.3,1.1,3.3);assert(open.state.por);
 // Open U19 output affects exactly its own slot; low standby gives Ioff.
 auto slot=settled();slot.config.clampConnected[2]=false;
 slot.update(563000000,3.3,1.1,3.3);
 for(int i=0;i<6;i++)assert(slot.state.slotHigh[i]==(i==2));
 slot.update(564000000,3.3,1.1,0);for(bool high:slot.state.slotHigh)assert(high);
 // Reference zero and lost feedback are detected by functional behavior.
 auto bad=settled();bad.config.reference=3.;bad.update(563000000,3.3,1.2,3.3);assert(!bad.state.por);
 auto nofeedback=settled();nofeedback.config.feedback12=1e99;
 nofeedback.update(563000000,3.3,1.156,3.3);assert(nofeedback.state.out12<.1);
 bool refused=false;try{m.update(1,3.3,1.2,3.3);}catch(const std::invalid_argument&){refused=true;}assert(refused);
 std::cout<<"native reset monitor: ladder, startup, both faults, MR, exact timeout, retrigger, hysteresis, diode/output/reference/feedback mutations, Ioff and bad time PASS\n";
}
'''
def main():
 with tempfile.TemporaryDirectory(prefix='cupc8-monitor-test-') as tmp:
  src=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';src.write_text(PROGRAM)
  subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT),str(src),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()
