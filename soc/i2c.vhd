library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity i2c is
	port(
			clk		: in std_logic;

			sda		: inout std_logic;
			scl		: out std_logic;

			tx_data	: in std_logic_vector(7 downto 0);
			rx_data : out std_logic_vector(7 downto 0);

			go		: in std_logic := '0';
			stop	: in std_logic := '0'
		);
end entity;

architecture behavioural of i2c is
type states is (waiting, write_address, wait_write, wait_read, write, read, write_ack, read_ack, write_stop);
signal state: states := waiting;
signal state_nxt: states;
type bit_states is (setup, go_hi, hold, go_lo);
signal bit_state: bit_states := setup;

signal i2c_clk: std_logic := '0';

signal go_latch: std_logic;
signal go_edge: std_logic;

begin
process (clk)
variable clk_delay: integer range 0 to 50000000 := 0;
begin
   if (rising_edge(clk)) then
		if (clk_delay < 5000) then
			clk_delay := clk_delay + 1;
		else
			clk_delay := 0;
			i2c_clk <= not i2c_clk;
		end if;
	end if;
end process;

process (i2c_clk)
begin
	if (rising_edge(i2c_clk)) then
		go_latch <= go;
	end if;
end process;

--go_edge <= (not go_latch) and go;
--go_edge <= (not go) and go_latch;

go_edge <= go;
scl <= i2c_clk and go;

process (i2c_clk)
variable send_start: integer range 0 to 1 := 0;
variable bit_counter: integer range -1 to 7 := 7;
begin
	if (rising_edge(i2c_clk)) then
		case state is
			when waiting =>
					send_start := 1;
					state <= write_address;
					scl <= '1';
					sda <= '1';
			when write_address =>
				if send_start = 1 then
					send_start := 0;
					sda <= '0';
					bit_counter := 7;
					bit_state <= hold;
				else
					case bit_state is
						when hold =>
							scl <= '0';
						when setup =>
							if bit_counter = -1 then
								bit_counter := 7;
								state <= read_ack;
								if tx_data(0) = '1' then
									state_nxt <= wait_read;
								else
									state_nxt <= wait_write;
								end if;
								bit_state <= go_hi;
							else
								sda <= tx_data(bit_counter);
								bit_state <= go_hi;
							end if;
						when go_hi =>
							scl <= '1';
							bit_state <= go_lo;
						when go_lo =>
							scl <= '0';
							bit_counter := bit_counter - 1;
							bit_state <= setup;
					end case;
				end if;
			when read_ack =>
				case bit_state is
					when go_hi =>
						scl <= '1';
						bit_state <= go_lo;
					when go_lo =>
						scl <= '0';
						state <= state_nxt;
					when others =>
						state <= waiting;
				end case;
			when wait_read =>
				if go_edge = '1' then
					state <= read;
					bit_state <= go_hi;
				elsif stop = '1' then
					state <= write_stop;
					bit_state <= go_hi;
				end if;
			when wait_write =>
				if go_edge = '1' then
					state <= write;
					bit_state <= hold;
				elsif stop = '1' then
					state <= write_stop;
					bit_state <= go_hi;
				end if;
			when write =>
				case bit_state is
					when hold =>
						scl <= '0';
					when setup =>
						if bit_counter = -1 then
							bit_counter := 7;
							state <= read_ack;
							state_nxt <= wait_write;
							bit_state <= go_hi;
						else
							sda <= tx_data(bit_counter);
							bit_state <= go_hi;
						end if;
					when go_hi =>
						scl <= '1';
						bit_state <= go_lo;
					when go_lo =>
						scl <= '0';
						bit_counter := bit_counter - 1;
						bit_state <= setup;
				end case;
			when read =>
				case bit_state is
					when go_hi =>
						if bit_counter = -1 then
							bit_counter := 7;
							state <= read_ack;
							state_nxt <= wait_read;
							bit_state <= go_hi;
						else
							scl <= '1';
							bit_state <= hold;
						end if;
					when hold =>
						rx_data(bit_counter) <= sda;
					when go_lo =>
						bit_counter := bit_counter - 1;
						scl <= '0';
						bit_state <= go_hi;
					when others =>
						state <= waiting;
				end case;
			when write_stop =>
				case bit_state is
					when go_hi =>
						scl <= '1';
						bit_state <= hold;
					when hold =>
						sda <= '1';
						bit_state <= go_lo;
					when go_lo =>
						scl <= '0';
						state <= waiting;
					when others =>
						state <= waiting;
				end case;

			when others => state <= waiting;
		end case;
	end if;
end process;
end architecture;
