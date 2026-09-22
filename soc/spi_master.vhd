-- Chipset SPI master (doc/hardware/memory-map.md, SPI registers).
--
-- One shift engine shared by devices 0-7. `start` shifts one byte on device
-- `dev` with that device's CPOL/CPHA and divider. SCK half-period is `div`
-- clocks (div 0 is treated as 1), so SCK = clk / (2 × div).
--
-- CS: `hold` (the SPI_CS register, one-hot or zero) keeps a device selected
-- across bytes. A device whose hold bit is clear is selected only while its
-- byte shifts. At most one CS is ever low.
--
-- Edges k = 1..16 alternate leading (odd k) and trailing (even k).
--   CPHA=0: sample MISO on leading edges, shift MOSI on trailing edges
--           (bit 7 is on MOSI before the first edge).
--   CPHA=1: shift MOSI on leading edges except the first (bit 7 is already
--           out), sample MISO on trailing edges.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity spi_master is
	port(
		clk:	in std_logic;
		rst:	in std_logic;
		start:	in std_logic;						-- pulse: shift tx on dev
		dev:	in unsigned(2 downto 0);
		tx:		in std_logic_vector(7 downto 0);
		cpol:	in std_logic;
		cpha:	in std_logic;
		div:	in unsigned(4 downto 0);
		hold:	in std_logic_vector(7 downto 0);	-- SPI_CS per device
		busy:	out std_logic;
		done:	out std_logic;						-- pulse when rx is valid
		rx:		out std_logic_vector(7 downto 0);
		sck:	out std_logic;
		mosi:	out std_logic;
		miso:	in std_logic;
		n_cs:	out std_logic_vector(7 downto 0)
	);
end entity;

architecture rtl of spi_master is
	signal busy_r, sck_r, pha, done_r: std_logic := '0';
	signal tx_sh, rx_sh, rx_r: std_logic_vector(7 downto 0) := x"00";
	signal k: unsigned(4 downto 0) := (others => '0');		-- edges made so far
	signal cnt, half: unsigned(4 downto 0) := (others => '0');
	signal cur: unsigned(2 downto 0) := "000";
begin
	busy <= busy_r;
	done <= done_r;
	rx <= rx_r;
	sck <= sck_r;
	mosi <= tx_sh(7);

	cs: process(busy_r, cur, hold)
	begin
		n_cs <= (others => '1');
		if busy_r = '1' then
			n_cs(to_integer(cur)) <= '0';
		else
			for i in 0 to 7 loop
				if hold(i) = '1' then
					n_cs <= (others => '1');
					n_cs(i) <= '0';			-- lowest set bit wins if hold is not one-hot
					exit;
				end if;
			end loop;
		end if;
	end process;

	process(clk)
		variable e: unsigned(4 downto 0);
	begin
		if rising_edge(clk) then
			done_r <= '0';
			if rst = '1' then
				busy_r <= '0';
				sck_r <= cpol;
			elsif busy_r = '0' then
				sck_r <= cpol;
				if start = '1' then
					busy_r <= '1';
					cur <= dev;
					pha <= cpha;
					tx_sh <= tx;
					if div = 0 then half <= to_unsigned(1, 5); cnt <= to_unsigned(1, 5);
					else half <= div; cnt <= div;
					end if;
					k <= (others => '0');
				end if;
			elsif cnt > 1 then
				cnt <= cnt - 1;
			else
				cnt <= half;
				if k = 16 then
					-- trailing half period after the last edge: done
					busy_r <= '0';
					done_r <= '1';
					rx_r <= rx_sh;
				else
					e := k + 1;						-- the edge being made now
					k <= e;
					sck_r <= not sck_r;
					if (e(0) = '1') = (pha = '0') then		-- sampling edge
						rx_sh <= rx_sh(6 downto 0) & miso;
					elsif not (pha = '1' and e = 1) then	-- shifting edge
						tx_sh <= tx_sh(6 downto 0) & '0';
					end if;
				end if;
			end if;
		end if;
	end process;
end architecture;
