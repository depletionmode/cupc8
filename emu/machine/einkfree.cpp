// Genuine RP2040 FREE boundary: populate the FIFO through legal slot frames.
#define main einkcard_suite_main
#include "einkcard.cpp"
#undef main

int main(int argc, char **argv) {
  if (argc != 7) {
    std::fprintf(stderr, "usage: einkfree ELF HEAD_ADDR TAIL_ADDR GPU_ERRORS_ADDR SLOT_ERRORS_ADDR old|fixed\n");
    return 2;
  }
  auto addr=[](const char *s){return static_cast<uint32_t>(std::stoul(s,nullptr,0));};
  auto cfg=EinkPanel::config(800,480);cfg.time_scale=0.1;
  Bench b(argv[1],cfg);
  const uint32_t headAt=addr(argv[2]),tailAt=addr(argv[3]),errorsAt=addr(argv[4]),slotAt=addr(argv[5]);
  auto word=[&](uint32_t a){return b.e.mcu->readUint32(a);};
  auto waitUntil=[&](auto condition,double limit){double end=b.ns()+limit;while(!condition()&&b.ns()<end)b.e.steps(64);return condition();};
  CHECK(waitUntil([&]{return b.frame({0xff})[0]!=0xff;},200e6),"genuine firmware boots");
  // Explicit grey refresh holds execution while real panel BUSY is active.
  // No SRAM state is written: head/tail and errors are observations only.
  b.frame({0x09,3});
  CHECK(waitUntil([&]{return b.panel.m.busy_op==0x12;},5e9),"actual grey refresh holds execution");
  std::vector<uint8_t> blit(8006,7);blit[0]=0x24;blit[1]=0;blit[2]=0;blit[3]=0;blit[4]=80;blit[5]=100;
  CHECK(b.frame({0xff})[0]>=126,"FREE permits legal8006byte BLIT");
  b.frame(blit);
  CHECK(waitUntil([&]{return word(headAt)-word(tailAt)==8008;},50e6),"BLIT+two-byteheader occupies8008bytes");
  std::vector<uint8_t> prefix(118,'A');prefix[0]=0x11;prefix[1]=116;
  CHECK(b.frame({0xff})[0]>=2,"FREE permits legal118byte PUTS");
  b.frame(prefix);
  CHECK(waitUntil([&]{return word(headAt)-word(tailAt)==8128;},50e6),"legal frames leaveexact64physicalFIFO bytes");
  CHECK(b.panel.m.busy_op==0x12,"FIFO is still legitimately held by panel refresh");
  const uint32_t errors=word(errorsAt),head=word(headAt),slotErrors=word(slotAt);
  const uint8_t credit=b.frame({0xff})[0]&127;
  const bool fixed=std::string(argv[6])=="fixed";
  std::vector<uint8_t> target(64,'B');target[0]=0x11;target[1]=62;
  if (!fixed) {
    CHECK(credit==1,"originalRP statusadvertises FREE1 with64physicalbytes remaining (%u)",credit);
    b.frame(target);
    CHECK(waitUntil([&]{return word(errorsAt)>errors;},50e6),"advertisedlegal64byte PUTS is rejected for missingheader space");
    CHECK(word(headAt)==head,"rejectedframe doesnot enter FIFO");
  } else {
    CHECK(credit==0,"correctedRP statusreserves futureheader (%u)",credit);
    CHECK(waitUntil([&]{return !b.panel.m.busy_op && word(headAt)==word(tailAt);},10e9),"actual heldwork drains without deadlinechange");
    // The outgoing first byte is cached before CS. Poll until the firmware's
    // normal idle service has published the recovered credit.
    CHECK(waitUntil([&]{return (b.frame({0xff})[0]&127)>=1;},50e6),"creditrecovers afterrealdrain");
    const uint32_t beforeTarget=word(headAt);
    b.frame(target);
    CHECK(waitUntil([&]{return word(headAt)==beforeTarget+66 && word(headAt)==word(tailAt);},50e6),"legal64byte PUTS accepted/executed aftercreditsrecover");
    CHECK(word(errorsAt)==errors,"corrected credit-obeying host losesno frame");
  }
  CHECK(word(slotAt)==slotErrors,"no descriptorqueue overflow confounds FIFO boundary");
  CHECK(b.panel.m.errors==0,"controller accepted actualrefresh");
  std::printf("EINK-FREE %s:64physicalbytesleft, advertisedcredit%u, GPUerrors%u, transporterrors%u; %d checks,%d failures\n",argv[6],credit,word(errorsAt)-errors,word(slotAt)-slotErrors,checks,failures);
  return failures?1:0;
}
