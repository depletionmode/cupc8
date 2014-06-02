-- Based on:
--
-- Simple generic RAM Model
--
-- +-----------------------------+
-- |    Copyright 2008 DOULOS    |
-- |   designer :  JK            |
-- +-----------------------------+
--
-- http://www.doulos.com/knowhow/vhdl_designers_guide/models/simple_ram_model/

library IEEE;
use IEEE.STD_LOGIC_1164.all;
use IEEE.Numeric_Std.all;

entity simpleram is
  port (
    en   : in  std_logic;
    we      : in  std_logic;
    address : in  std_logic_vector;
    datain  : in  std_logic_vector;
    dataout : out std_logic_vector
  );
end entity simpleram;

architecture RTL of simpleram is

   type ram_type is array (0 to (2**address'length)-1) of std_logic_vector(datain'range);
   signal ram : ram_type;
   signal read_address : std_logic_vector(address'range);

	shared variable tmp : std_logic_vector(7 downto 0) := "10101010";
begin

  RamProc: process(en) is

  begin
    if en = '1' then
      if we = '1' then
		tmp := datain;
        --ram(to_integer(unsigned(address))) <= datain;
      end if;
      read_address <= address;
    end if;
  end process RamProc;

  --dataout <= ram(to_integer(unsigned(read_address)));
  dataout <= tmp;

end architecture RTL;