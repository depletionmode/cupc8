# Host builds of the firmware cores and their unit tests.
#   make -C fw test          build and run every host test
#   make -C fw test_gpu      one test
# Output (binaries, rendered frames) goes to build/fw.

OUT     := ../build/fw
CC      ?= cc
CFLAGS  ?= -std=c11 -D_GNU_SOURCE -O2 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all
INC     := -Icommon -Igpu/core -Iio/core -Iwifi/core -Iwifi/host -Itest

COMMON  := common/cardproto.c common/font8x8_cp437.c
TESTS   := test_cardproto test_gpu test_iocard test_wifi

.PHONY: test $(TESTS)
test: $(TESTS)

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

$(TESTS): %: $(OUT)/%
	OUT=$(OUT) $(OUT)/$@
