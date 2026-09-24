# Host builds of the firmware cores and their unit tests.
#   make -C fw test          build and run every host test
#   make -C fw test_gpu      one test
# Output (binaries, rendered frames) goes to build/fw.

OUT     := ../build/fw
CC      ?= cc
CFLAGS  ?= -std=c11 -D_GNU_SOURCE -O2 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all
INC     := -Icommon -Igpu/core -Iio/core -Iwifi/core -Iwifi/host -Isysctl/core -Istorage/core -Istorage/host -Ithird_party/fatfs -Itest

COMMON  := common/cardproto.c common/font8x8_cp437.c
TESTS   := test_cardproto test_gpu test_iocard test_wifi test_sysctl

.PHONY: test $(TESTS) test_storage
test: $(TESTS) test_storage

$(OUT):
	mkdir -p $(OUT)

$(OUT)/test_cardproto: test/test_cardproto.c $(COMMON) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^
$(OUT)/test_gpu: test/test_gpu.c gpu/core/gpu.c $(COMMON) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^

$(OUT)/test_iocard: test/test_iocard.c io/core/iocard.c $(COMMON) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^

$(OUT)/test_wifi: test/test_wifi.c wifi/core/wifi.c wifi/host/netposix.c $(COMMON) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^

# STO-001/002: the storage card core on FatFs over disk images, then the
# images against a PC's FAT reader (tools/fatcheck.py: pyfatfs and fsck.fat)
STORAGE := storage/core/storage.c storage/core/diskio.c storage/host/imgdisk.c third_party/fatfs/ff.c
$(OUT)/test_storage: test/test_storage.c $(STORAGE) $(COMMON) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^
test_storage: $(OUT)/test_storage
	python3 ../tools/fatcheck.py mkimg $(OUT)/storage_pc.img
	rm -rf $(OUT)/storage_expect
	OUT=$(OUT) $(OUT)/test_storage $(OUT)/storage_pc.img
	python3 ../tools/fatcheck.py check $(OUT)/storage_card.img $(OUT)/storage_expect --absent GONE.TXT OLD.TXT
	python3 ../tools/fatcheck.py check $(OUT)/storage_pc.img --absent DELME.TXT --size CARD.DAT=3000 PC.TXT=1120 EMPTY.TXT=0

SYSCTL  := $(wildcard sysctl/core/*.c)
$(OUT)/test_sysctl: test/test_sysctl.c test/sysmachine.c test/sysmodels.c test/swdtarget.c $(SYSCTL) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^

# IOC-002: recordings of real keyboards (tools/kbdrecord.py) through the IO core
$(OUT)/test_recorded: test/test_recorded.c io/core/iocard.c $(COMMON) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^
test_recorded: $(OUT)/test_recorded
	cd .. && build/fw/test_recorded
.PHONY: test_recorded

# cupc8.py's stand-in for the system card: the sysctl core on the model machine
$(OUT)/sysctl_sim: test/sysctl_sim.c test/sysmachine.c test/sysmodels.c test/swdtarget.c $(SYSCTL) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^
sysctl_sim: $(OUT)/sysctl_sim
.PHONY: sysctl_sim

# the golden frames for the emulated graphics card tests (test/emu/test_gpu.mjs)
$(OUT)/gpu_golden: test/gpu_golden.c gpu/core/gpu.c $(COMMON) | $(OUT)
	$(CC) $(CFLAGS) $(INC) -o $@ $^
gpu_golden: $(OUT)/gpu_golden
.PHONY: gpu_golden

$(TESTS): %: $(OUT)/%
	OUT=$(OUT) $(OUT)/$@
