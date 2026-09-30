// Functional electrical model of the fitted main-board reset qualifier.
// Values/pin topology must be bound independently by gen_top. This models DC
// KCL, hysteresis, diode clamps, and MAX811's maximum specified recovery time.
// It does not certify unspecified maximum OPA376/MR propagation or reference
// settling; those remain physical qualification obligations.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace machine {
struct ResetMonitor {
  struct Config {
    double ladder1=7500, ladder2=4120, ladder3=10000;
    double sense33=9530, bottom33=10000, feedback33=6800000;
    double sense12=1000, feedback12=2700000;
    double reference=2.5, swing=.05, diodeDrop=.42;
    double supervisorThreshold=3.15, recoveryNs=560000000;
    double referenceReadyNs=2500000; // deterministic functional startup point
    std::array<bool,2> diodeConnected{{true,true}};
    std::array<bool,6> clampConnected{{true,true,true,true,true,true}};
  } config;
  struct State {
    double vref=0, tap33=0, tap12=0, plus33=0, plus12=0;
    double out33=0, out12=0, mr=0;
    bool por=false;
    std::array<bool,6> slotHigh{{false,false,false,false,false,false}};
  } state;
  bool high33=false, high12=false;
  double poweredSince=-1, healthySince=-1, lastNs=-1;

  const State &update(double ns, double v33, double v12, double standby,
                      bool externalMrLow=false) {
    if (!std::isfinite(ns)||!std::isfinite(v33)||!std::isfinite(v12)||
        !std::isfinite(standby)||ns<0||v33<0||v12<0||standby<0||ns<lastNs)
      throw std::invalid_argument("reset monitor: invalid voltage/time");
    if (standby>0 && standby<1.65)
      throw std::invalid_argument("reset monitor: unsupported partially powered U19");
    lastNs=ns;
    const bool powered=v33>=config.supervisorThreshold;
    if (!powered) { poweredSince=-1; high33=high12=false; }
    else if (poweredSince<0) poweredSince=ns;
    const bool referenceReady=powered && ns-poweredSince>=config.referenceReadyNs;
    state.vref=referenceReady?config.reference:0;
    // Unloaded resistor ladder KCL, nominal functional operating point.
    const double current=state.vref/(config.ladder1+config.ladder2+config.ladder3);
    state.tap12=current*config.ladder3;
    state.tap33=current*(config.ladder2+config.ladder3);
    const double lo=std::min(config.swing,v33),hi=std::max(0.,v33-config.swing);
    auto plus33=[&](bool high) {
      return (v33/config.sense33+(high?hi:lo)/config.feedback33)/
        (1/config.sense33+1/config.bottom33+1/config.feedback33);
    };
    auto plus12=[&](bool high) {
      return (v12/config.sense12+(high?hi:lo)/config.feedback12)/
        (1/config.sense12+1/config.feedback12);
    };
    if(referenceReady) {
      // Positive feedback preserves the previous state between its two trips.
      high33=plus33(high33)>state.tap33;
      high12=plus12(high12)>state.tap12;
    } else high33=high12=false;
    state.plus33=plus33(high33); state.plus12=plus12(high12);
    state.out33=high33?hi:lo; state.out12=high12?hi:lo;
    state.mr=v33;
    if(config.diodeConnected[0]) state.mr=std::min(state.mr,state.out33+config.diodeDrop);
    if(config.diodeConnected[1]) state.mr=std::min(state.mr,state.out12+config.diodeDrop);
    if(externalMrLow) state.mr=0;
    const bool healthy=powered && state.mr>.25*v33;
    if(!healthy) healthySince=-1;
    else if(healthySince<0) healthySince=ns;
    state.por=healthy && ns-healthySince>=config.recoveryNs;
    // LVC07 Ioff means unpowered standby cannot assert a sink; each line then
    // reads its card-side pull-up. Powered low A sinks Y; high A releases Y.
    for(size_t i=0;i<6;i++) state.slotHigh[i]=
      standby==0 || !config.clampConnected[i] || state.por;
    return state;
  }
};
} // namespace machine
