set(FW ${CMAKE_CURRENT_LIST_DIR}/../../../..)
idf_component_register(
	SRCS main.c frames.c netesp.c transport_spi.c transport_uart.c
	     ${FW}/wifi/core/wifi.c ${FW}/common/cardproto.c
	INCLUDE_DIRS . ${FW}/wifi ${FW}/wifi/core ${FW}/common
	PRIV_REQUIRES esp_wifi esp_eth esp_netif esp-tls esp_driver_spi esp_driver_gpio
	              esp_driver_uart nvs_flash mbedtls lwip)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -Wno-unused-parameter)
