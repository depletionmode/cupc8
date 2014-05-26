-- Copyright (C) 1991-2013 Altera Corporation
-- Your use of Altera Corporation's design tools, logic functions 
-- and other software and tools, and its AMPP partner logic 
-- functions, and any output files from any of the foregoing 
-- (including device programming or simulation files), and any 
-- associated documentation or information are expressly subject 
-- to the terms and conditions of the Altera Program License 
-- Subscription Agreement, Altera MegaCore Function License 
-- Agreement, or other applicable license agreement, including, 
-- without limitation, that your use is for the sole purpose of 
-- programming logic devices manufactured by Altera and sold by 
-- Altera or its authorized distributors.  Please refer to the 
-- applicable agreement for further details.

-- VENDOR "Altera"
-- PROGRAM "Quartus II 32-bit"
-- VERSION "Version 13.1.0 Build 162 10/23/2013 SJ Web Edition"

-- DATE "05/23/2014 08:32:00"

-- 
-- Device: Altera EP3C16F484C6 Package FBGA484
-- 

-- 
-- This VHDL file should be used for ModelSim-Altera (VHDL) only
-- 

LIBRARY ALTERA;
LIBRARY CYCLONEIII;
LIBRARY IEEE;
LIBRARY STD;
USE ALTERA.ALTERA_PRIMITIVES_COMPONENTS.ALL;
USE CYCLONEIII.CYCLONEIII_COMPONENTS.ALL;
USE IEEE.NUMERIC_STD.ALL;
USE IEEE.STD_LOGIC_1164.ALL;
USE STD.STANDARD.ALL;

ENTITY 	alu IS
    PORT (
	clk : IN std_logic;
	op : IN std_logic_vector(3 DOWNTO 0);
	a : IN IEEE.NUMERIC_STD.unsigned(7 DOWNTO 0);
	b : IN IEEE.NUMERIC_STD.unsigned(7 DOWNTO 0);
	r : OUT IEEE.NUMERIC_STD.unsigned(7 DOWNTO 0);
	zf : OUT STD.STANDARD.bit;
	cf : OUT STD.STANDARD.bit
	);
END alu;

-- Design Ports Information
-- r[0]	=>  Location: PIN_G18,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- r[1]	=>  Location: PIN_J15,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- r[2]	=>  Location: PIN_J21,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- r[3]	=>  Location: PIN_D20,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- r[4]	=>  Location: PIN_C22,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- r[5]	=>  Location: PIN_E21,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- r[6]	=>  Location: PIN_F17,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- r[7]	=>  Location: PIN_H16,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- zf	=>  Location: PIN_J18,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- cf	=>  Location: PIN_V7,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- op[2]	=>  Location: PIN_G14,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- op[1]	=>  Location: PIN_J17,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[0]	=>  Location: PIN_F22,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[0]	=>  Location: PIN_H21,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- op[0]	=>  Location: PIN_C21,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- op[3]	=>  Location: PIN_C19,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[7]	=>  Location: PIN_H15,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[3]	=>  Location: PIN_H20,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[2]	=>  Location: PIN_H17,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[1]	=>  Location: PIN_H19,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[7]	=>  Location: PIN_F21,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[4]	=>  Location: PIN_D21,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[5]	=>  Location: PIN_K17,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- b[6]	=>  Location: PIN_F19,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[6]	=>  Location: PIN_H18,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[5]	=>  Location: PIN_D22,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[4]	=>  Location: PIN_C20,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[3]	=>  Location: PIN_F16,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[2]	=>  Location: PIN_F20,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- a[1]	=>  Location: PIN_E22,	 I/O Standard: 2.5 V,	 Current Strength: Default
-- clk	=>  Location: PIN_G2,	 I/O Standard: 2.5 V,	 Current Strength: Default


ARCHITECTURE structure OF alu IS
SIGNAL gnd : std_logic := '0';
SIGNAL vcc : std_logic := '1';
SIGNAL unknown : std_logic := 'X';
SIGNAL devoe : std_logic := '1';
SIGNAL devclrn : std_logic := '1';
SIGNAL devpor : std_logic := '1';
SIGNAL ww_devoe : std_logic;
SIGNAL ww_devclrn : std_logic;
SIGNAL ww_devpor : std_logic;
SIGNAL ww_clk : std_logic;
SIGNAL ww_op : std_logic_vector(3 DOWNTO 0);
SIGNAL ww_a : std_logic_vector(7 DOWNTO 0);
SIGNAL ww_b : std_logic_vector(7 DOWNTO 0);
SIGNAL ww_r : std_logic_vector(7 DOWNTO 0);
SIGNAL ww_zf : std_logic;
SIGNAL ww_cf : std_logic;
SIGNAL \clk~inputclkctrl_INCLK_bus\ : std_logic_vector(3 DOWNTO 0);
SIGNAL \r[0]~output_o\ : std_logic;
SIGNAL \r[1]~output_o\ : std_logic;
SIGNAL \r[2]~output_o\ : std_logic;
SIGNAL \r[3]~output_o\ : std_logic;
SIGNAL \r[4]~output_o\ : std_logic;
SIGNAL \r[5]~output_o\ : std_logic;
SIGNAL \r[6]~output_o\ : std_logic;
SIGNAL \r[7]~output_o\ : std_logic;
SIGNAL \zf~output_o\ : std_logic;
SIGNAL \cf~output_o\ : std_logic;
SIGNAL \clk~input_o\ : std_logic;
SIGNAL \clk~inputclkctrl_outclk\ : std_logic;
SIGNAL \op[2]~input_o\ : std_logic;
SIGNAL \op[3]~input_o\ : std_logic;
SIGNAL \op[0]~input_o\ : std_logic;
SIGNAL \rres[0]~4_combout\ : std_logic;
SIGNAL \op[1]~input_o\ : std_logic;
SIGNAL \rres[0]~0_combout\ : std_logic;
SIGNAL \b[7]~input_o\ : std_logic;
SIGNAL \b[6]~input_o\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|selnose[45]~6_combout\ : std_logic;
SIGNAL \b[5]~input_o\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|selnose[36]~5_combout\ : std_logic;
SIGNAL \b[4]~input_o\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|selnose[27]~3_combout\ : std_logic;
SIGNAL \b[0]~input_o\ : std_logic;
SIGNAL \a[6]~input_o\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\ : std_logic;
SIGNAL \b[3]~input_o\ : std_logic;
SIGNAL \b[2]~input_o\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|selnose[0]~4_combout\ : std_logic;
SIGNAL \b[1]~input_o\ : std_logic;
SIGNAL \a[7]~input_o\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|selnose[0]~2_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[0]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[8]~1_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ : std_logic;
SIGNAL \a[5]~input_o\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\ : std_logic;
SIGNAL \a[4]~input_o\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\ : std_logic;
SIGNAL \a[3]~input_o\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\ : std_logic;
SIGNAL \a[2]~input_o\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\ : std_logic;
SIGNAL \a[1]~input_o\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\ : std_logic;
SIGNAL \a[0]~input_o\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~15\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~0_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[56]~28_combout\ : std_logic;
SIGNAL \rres[0]~3_combout\ : std_logic;
SIGNAL \rres[0]~2_combout\ : std_logic;
SIGNAL \Mux8~0_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[18]~1_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[17]~2_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[16]~3_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[27]~4_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[26]~5_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[25]~6_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[24]~7_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[36]~8_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[35]~9_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[34]~10_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[33]~11_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[32]~12_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[45]~13_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[44]~14_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[43]~15_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[42]~16_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[41]~17_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[40]~18_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[54]~19_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[53]~20_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[52]~21_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[51]~22_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[50]~23_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[49]~24_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|StageOut[48]~25_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[0]~1_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[1]~3_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[2]~5_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[3]~7_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[4]~9_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[5]~11_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[6]~13_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[7]~15_cout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ : std_logic;
SIGNAL \rres[0]~1_combout\ : std_logic;
SIGNAL \Mux8~1_combout\ : std_logic;
SIGNAL \Add0~0_combout\ : std_logic;
SIGNAL \Add0~2_cout\ : std_logic;
SIGNAL \Add0~3_combout\ : std_logic;
SIGNAL \Mux8~2_combout\ : std_logic;
SIGNAL \Mux8~3_combout\ : std_logic;
SIGNAL \rres[0]~5_combout\ : std_logic;
SIGNAL \Mux7~0_combout\ : std_logic;
SIGNAL \Add0~5_combout\ : std_logic;
SIGNAL \Add0~4\ : std_logic;
SIGNAL \Add0~6_combout\ : std_logic;
SIGNAL \Mux7~1_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~2_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[57]~29_combout\ : std_logic;
SIGNAL \Mux7~2_combout\ : std_logic;
SIGNAL \Mux7~3_combout\ : std_logic;
SIGNAL \Mux6~0_combout\ : std_logic;
SIGNAL \Mux6~1_combout\ : std_logic;
SIGNAL \Add0~8_combout\ : std_logic;
SIGNAL \Add0~7\ : std_logic;
SIGNAL \Add0~9_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~4_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[58]~30_combout\ : std_logic;
SIGNAL \Mux6~2_combout\ : std_logic;
SIGNAL \Mux6~3_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~6_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[59]~31_combout\ : std_logic;
SIGNAL \Add0~11_combout\ : std_logic;
SIGNAL \Add0~10\ : std_logic;
SIGNAL \Add0~12_combout\ : std_logic;
SIGNAL \Mux5~0_combout\ : std_logic;
SIGNAL \Mux5~1_combout\ : std_logic;
SIGNAL \Mux5~2_combout\ : std_logic;
SIGNAL \Mux5~3_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~8_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[60]~32_combout\ : std_logic;
SIGNAL \Add0~14_combout\ : std_logic;
SIGNAL \Add0~13\ : std_logic;
SIGNAL \Add0~15_combout\ : std_logic;
SIGNAL \Mux4~0_combout\ : std_logic;
SIGNAL \Mux4~1_combout\ : std_logic;
SIGNAL \Mux4~2_combout\ : std_logic;
SIGNAL \Mux4~3_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~10_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[61]~33_combout\ : std_logic;
SIGNAL \Add0~17_combout\ : std_logic;
SIGNAL \Add0~16\ : std_logic;
SIGNAL \Add0~18_combout\ : std_logic;
SIGNAL \Mux3~0_combout\ : std_logic;
SIGNAL \Mux3~1_combout\ : std_logic;
SIGNAL \Mux3~2_combout\ : std_logic;
SIGNAL \Mux3~3_combout\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|selnose[9]~7_combout\ : std_logic;
SIGNAL \Mux2~0_combout\ : std_logic;
SIGNAL \Mux2~1_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~12_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[62]~34_combout\ : std_logic;
SIGNAL \Add0~20_combout\ : std_logic;
SIGNAL \Add0~19\ : std_logic;
SIGNAL \Add0~21_combout\ : std_logic;
SIGNAL \Mux2~2_combout\ : std_logic;
SIGNAL \Mux2~3_combout\ : std_logic;
SIGNAL \Mux1~0_combout\ : std_logic;
SIGNAL \Add0~23_combout\ : std_logic;
SIGNAL \Add0~22\ : std_logic;
SIGNAL \Add0~24_combout\ : std_logic;
SIGNAL \Mux1~1_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~14_combout\ : std_logic;
SIGNAL \Mod0|auto_generated|divider|divider|StageOut[63]~35_combout\ : std_logic;
SIGNAL \Mux1~2_combout\ : std_logic;
SIGNAL \Mux1~3_combout\ : std_logic;
SIGNAL \Mux0~3_combout\ : std_logic;
SIGNAL \RESULT~0_combout\ : std_logic;
SIGNAL \Mux0~4_combout\ : std_logic;
SIGNAL \Mux0~0_combout\ : std_logic;
SIGNAL \Mux0~1_combout\ : std_logic;
SIGNAL \Mux0~2_combout\ : std_logic;
SIGNAL \Mux0~5_combout\ : std_logic;
SIGNAL \z~q\ : std_logic;
SIGNAL \Div0|auto_generated|divider|divider|sel\ : std_logic_vector(71 DOWNTO 0);
SIGNAL \Div0|auto_generated|divider|divider|selnose\ : std_logic_vector(71 DOWNTO 0);
SIGNAL rres : std_logic_vector(7 DOWNTO 0);

BEGIN

ww_clk <= clk;
ww_op <= op;
ww_a <= IEEE.STD_LOGIC_1164.STD_LOGIC_VECTOR(a);
ww_b <= IEEE.STD_LOGIC_1164.STD_LOGIC_VECTOR(b);
r <= IEEE.NUMERIC_STD.UNSIGNED(ww_r);
zf <= IEEE.STD_LOGIC_1164.TO_BIT(ww_zf);
cf <= IEEE.STD_LOGIC_1164.TO_BIT(ww_cf);
ww_devoe <= devoe;
ww_devclrn <= devclrn;
ww_devpor <= devpor;

\clk~inputclkctrl_INCLK_bus\ <= (vcc & vcc & vcc & \clk~input_o\);

-- Location: IOOBUF_X41_Y25_N9
\r[0]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(0),
	devoe => ww_devoe,
	o => \r[0]~output_o\);

-- Location: IOOBUF_X41_Y19_N23
\r[1]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(1),
	devoe => ww_devoe,
	o => \r[1]~output_o\);

-- Location: IOOBUF_X41_Y20_N23
\r[2]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(2),
	devoe => ww_devoe,
	o => \r[2]~output_o\);

-- Location: IOOBUF_X41_Y27_N16
\r[3]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(3),
	devoe => ww_devoe,
	o => \r[3]~output_o\);

-- Location: IOOBUF_X41_Y26_N23
\r[4]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(4),
	devoe => ww_devoe,
	o => \r[4]~output_o\);

-- Location: IOOBUF_X41_Y23_N9
\r[5]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(5),
	devoe => ww_devoe,
	o => \r[5]~output_o\);

-- Location: IOOBUF_X41_Y27_N9
\r[6]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(6),
	devoe => ww_devoe,
	o => \r[6]~output_o\);

-- Location: IOOBUF_X41_Y24_N16
\r[7]~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => rres(7),
	devoe => ww_devoe,
	o => \r[7]~output_o\);

-- Location: IOOBUF_X41_Y21_N2
\zf~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => \z~q\,
	devoe => ww_devoe,
	o => \zf~output_o\);

-- Location: IOOBUF_X7_Y0_N16
\cf~output\ : cycloneiii_io_obuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	open_drain_output => "false")
-- pragma translate_on
PORT MAP (
	i => GND,
	devoe => ww_devoe,
	o => \cf~output_o\);

-- Location: IOIBUF_X0_Y14_N1
\clk~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_clk,
	o => \clk~input_o\);

-- Location: CLKCTRL_G4
\clk~inputclkctrl\ : cycloneiii_clkctrl
-- pragma translate_off
GENERIC MAP (
	clock_type => "global clock",
	ena_register_mode => "none")
-- pragma translate_on
PORT MAP (
	inclk => \clk~inputclkctrl_INCLK_bus\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	outclk => \clk~inputclkctrl_outclk\);

-- Location: IOIBUF_X37_Y29_N8
\op[2]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_op(2),
	o => \op[2]~input_o\);

-- Location: IOIBUF_X37_Y29_N22
\op[3]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_op(3),
	o => \op[3]~input_o\);

-- Location: IOIBUF_X41_Y26_N15
\op[0]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_op(0),
	o => \op[0]~input_o\);

-- Location: LCCOMB_X37_Y23_N4
\rres[0]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \rres[0]~4_combout\ = (\op[2]~input_o\ & (!\op[3]~input_o\ & \op[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000101000000000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datac => \op[3]~input_o\,
	datad => \op[0]~input_o\,
	combout => \rres[0]~4_combout\);

-- Location: IOIBUF_X41_Y24_N22
\op[1]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_op(1),
	o => \op[1]~input_o\);

-- Location: LCCOMB_X37_Y23_N12
\rres[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \rres[0]~0_combout\ = (\op[3]~input_o\ & ((\op[1]~input_o\) # (!\op[2]~input_o\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000001010000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datac => \op[3]~input_o\,
	datad => \op[1]~input_o\,
	combout => \rres[0]~0_combout\);

-- Location: IOIBUF_X41_Y22_N15
\b[7]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(7),
	o => \b[7]~input_o\);

-- Location: IOIBUF_X41_Y25_N15
\b[6]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(6),
	o => \b[6]~input_o\);

-- Location: LCCOMB_X38_Y23_N24
\Div0|auto_generated|divider|divider|selnose[45]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose[45]~6_combout\ = (!\b[7]~input_o\ & !\b[6]~input_o\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000110011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \b[7]~input_o\,
	datad => \b[6]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\);

-- Location: IOIBUF_X41_Y21_N15
\b[5]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(5),
	o => \b[5]~input_o\);

-- Location: LCCOMB_X38_Y23_N30
\Div0|auto_generated|divider|divider|selnose[36]~5\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose[36]~5_combout\ = (!\b[6]~input_o\ & (!\b[7]~input_o\ & !\b[5]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000010001",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[6]~input_o\,
	datab => \b[7]~input_o\,
	datad => \b[5]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\);

-- Location: IOIBUF_X41_Y24_N1
\b[4]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(4),
	o => \b[4]~input_o\);

-- Location: LCCOMB_X39_Y22_N0
\Div0|auto_generated|divider|divider|selnose[27]~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose[27]~3_combout\ = (!\b[4]~input_o\ & (!\b[5]~input_o\ & (!\b[7]~input_o\ & !\b[6]~input_o\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000000001",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[4]~input_o\,
	datab => \b[5]~input_o\,
	datac => \b[7]~input_o\,
	datad => \b[6]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\);

-- Location: IOIBUF_X41_Y22_N22
\b[0]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(0),
	o => \b[0]~input_o\);

-- Location: IOIBUF_X41_Y23_N1
\a[6]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(6),
	o => \a[6]~input_o\);

-- Location: LCCOMB_X35_Y23_N6
\Div0|auto_generated|divider|divider|add_sub_1|_~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\ = (\a[6]~input_o\) # (!\b[0]~input_o\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111010111110101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datac => \a[6]~input_o\,
	combout => \Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\);

-- Location: IOIBUF_X41_Y22_N1
\b[3]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(3),
	o => \b[3]~input_o\);

-- Location: IOIBUF_X41_Y25_N1
\b[2]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(2),
	o => \b[2]~input_o\);

-- Location: LCCOMB_X35_Y23_N8
\Div0|auto_generated|divider|divider|selnose[0]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose[0]~4_combout\ = (!\b[3]~input_o\ & (\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & !\b[2]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000001010000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datac => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datad => \b[2]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose[0]~4_combout\);

-- Location: IOIBUF_X41_Y23_N22
\b[1]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_b(1),
	o => \b[1]~input_o\);

-- Location: IOIBUF_X35_Y29_N22
\a[7]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(7),
	o => \a[7]~input_o\);

-- Location: LCCOMB_X35_Y23_N0
\Div0|auto_generated|divider|divider|selnose[0]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose[0]~2_combout\ = (\b[1]~input_o\) # ((!\a[7]~input_o\ & \b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111010111110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[7]~input_o\,
	datac => \b[1]~input_o\,
	datad => \b[0]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose[0]~2_combout\);

-- Location: LCCOMB_X35_Y23_N2
\Div0|auto_generated|divider|divider|selnose[0]\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose\(0) = (\b[3]~input_o\) # ((\Div0|auto_generated|divider|divider|selnose[0]~2_combout\) # ((\b[2]~input_o\) # (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111111101111",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Div0|auto_generated|divider|divider|selnose[0]~2_combout\,
	datac => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datad => \b[2]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose\(0));

-- Location: LCCOMB_X35_Y23_N28
\Div0|auto_generated|divider|divider|StageOut[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[0]~0_combout\ = \a[7]~input_o\ $ (((!\Div0|auto_generated|divider|divider|selnose\(0) & \b[0]~input_o\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001100110101010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[7]~input_o\,
	datab => \Div0|auto_generated|divider|divider|selnose\(0),
	datad => \b[0]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[0]~0_combout\);

-- Location: LCCOMB_X35_Y23_N10
\Mod0|auto_generated|divider|divider|StageOut[9]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\ = (\Div0|auto_generated|divider|divider|StageOut[0]~0_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\ $ (\b[1]~input_o\)) # 
-- (!\Div0|auto_generated|divider|divider|selnose[0]~4_combout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0111101100000000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[0]~4_combout\,
	datac => \b[1]~input_o\,
	datad => \Div0|auto_generated|divider|divider|StageOut[0]~0_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\);

-- Location: LCCOMB_X39_Y23_N0
\Div0|auto_generated|divider|divider|sel[18]\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|sel\(18) = (\b[3]~input_o\) # (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111001111110011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datac => \b[3]~input_o\,
	combout => \Div0|auto_generated|divider|divider|sel\(18));

-- Location: LCCOMB_X35_Y23_N12
\Mod0|auto_generated|divider|divider|StageOut[8]~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[8]~1_combout\ = (\a[6]~input_o\ & (\b[1]~input_o\ & (\Div0|auto_generated|divider|divider|selnose\(0) $ (\a[7]~input_o\)))) # (!\a[6]~input_o\ & ((\b[1]~input_o\) # 
-- (\Div0|auto_generated|divider|divider|selnose\(0) $ (\a[7]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0111000111010100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[6]~input_o\,
	datab => \Div0|auto_generated|divider|divider|selnose\(0),
	datac => \b[1]~input_o\,
	datad => \a[7]~input_o\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[8]~1_combout\);

-- Location: LCCOMB_X35_Y23_N24
\Mod0|auto_generated|divider|divider|StageOut[8]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ = \a[6]~input_o\ $ (((!\Mod0|auto_generated|divider|divider|StageOut[8]~1_combout\ & (\Div0|auto_generated|divider|divider|selnose[0]~4_combout\ & \b[0]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011010011110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[8]~1_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[0]~4_combout\,
	datac => \a[6]~input_o\,
	datad => \b[0]~input_o\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\);

-- Location: IOIBUF_X41_Y24_N8
\a[5]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(5),
	o => \a[5]~input_o\);

-- Location: LCCOMB_X39_Y23_N2
\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\ = (\a[5]~input_o\ & ((GND) # (!\b[0]~input_o\))) # (!\a[5]~input_o\ & (\b[0]~input_o\ $ (GND)))
-- \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\ = CARRY((\a[5]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011010111011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[5]~input_o\,
	datab => \b[0]~input_o\,
	datad => VCC,
	combout => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\);

-- Location: LCCOMB_X39_Y23_N4
\Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\ = (\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\) # (GND))))) # (!\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\))))
-- \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\ = CARRY((\b[1]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\) # (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\))) # (!\b[1]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\);

-- Location: LCCOMB_X39_Y23_N6
\Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\ = ((\b[2]~input_o\ $ (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\ $ (\Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\ = CARRY((\b[2]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\)) # (!\b[2]~input_o\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\) # (!\Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[2]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\);

-- Location: LCCOMB_X39_Y23_N8
\Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ = !\Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000111100001111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\);

-- Location: LCCOMB_X39_Y23_N16
\Mod0|auto_generated|divider|divider|StageOut[18]~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\ = (\Div0|auto_generated|divider|divider|sel\(18) & (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\)) # (!\Div0|auto_generated|divider|divider|sel\(18) & 
-- ((\Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101110101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\,
	datab => \Div0|auto_generated|divider|divider|sel\(18),
	datac => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\);

-- Location: LCCOMB_X39_Y23_N10
\Mod0|auto_generated|divider|divider|StageOut[17]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\ = (\Div0|auto_generated|divider|divider|sel\(18) & (((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\)))) # (!\Div0|auto_generated|divider|divider|sel\(18) & 
-- ((\Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111000010000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|sel\(18),
	datab => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\);

-- Location: LCCOMB_X39_Y23_N28
\Mod0|auto_generated|divider|divider|StageOut[16]~5\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\ = (\Div0|auto_generated|divider|divider|sel\(18) & (\a[5]~input_o\)) # (!\Div0|auto_generated|divider|divider|sel\(18) & ((\Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ 
-- & (\a[5]~input_o\)) # (!\Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101110101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[5]~input_o\,
	datab => \Div0|auto_generated|divider|divider|sel\(18),
	datac => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\);

-- Location: IOIBUF_X41_Y27_N22
\a[4]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(4),
	o => \a[4]~input_o\);

-- Location: LCCOMB_X40_Y23_N22
\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\ = (\a[4]~input_o\ & ((GND) # (!\b[0]~input_o\))) # (!\a[4]~input_o\ & (\b[0]~input_o\ $ (GND)))
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\ = CARRY((\a[4]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011010111011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[4]~input_o\,
	datab => \b[0]~input_o\,
	datad => VCC,
	combout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\);

-- Location: LCCOMB_X40_Y23_N24
\Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\ = (\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\) # (GND))))) # (!\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\))))
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\ = CARRY((\b[1]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\) # (!\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\))) # (!\b[1]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\);

-- Location: LCCOMB_X40_Y23_N26
\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\ $ (\b[2]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\ & (!\b[2]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\);

-- Location: LCCOMB_X40_Y23_N28
\Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\ = (\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\) # (GND))))) # (!\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\))))
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\ = CARRY((\b[3]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\) # (!\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\))) # (!\b[3]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\);

-- Location: LCCOMB_X40_Y23_N30
\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ = \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011110000",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\);

-- Location: LCCOMB_X40_Y23_N12
\Mod0|auto_generated|divider|divider|StageOut[27]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\ = (\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & 
-- (\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100111011000100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[18]~3_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\);

-- Location: LCCOMB_X40_Y23_N14
\Mod0|auto_generated|divider|divider|StageOut[26]~7\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\ = (\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111101100001000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[17]~4_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\);

-- Location: LCCOMB_X40_Y23_N16
\Mod0|auto_generated|divider|divider|StageOut[25]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\ = (\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & 
-- (\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100111011000100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[16]~5_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\);

-- Location: LCCOMB_X40_Y23_N18
\Mod0|auto_generated|divider|divider|StageOut[24]~9\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\ = (\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & ((\a[4]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\)))) # (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (((\a[4]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011011000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\,
	datac => \a[4]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\);

-- Location: IOIBUF_X39_Y29_N1
\a[3]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(3),
	o => \a[3]~input_o\);

-- Location: LCCOMB_X40_Y23_N0
\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\ = (\a[3]~input_o\ & ((GND) # (!\b[0]~input_o\))) # (!\a[3]~input_o\ & (\b[0]~input_o\ $ (GND)))
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\ = CARRY((\a[3]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011010111011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[3]~input_o\,
	datab => \b[0]~input_o\,
	datad => VCC,
	combout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\);

-- Location: LCCOMB_X40_Y23_N2
\Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\ = (\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\) # (GND))))) # (!\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\))))
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\ = CARRY((\b[1]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\) # (!\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\))) # (!\b[1]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\);

-- Location: LCCOMB_X40_Y23_N4
\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\ $ (\b[2]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\ & (!\b[2]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\);

-- Location: LCCOMB_X40_Y23_N6
\Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\ = (\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\) # (GND))))) # (!\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\))))
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\ = CARRY((\b[3]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\) # (!\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\))) # (!\b[3]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\);

-- Location: LCCOMB_X40_Y23_N8
\Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\ = ((\b[4]~input_o\ $ (\Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\ $ (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\ = CARRY((\b[4]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\)) # (!\b[4]~input_o\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\) # (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[4]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\);

-- Location: LCCOMB_X40_Y23_N10
\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ = !\Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000111100001111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\);

-- Location: LCCOMB_X40_Y22_N0
\Mod0|auto_generated|divider|divider|StageOut[36]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\ = (\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110100100000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[27]~6_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\);

-- Location: LCCOMB_X40_Y22_N10
\Mod0|auto_generated|divider|divider|StageOut[35]~11\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\ = (\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110100100000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[26]~7_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\);

-- Location: LCCOMB_X39_Y23_N30
\Mod0|auto_generated|divider|divider|StageOut[34]~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\ = (\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111101100001000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[25]~8_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\);

-- Location: LCCOMB_X40_Y22_N28
\Mod0|auto_generated|divider|divider|StageOut[33]~13\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\ = (\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- (\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111001011010000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datac => \Mod0|auto_generated|divider|divider|StageOut[24]~9_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\);

-- Location: LCCOMB_X40_Y23_N20
\Mod0|auto_generated|divider|divider|StageOut[32]~14\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & (((\a[3]~input_o\)))) # (!\Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- ((\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\))) # (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (\a[3]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111010010110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datac => \a[3]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\);

-- Location: IOIBUF_X41_Y25_N22
\a[2]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(2),
	o => \a[2]~input_o\);

-- Location: LCCOMB_X40_Y22_N14
\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\ = (\a[2]~input_o\ & ((GND) # (!\b[0]~input_o\))) # (!\a[2]~input_o\ & (\b[0]~input_o\ $ (GND)))
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\ = CARRY((\a[2]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011010111011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[2]~input_o\,
	datab => \b[0]~input_o\,
	datad => VCC,
	combout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\);

-- Location: LCCOMB_X40_Y22_N16
\Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\ = (\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\) # (GND))))) # (!\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\))))
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\ = CARRY((\b[1]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\) # (!\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\))) # (!\b[1]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\);

-- Location: LCCOMB_X40_Y22_N18
\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\ = ((\b[2]~input_o\ $ (\Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\ $ (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\ = CARRY((\b[2]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\)) # (!\b[2]~input_o\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\) # (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[2]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\);

-- Location: LCCOMB_X40_Y22_N20
\Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\ = (\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\) # (GND))))) # (!\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\))))
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\ = CARRY((\b[3]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\) # (!\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\))) # (!\b[3]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\);

-- Location: LCCOMB_X40_Y22_N22
\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\ $ (\b[4]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\) # (!\b[4]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\ & (!\b[4]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\,
	datab => \b[4]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\);

-- Location: LCCOMB_X40_Y22_N24
\Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\ = (\b[5]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\) # (GND))))) # (!\b[5]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\))))
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\ = CARRY((\b[5]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\) # (!\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\))) # (!\b[5]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[5]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\);

-- Location: LCCOMB_X40_Y22_N26
\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ = \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011110000",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\);

-- Location: LCCOMB_X40_Y22_N6
\Mod0|auto_generated|divider|divider|StageOut[45]~15\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110100001000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[36]~10_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\);

-- Location: LCCOMB_X40_Y22_N8
\Mod0|auto_generated|divider|divider|StageOut[44]~16\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\)) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & ((\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1101100011001100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[35]~11_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\,
	datad => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\);

-- Location: LCCOMB_X40_Y22_N2
\Mod0|auto_generated|divider|divider|StageOut[43]~17\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- (\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100111011000100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[34]~12_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\);

-- Location: LCCOMB_X40_Y22_N12
\Mod0|auto_generated|divider|divider|StageOut[42]~18\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110100001000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[33]~13_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\);

-- Location: LCCOMB_X40_Y22_N4
\Mod0|auto_generated|divider|divider|StageOut[41]~19\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110100001000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[32]~14_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\);

-- Location: LCCOMB_X40_Y22_N30
\Mod0|auto_generated|divider|divider|StageOut[40]~20\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (((\a[2]~input_o\)))) # (!\Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- ((\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\)) # (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\a[2]~input_o\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110010011110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\,
	datac => \a[2]~input_o\,
	datad => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\);

-- Location: IOIBUF_X41_Y23_N15
\a[1]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(1),
	o => \a[1]~input_o\);

-- Location: LCCOMB_X39_Y22_N6
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\ = (\a[1]~input_o\ & ((GND) # (!\b[0]~input_o\))) # (!\a[1]~input_o\ & (\b[0]~input_o\ $ (GND)))
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\ = CARRY((\a[1]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011010111011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[1]~input_o\,
	datab => \b[0]~input_o\,
	datad => VCC,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\);

-- Location: LCCOMB_X39_Y22_N8
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\ = (\Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\ & ((\b[1]~input_o\ & (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\)) # (!\b[1]~input_o\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\ & VCC)))) # (!\Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\ & ((\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\) # (GND))) # 
-- (!\b[1]~input_o\ & (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\))))
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\ & (\b[1]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\ & ((\b[1]~input_o\) # (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\,
	datab => \b[1]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\);

-- Location: LCCOMB_X39_Y22_N10
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\ $ (\b[2]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\ & (!\b[2]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\);

-- Location: LCCOMB_X39_Y22_N12
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\ = (\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\) # (GND))))) # (!\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\))))
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\ = CARRY((\b[3]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\) # (!\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\))) # (!\b[3]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\);

-- Location: LCCOMB_X39_Y22_N14
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\ $ (\b[4]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\) # (!\b[4]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\ & (!\b[4]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\,
	datab => \b[4]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\);

-- Location: LCCOMB_X39_Y22_N16
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\ = (\Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\ & ((\b[5]~input_o\ & (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\)) # (!\b[5]~input_o\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\ & VCC)))) # (!\Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\ & ((\b[5]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\) # (GND))) # 
-- (!\b[5]~input_o\ & (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\))))
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\ & (\b[5]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\ & ((\b[5]~input_o\) # (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\,
	datab => \b[5]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\);

-- Location: LCCOMB_X39_Y22_N18
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\ $ (\b[6]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\) # (!\b[6]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\ & (!\b[6]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\,
	datab => \b[6]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\);

-- Location: LCCOMB_X39_Y22_N20
\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ = !\Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000111100001111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\);

-- Location: LCCOMB_X39_Y22_N26
\Mod0|auto_generated|divider|divider|StageOut[54]~21\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\ = (\b[7]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\)) # (!\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & 
-- (\Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010101100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[45]~15_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\,
	datac => \b[7]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\);

-- Location: LCCOMB_X39_Y22_N28
\Mod0|auto_generated|divider|divider|StageOut[53]~22\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\ = (\b[7]~input_o\ & (((\Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\)))) # (!\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011100100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[7]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\,
	datac => \Mod0|auto_generated|divider|divider|StageOut[44]~16_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\);

-- Location: LCCOMB_X39_Y22_N22
\Mod0|auto_generated|divider|divider|StageOut[52]~23\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\ = (\b[7]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\)) # (!\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & 
-- (\Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010101100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[43]~17_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\,
	datac => \b[7]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\);

-- Location: LCCOMB_X39_Y22_N24
\Mod0|auto_generated|divider|divider|StageOut[51]~24\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\ = (\b[7]~input_o\ & (((\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\)))) # (!\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\))) # (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110011001010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[42]~18_combout\,
	datac => \b[7]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\);

-- Location: LCCOMB_X39_Y22_N2
\Mod0|auto_generated|divider|divider|StageOut[50]~25\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\)))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\))) # (!\b[7]~input_o\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111000000010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datac => \b[7]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[41]~19_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\);

-- Location: LCCOMB_X39_Y22_N4
\Mod0|auto_generated|divider|divider|StageOut[49]~26\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\ = (\b[7]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\)) # (!\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & 
-- (\Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\)) # (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010101100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[40]~20_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\,
	datac => \b[7]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\);

-- Location: LCCOMB_X39_Y22_N30
\Mod0|auto_generated|divider|divider|StageOut[48]~27\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\ = (\b[7]~input_o\ & (((\a[1]~input_o\)))) # (!\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (\a[1]~input_o\)) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000111100000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[7]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datac => \a[1]~input_o\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\);

-- Location: IOIBUF_X41_Y21_N22
\a[0]~input\ : cycloneiii_io_ibuf
-- pragma translate_off
GENERIC MAP (
	bus_hold => "false",
	simulate_z_as => "z")
-- pragma translate_on
PORT MAP (
	i => ww_a(0),
	o => \a[0]~input_o\);

-- Location: LCCOMB_X38_Y22_N8
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~0_combout\ = (\b[0]~input_o\ & (\a[0]~input_o\ $ (VCC))) # (!\b[0]~input_o\ & ((\a[0]~input_o\) # (GND)))
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\ = CARRY((\a[0]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011011011101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \a[0]~input_o\,
	datad => VCC,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~0_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\);

-- Location: LCCOMB_X38_Y22_N10
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~2_combout\ = (\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\) # (GND))))) # (!\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\))))
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\ = CARRY((\b[1]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\) # (!\Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\))) # (!\b[1]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~2_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\);

-- Location: LCCOMB_X38_Y22_N12
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~4_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\ $ (\b[2]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\ & (!\b[2]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~4_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\);

-- Location: LCCOMB_X38_Y22_N14
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~6_combout\ = (\Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\ & ((\b[3]~input_o\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\)) # (!\b[3]~input_o\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\ & VCC)))) # (!\Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\ & ((\b[3]~input_o\ & ((\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\) # (GND))) # 
-- (!\b[3]~input_o\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\))))
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\ & (\b[3]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\ & ((\b[3]~input_o\) # (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\,
	datab => \b[3]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~6_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\);

-- Location: LCCOMB_X38_Y22_N16
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~8_combout\ = ((\Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\ $ (\b[4]~input_o\ $ (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\ = CARRY((\Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\ & ((!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\) # (!\b[4]~input_o\))) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\ & (!\b[4]~input_o\ & !\Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\,
	datab => \b[4]~input_o\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~8_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\);

-- Location: LCCOMB_X38_Y22_N18
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~10_combout\ = (\b[5]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\) # (GND))))) # (!\b[5]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\))))
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\ = CARRY((\b[5]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\) # (!\Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\))) # (!\b[5]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[5]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~10_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\);

-- Location: LCCOMB_X38_Y22_N20
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~12_combout\ = ((\b[6]~input_o\ $ (\Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\ $ (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\)))) # (GND)
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\ = CARRY((\b[6]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\)) # (!\b[6]~input_o\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\) # (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[6]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~12_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\);

-- Location: LCCOMB_X38_Y22_N22
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~14\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~14_combout\ = (\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\ & ((\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\) # (GND))))) # (!\b[7]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\ & (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\))))
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~15\ = CARRY((\b[7]~input_o\ & ((!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\) # (!\Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\))) # (!\b[7]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\ & !\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[7]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\,
	datad => VCC,
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~14_combout\,
	cout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~15\);

-- Location: LCCOMB_X38_Y22_N24
\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ = \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~15\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011110000",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~15\,
	combout => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\);

-- Location: LCCOMB_X37_Y24_N8
\Mod0|auto_generated|divider|divider|StageOut[56]~28\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[56]~28_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\a[0]~input_o\))) # (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & 
-- (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~0_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110010011100100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[0]~0_combout\,
	datac => \a[0]~input_o\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[56]~28_combout\);

-- Location: LCCOMB_X37_Y23_N26
\rres[0]~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \rres[0]~3_combout\ = (\op[2]~input_o\) # ((\op[1]~input_o\ & \op[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110111010101010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datab => \op[1]~input_o\,
	datad => \op[0]~input_o\,
	combout => \rres[0]~3_combout\);

-- Location: LCCOMB_X37_Y23_N0
\rres[0]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \rres[0]~2_combout\ = (!\op[2]~input_o\ & \op[1]~input_o\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0101010100000000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datad => \op[1]~input_o\,
	combout => \rres[0]~2_combout\);

-- Location: LCCOMB_X36_Y24_N2
\Mux8~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux8~0_combout\ = (\rres[0]~3_combout\ & (\a[0]~input_o\ $ (((\b[0]~input_o\) # (\rres[0]~2_combout\))))) # (!\rres[0]~3_combout\ & ((\b[0]~input_o\ & ((\a[0]~input_o\) # (\rres[0]~2_combout\))) # (!\b[0]~input_o\ & (\a[0]~input_o\ & 
-- \rres[0]~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0011111001101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \rres[0]~3_combout\,
	datac => \a[0]~input_o\,
	datad => \rres[0]~2_combout\,
	combout => \Mux8~0_combout\);

-- Location: LCCOMB_X39_Y23_N18
\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\ = (\a[5]~input_o\ & ((GND) # (!\b[0]~input_o\))) # (!\a[5]~input_o\ & (\b[0]~input_o\ $ (GND)))
-- \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\ = CARRY((\a[5]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011010111011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[5]~input_o\,
	datab => \b[0]~input_o\,
	datad => VCC,
	combout => \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\);

-- Location: LCCOMB_X39_Y23_N20
\Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\ = (\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\)) # 
-- (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\) # (GND))))) # (!\b[1]~input_o\ & ((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\ & VCC)) # (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\))))
-- \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\ = CARRY((\b[1]~input_o\ & ((!\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\) # (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\))) # (!\b[1]~input_o\ & 
-- (!\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\ & !\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~1\,
	combout => \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\);

-- Location: LCCOMB_X39_Y23_N22
\Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\ = ((\b[2]~input_o\ $ (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\ $ (\Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\ = CARRY((\b[2]~input_o\ & (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\ & !\Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\)) # (!\b[2]~input_o\ & 
-- ((\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\) # (!\Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[2]~input_o\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~3\,
	combout => \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\);

-- Location: LCCOMB_X39_Y23_N24
\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ = !\Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000111100001111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~5\,
	combout => \Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\);

-- Location: LCCOMB_X39_Y23_N26
\Div0|auto_generated|divider|divider|StageOut[18]~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[18]~1_combout\ = (\Div0|auto_generated|divider|divider|sel\(18) & (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\)) # (!\Div0|auto_generated|divider|divider|sel\(18) & 
-- ((\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\)) # (!\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & 
-- ((\Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010111000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[9]~0_combout\,
	datab => \Div0|auto_generated|divider|divider|sel\(18),
	datac => \Div0|auto_generated|divider|divider|add_sub_2_result_int[2]~4_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[18]~1_combout\);

-- Location: LCCOMB_X39_Y23_N12
\Div0|auto_generated|divider|divider|StageOut[17]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[17]~2_combout\ = (\Div0|auto_generated|divider|divider|sel\(18) & (((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\)))) # (!\Div0|auto_generated|divider|divider|sel\(18) & 
-- ((\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\))) # (!\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110011001010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_2_result_int[1]~2_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[8]~2_combout\,
	datac => \Div0|auto_generated|divider|divider|sel\(18),
	datad => \Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[17]~2_combout\);

-- Location: LCCOMB_X39_Y23_N14
\Div0|auto_generated|divider|divider|StageOut[16]~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[16]~3_combout\ = (\Div0|auto_generated|divider|divider|sel\(18) & (((\a[5]~input_o\)))) # (!\Div0|auto_generated|divider|divider|sel\(18) & 
-- ((\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & ((\a[5]~input_o\))) # (!\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\ & (\Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011100100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|sel\(18),
	datab => \Div0|auto_generated|divider|divider|add_sub_2_result_int[0]~0_combout\,
	datac => \a[5]~input_o\,
	datad => \Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[16]~3_combout\);

-- Location: LCCOMB_X35_Y23_N14
\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\ = (\b[0]~input_o\ & (\a[4]~input_o\ $ (VCC))) # (!\b[0]~input_o\ & ((\a[4]~input_o\) # (GND)))
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\ = CARRY((\a[4]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011011011101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \a[4]~input_o\,
	datad => VCC,
	combout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\);

-- Location: LCCOMB_X35_Y23_N16
\Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\ = (\b[1]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\) # (GND))))) # (!\b[1]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\ & VCC)) # (!\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\))))
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\ = CARRY((\b[1]~input_o\ & ((!\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\) # (!\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\))) # (!\b[1]~input_o\ & 
-- (!\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\ & !\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[16]~3_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~1\,
	combout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\);

-- Location: LCCOMB_X35_Y23_N18
\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\ = ((\Div0|auto_generated|divider|divider|StageOut[17]~2_combout\ $ (\b[2]~input_o\ $ (\Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[17]~2_combout\ & ((!\Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[17]~2_combout\ & (!\b[2]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[17]~2_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~3\,
	combout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\);

-- Location: LCCOMB_X35_Y23_N20
\Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\ = (\b[3]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\) # (GND))))) # (!\b[3]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\ & VCC)) # (!\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\))))
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\ = CARRY((\b[3]~input_o\ & ((!\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\) # (!\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\))) # (!\b[3]~input_o\ & 
-- (!\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\ & !\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[18]~1_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~5\,
	combout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\);

-- Location: LCCOMB_X35_Y23_N22
\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ = \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011110000",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~7\,
	combout => \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\);

-- Location: LCCOMB_X36_Y23_N16
\Div0|auto_generated|divider|divider|StageOut[27]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[27]~4_combout\ = (\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & ((\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (\Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Div0|auto_generated|divider|divider|StageOut[18]~1_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110010011110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_3_result_int[3]~6_combout\,
	datac => \Div0|auto_generated|divider|divider|StageOut[18]~1_combout\,
	datad => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[27]~4_combout\);

-- Location: LCCOMB_X36_Y23_N10
\Div0|auto_generated|divider|divider|StageOut[26]~5\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[26]~5_combout\ = (\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & (\Div0|auto_generated|divider|divider|StageOut[17]~2_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & ((\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (\Div0|auto_generated|divider|divider|StageOut[17]~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010110010101010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[17]~2_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_3_result_int[2]~4_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	datad => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[26]~5_combout\);

-- Location: LCCOMB_X36_Y23_N12
\Div0|auto_generated|divider|divider|StageOut[25]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[25]~6_combout\ = (\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & ((\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (\Div0|auto_generated|divider|divider|StageOut[16]~3_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111010010110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datac => \Div0|auto_generated|divider|divider|StageOut[16]~3_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_3_result_int[1]~2_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[25]~6_combout\);

-- Location: LCCOMB_X36_Y23_N6
\Div0|auto_generated|divider|divider|StageOut[24]~7\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[24]~7_combout\ = (\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & (((\a[4]~input_o\)))) # (!\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\ & 
-- ((\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\))) # (!\Div0|auto_generated|divider|divider|selnose[27]~3_combout\ & (\a[4]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111010010110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[27]~3_combout\,
	datac => \a[4]~input_o\,
	datad => \Div0|auto_generated|divider|divider|add_sub_3_result_int[0]~0_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[24]~7_combout\);

-- Location: LCCOMB_X36_Y23_N18
\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\ = (\b[0]~input_o\ & (\a[3]~input_o\ $ (VCC))) # (!\b[0]~input_o\ & ((\a[3]~input_o\) # (GND)))
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\ = CARRY((\a[3]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011011011101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \a[3]~input_o\,
	datad => VCC,
	combout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\);

-- Location: LCCOMB_X36_Y23_N20
\Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\ = (\Div0|auto_generated|divider|divider|StageOut[24]~7_combout\ & ((\b[1]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\)) # (!\b[1]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\ & VCC)))) # (!\Div0|auto_generated|divider|divider|StageOut[24]~7_combout\ & ((\b[1]~input_o\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\) # (GND))) # 
-- (!\b[1]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\))))
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[24]~7_combout\ & (\b[1]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[24]~7_combout\ & ((\b[1]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[24]~7_combout\,
	datab => \b[1]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~1\,
	combout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\);

-- Location: LCCOMB_X36_Y23_N22
\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\ = ((\Div0|auto_generated|divider|divider|StageOut[25]~6_combout\ $ (\b[2]~input_o\ $ (\Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[25]~6_combout\ & ((!\Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[25]~6_combout\ & (!\b[2]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[25]~6_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~3\,
	combout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\);

-- Location: LCCOMB_X36_Y23_N24
\Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\ = (\Div0|auto_generated|divider|divider|StageOut[26]~5_combout\ & ((\b[3]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\)) # (!\b[3]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\ & VCC)))) # (!\Div0|auto_generated|divider|divider|StageOut[26]~5_combout\ & ((\b[3]~input_o\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\) # (GND))) # 
-- (!\b[3]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\))))
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[26]~5_combout\ & (\b[3]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[26]~5_combout\ & ((\b[3]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[26]~5_combout\,
	datab => \b[3]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~5\,
	combout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\);

-- Location: LCCOMB_X36_Y23_N26
\Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\ = ((\b[4]~input_o\ $ (\Div0|auto_generated|divider|divider|StageOut[27]~4_combout\ $ (\Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\ = CARRY((\b[4]~input_o\ & (\Div0|auto_generated|divider|divider|StageOut[27]~4_combout\ & !\Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\)) # (!\b[4]~input_o\ & 
-- ((\Div0|auto_generated|divider|divider|StageOut[27]~4_combout\) # (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[4]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[27]~4_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~7\,
	combout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\);

-- Location: LCCOMB_X36_Y23_N28
\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ = !\Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000111100001111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~9\,
	combout => \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\);

-- Location: LCCOMB_X36_Y23_N8
\Div0|auto_generated|divider|divider|StageOut[36]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[36]~8_combout\ = (\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- (\Div0|auto_generated|divider|divider|StageOut[27]~4_combout\)) # (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (\Div0|auto_generated|divider|divider|StageOut[27]~4_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110011100100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datab => \Div0|auto_generated|divider|divider|StageOut[27]~4_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_4_result_int[4]~8_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[36]~8_combout\);

-- Location: LCCOMB_X36_Y23_N2
\Div0|auto_generated|divider|divider|StageOut[35]~9\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[35]~9_combout\ = (\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- (\Div0|auto_generated|divider|divider|StageOut[26]~5_combout\)) # (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (\Div0|auto_generated|divider|divider|StageOut[26]~5_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101011001010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[26]~5_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_4_result_int[3]~6_combout\,
	datac => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[35]~9_combout\);

-- Location: LCCOMB_X37_Y22_N0
\Div0|auto_generated|divider|divider|StageOut[34]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[34]~10_combout\ = (\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & (\Div0|auto_generated|divider|divider|StageOut[25]~6_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & ((\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (\Div0|auto_generated|divider|divider|StageOut[25]~6_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1101110010001100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datab => \Div0|auto_generated|divider|divider|StageOut[25]~6_combout\,
	datac => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_4_result_int[2]~4_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[34]~10_combout\);

-- Location: LCCOMB_X36_Y23_N4
\Div0|auto_generated|divider|divider|StageOut[33]~11\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[33]~11_combout\ = (\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- (\Div0|auto_generated|divider|divider|StageOut[24]~7_combout\)) # (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (\Div0|auto_generated|divider|divider|StageOut[24]~7_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101011001010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[24]~7_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_4_result_int[1]~2_combout\,
	datac => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[33]~11_combout\);

-- Location: LCCOMB_X36_Y23_N14
\Div0|auto_generated|divider|divider|StageOut[32]~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[32]~12_combout\ = (\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & (((\a[3]~input_o\)))) # (!\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\ & 
-- ((\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & (\Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\)) # (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\ & ((\a[3]~input_o\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110111100100000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_4_result_int[0]~0_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datac => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datad => \a[3]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[32]~12_combout\);

-- Location: LCCOMB_X37_Y22_N8
\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\ = (\b[0]~input_o\ & (\a[2]~input_o\ $ (VCC))) # (!\b[0]~input_o\ & ((\a[2]~input_o\) # (GND)))
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\ = CARRY((\a[2]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011011011101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \a[2]~input_o\,
	datad => VCC,
	combout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\);

-- Location: LCCOMB_X37_Y22_N10
\Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\ = (\Div0|auto_generated|divider|divider|StageOut[32]~12_combout\ & ((\b[1]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\)) # (!\b[1]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\ & VCC)))) # (!\Div0|auto_generated|divider|divider|StageOut[32]~12_combout\ & ((\b[1]~input_o\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\) # (GND))) # 
-- (!\b[1]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\))))
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[32]~12_combout\ & (\b[1]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[32]~12_combout\ & ((\b[1]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[32]~12_combout\,
	datab => \b[1]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~1\,
	combout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\);

-- Location: LCCOMB_X37_Y22_N12
\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\ = ((\Div0|auto_generated|divider|divider|StageOut[33]~11_combout\ $ (\b[2]~input_o\ $ (\Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[33]~11_combout\ & ((!\Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[33]~11_combout\ & (!\b[2]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[33]~11_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~3\,
	combout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\);

-- Location: LCCOMB_X37_Y22_N14
\Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\ = (\b[3]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\) # (GND))))) # (!\b[3]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\ & VCC)) # (!\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\))))
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\ = CARRY((\b[3]~input_o\ & ((!\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\) # (!\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\))) # (!\b[3]~input_o\ & 
-- (!\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\ & !\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[34]~10_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~5\,
	combout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\);

-- Location: LCCOMB_X37_Y22_N16
\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\ = ((\b[4]~input_o\ $ (\Div0|auto_generated|divider|divider|StageOut[35]~9_combout\ $ (\Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\ = CARRY((\b[4]~input_o\ & (\Div0|auto_generated|divider|divider|StageOut[35]~9_combout\ & !\Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\)) # (!\b[4]~input_o\ & 
-- ((\Div0|auto_generated|divider|divider|StageOut[35]~9_combout\) # (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[4]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[35]~9_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~7\,
	combout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\);

-- Location: LCCOMB_X37_Y22_N18
\Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\ = (\Div0|auto_generated|divider|divider|StageOut[36]~8_combout\ & ((\b[5]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\)) # (!\b[5]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\ & VCC)))) # (!\Div0|auto_generated|divider|divider|StageOut[36]~8_combout\ & ((\b[5]~input_o\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\) # (GND))) # 
-- (!\b[5]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\))))
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[36]~8_combout\ & (\b[5]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[36]~8_combout\ & ((\b[5]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[36]~8_combout\,
	datab => \b[5]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~9\,
	combout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\);

-- Location: LCCOMB_X37_Y22_N20
\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ = \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011110000",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~11\,
	combout => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\);

-- Location: LCCOMB_X37_Y22_N26
\Div0|auto_generated|divider|divider|StageOut[45]~13\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[45]~13_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- ((\Div0|auto_generated|divider|divider|StageOut[36]~8_combout\))) # (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (\Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[36]~8_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011011000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_5_result_int[5]~10_combout\,
	datac => \Div0|auto_generated|divider|divider|StageOut[36]~8_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[45]~13_combout\);

-- Location: LCCOMB_X37_Y22_N28
\Div0|auto_generated|divider|divider|StageOut[44]~14\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[44]~14_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- (\Div0|auto_generated|divider|divider|StageOut[35]~9_combout\)) # (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[35]~9_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111001011010000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datac => \Div0|auto_generated|divider|divider|StageOut[35]~9_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_5_result_int[4]~8_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[44]~14_combout\);

-- Location: LCCOMB_X37_Y22_N6
\Div0|auto_generated|divider|divider|StageOut[43]~15\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[43]~15_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & 
-- (\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\)) # (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\))))) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (\Div0|auto_generated|divider|divider|StageOut[34]~10_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110011100100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Div0|auto_generated|divider|divider|StageOut[34]~10_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_5_result_int[3]~6_combout\,
	datad => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[43]~15_combout\);

-- Location: LCCOMB_X37_Y22_N22
\Div0|auto_generated|divider|divider|StageOut[42]~16\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[42]~16_combout\ = (\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[33]~11_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & ((\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (\Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Div0|auto_generated|divider|divider|StageOut[33]~11_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110001011110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_5_result_int[2]~4_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datac => \Div0|auto_generated|divider|divider|StageOut[33]~11_combout\,
	datad => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[42]~16_combout\);

-- Location: LCCOMB_X37_Y22_N24
\Div0|auto_generated|divider|divider|StageOut[41]~17\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[41]~17_combout\ = (\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[32]~12_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & ((\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (\Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Div0|auto_generated|divider|divider|StageOut[32]~12_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110001011110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_5_result_int[1]~2_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datac => \Div0|auto_generated|divider|divider|StageOut[32]~12_combout\,
	datad => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	combout => \Div0|auto_generated|divider|divider|StageOut[41]~17_combout\);

-- Location: LCCOMB_X37_Y22_N2
\Div0|auto_generated|divider|divider|StageOut[40]~18\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[40]~18_combout\ = (\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & ((\a[2]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\ & (\Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\)))) # (!\Div0|auto_generated|divider|divider|selnose[45]~6_combout\ & (((\a[2]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110100100000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[45]~6_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_5_result_int[0]~0_combout\,
	datad => \a[2]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[40]~18_combout\);

-- Location: LCCOMB_X36_Y22_N0
\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\ = (\a[1]~input_o\ & ((GND) # (!\b[0]~input_o\))) # (!\a[1]~input_o\ & (\b[0]~input_o\ $ (GND)))
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\ = CARRY((\a[1]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110011010111011",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[1]~input_o\,
	datab => \b[0]~input_o\,
	datad => VCC,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\);

-- Location: LCCOMB_X36_Y22_N2
\Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\ = (\Div0|auto_generated|divider|divider|StageOut[40]~18_combout\ & ((\b[1]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\)) # (!\b[1]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\ & VCC)))) # (!\Div0|auto_generated|divider|divider|StageOut[40]~18_combout\ & ((\b[1]~input_o\ & ((\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\) # (GND))) # 
-- (!\b[1]~input_o\ & (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\))))
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[40]~18_combout\ & (\b[1]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[40]~18_combout\ & ((\b[1]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100101001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[40]~18_combout\,
	datab => \b[1]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~1\,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\);

-- Location: LCCOMB_X36_Y22_N4
\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\ = ((\Div0|auto_generated|divider|divider|StageOut[41]~17_combout\ $ (\b[2]~input_o\ $ (\Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[41]~17_combout\ & ((!\Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\) # (!\b[2]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[41]~17_combout\ & (!\b[2]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[41]~17_combout\,
	datab => \b[2]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~3\,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\);

-- Location: LCCOMB_X36_Y22_N6
\Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\ = (\b[3]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\) # (GND))))) # (!\b[3]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\ & VCC)) # (!\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\))))
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\ = CARRY((\b[3]~input_o\ & ((!\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\) # (!\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\))) # (!\b[3]~input_o\ & 
-- (!\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\ & !\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[3]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[42]~16_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~5\,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\);

-- Location: LCCOMB_X36_Y22_N8
\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\ = ((\Div0|auto_generated|divider|divider|StageOut[43]~15_combout\ $ (\b[4]~input_o\ $ (\Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[43]~15_combout\ & ((!\Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\) # (!\b[4]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[43]~15_combout\ & (!\b[4]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[43]~15_combout\,
	datab => \b[4]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~7\,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\);

-- Location: LCCOMB_X36_Y22_N10
\Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~10\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\ = (\b[5]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\ & ((\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\) # (GND))))) # (!\b[5]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\ & VCC)) # (!\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\ & (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\))))
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\ = CARRY((\b[5]~input_o\ & ((!\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\) # (!\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\))) # (!\b[5]~input_o\ & 
-- (!\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\ & !\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100100101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[5]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[44]~14_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~9\,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\);

-- Location: LCCOMB_X36_Y22_N12
\Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\ = ((\b[6]~input_o\ $ (\Div0|auto_generated|divider|divider|StageOut[45]~13_combout\ $ (\Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\)))) # (GND)
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\ = CARRY((\b[6]~input_o\ & (\Div0|auto_generated|divider|divider|StageOut[45]~13_combout\ & !\Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\)) # (!\b[6]~input_o\ & 
-- ((\Div0|auto_generated|divider|divider|StageOut[45]~13_combout\) # (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[6]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[45]~13_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~11\,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\);

-- Location: LCCOMB_X36_Y22_N14
\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ = !\Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000111100001111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~13\,
	combout => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\);

-- Location: LCCOMB_X36_Y22_N24
\Div0|auto_generated|divider|divider|StageOut[54]~19\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[54]~19_combout\ = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[45]~13_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[45]~13_combout\))) # (!\b[7]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110011001010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_6_result_int[6]~12_combout\,
	datab => \Div0|auto_generated|divider|divider|StageOut[45]~13_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[54]~19_combout\);

-- Location: LCCOMB_X36_Y22_N26
\Div0|auto_generated|divider|divider|StageOut[53]~20\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[53]~20_combout\ = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[44]~14_combout\))) # (!\b[7]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110011001010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_6_result_int[5]~10_combout\,
	datab => \Div0|auto_generated|divider|divider|StageOut[44]~14_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[53]~20_combout\);

-- Location: LCCOMB_X36_Y22_N20
\Div0|auto_generated|divider|divider|StageOut[52]~21\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[52]~21_combout\ = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (\Div0|auto_generated|divider|divider|StageOut[43]~15_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & (\Div0|auto_generated|divider|divider|StageOut[43]~15_combout\)) # (!\b[7]~input_o\ & 
-- ((\Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010101100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[43]~15_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_6_result_int[4]~8_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[52]~21_combout\);

-- Location: LCCOMB_X36_Y22_N30
\Div0|auto_generated|divider|divider|StageOut[51]~22\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[51]~22_combout\ = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (((\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\)))) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & ((\Div0|auto_generated|divider|divider|StageOut[42]~16_combout\))) # (!\b[7]~input_o\ & 
-- (\Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110011001010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_6_result_int[3]~6_combout\,
	datab => \Div0|auto_generated|divider|divider|StageOut[42]~16_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[51]~22_combout\);

-- Location: LCCOMB_X36_Y22_N16
\Div0|auto_generated|divider|divider|StageOut[50]~23\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[50]~23_combout\ = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (\Div0|auto_generated|divider|divider|StageOut[41]~17_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & (\Div0|auto_generated|divider|divider|StageOut[41]~17_combout\)) # (!\b[7]~input_o\ & 
-- ((\Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010101100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[41]~17_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_6_result_int[2]~4_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[50]~23_combout\);

-- Location: LCCOMB_X36_Y22_N18
\Div0|auto_generated|divider|divider|StageOut[49]~24\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[49]~24_combout\ = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (\Div0|auto_generated|divider|divider|StageOut[40]~18_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & (\Div0|auto_generated|divider|divider|StageOut[40]~18_combout\)) # (!\b[7]~input_o\ & 
-- ((\Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010101100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[40]~18_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_6_result_int[1]~2_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[49]~24_combout\);

-- Location: LCCOMB_X36_Y22_N28
\Div0|auto_generated|divider|divider|StageOut[48]~25\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|StageOut[48]~25_combout\ = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & (\a[1]~input_o\)) # (!\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\ & ((\b[7]~input_o\ & 
-- (\a[1]~input_o\)) # (!\b[7]~input_o\ & ((\Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101010101100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[1]~input_o\,
	datab => \Div0|auto_generated|divider|divider|add_sub_6_result_int[0]~0_combout\,
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|StageOut[48]~25_combout\);

-- Location: LCCOMB_X36_Y24_N4
\Div0|auto_generated|divider|divider|add_sub_7_result_int[0]~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[0]~1_cout\ = CARRY((\a[0]~input_o\) # (!\b[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000011011101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \a[0]~input_o\,
	datad => VCC,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[0]~1_cout\);

-- Location: LCCOMB_X36_Y24_N6
\Div0|auto_generated|divider|divider|add_sub_7_result_int[1]~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[1]~3_cout\ = CARRY((\b[1]~input_o\ & ((!\Div0|auto_generated|divider|divider|add_sub_7_result_int[0]~1_cout\) # (!\Div0|auto_generated|divider|divider|StageOut[48]~25_combout\))) # (!\b[1]~input_o\ 
-- & (!\Div0|auto_generated|divider|divider|StageOut[48]~25_combout\ & !\Div0|auto_generated|divider|divider|add_sub_7_result_int[0]~1_cout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[48]~25_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[0]~1_cout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[1]~3_cout\);

-- Location: LCCOMB_X36_Y24_N8
\Div0|auto_generated|divider|divider|add_sub_7_result_int[2]~5\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[2]~5_cout\ = CARRY((\b[2]~input_o\ & (\Div0|auto_generated|divider|divider|StageOut[49]~24_combout\ & !\Div0|auto_generated|divider|divider|add_sub_7_result_int[1]~3_cout\)) # (!\b[2]~input_o\ & 
-- ((\Div0|auto_generated|divider|divider|StageOut[49]~24_combout\) # (!\Div0|auto_generated|divider|divider|add_sub_7_result_int[1]~3_cout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \b[2]~input_o\,
	datab => \Div0|auto_generated|divider|divider|StageOut[49]~24_combout\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[1]~3_cout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[2]~5_cout\);

-- Location: LCCOMB_X36_Y24_N10
\Div0|auto_generated|divider|divider|add_sub_7_result_int[3]~7\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[3]~7_cout\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[50]~23_combout\ & (\b[3]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_7_result_int[2]~5_cout\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[50]~23_combout\ & ((\b[3]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_7_result_int[2]~5_cout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[50]~23_combout\,
	datab => \b[3]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[2]~5_cout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[3]~7_cout\);

-- Location: LCCOMB_X36_Y24_N12
\Div0|auto_generated|divider|divider|add_sub_7_result_int[4]~9\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[4]~9_cout\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[51]~22_combout\ & ((!\Div0|auto_generated|divider|divider|add_sub_7_result_int[3]~7_cout\) # (!\b[4]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[51]~22_combout\ & (!\b[4]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_7_result_int[3]~7_cout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[51]~22_combout\,
	datab => \b[4]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[3]~7_cout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[4]~9_cout\);

-- Location: LCCOMB_X36_Y24_N14
\Div0|auto_generated|divider|divider|add_sub_7_result_int[5]~11\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[5]~11_cout\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[52]~21_combout\ & (\b[5]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_7_result_int[4]~9_cout\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[52]~21_combout\ & ((\b[5]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_7_result_int[4]~9_cout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[52]~21_combout\,
	datab => \b[5]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[4]~9_cout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[5]~11_cout\);

-- Location: LCCOMB_X36_Y24_N16
\Div0|auto_generated|divider|divider|add_sub_7_result_int[6]~13\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[6]~13_cout\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[53]~20_combout\ & ((!\Div0|auto_generated|divider|divider|add_sub_7_result_int[5]~11_cout\) # (!\b[6]~input_o\))) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[53]~20_combout\ & (!\b[6]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_7_result_int[5]~11_cout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000101011",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[53]~20_combout\,
	datab => \b[6]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[5]~11_cout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[6]~13_cout\);

-- Location: LCCOMB_X36_Y24_N18
\Div0|auto_generated|divider|divider|add_sub_7_result_int[7]~15\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[7]~15_cout\ = CARRY((\Div0|auto_generated|divider|divider|StageOut[54]~19_combout\ & (\b[7]~input_o\ & !\Div0|auto_generated|divider|divider|add_sub_7_result_int[6]~13_cout\)) # 
-- (!\Div0|auto_generated|divider|divider|StageOut[54]~19_combout\ & ((\b[7]~input_o\) # (!\Div0|auto_generated|divider|divider|add_sub_7_result_int[6]~13_cout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000001001101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|StageOut[54]~19_combout\,
	datab => \b[7]~input_o\,
	datad => VCC,
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[6]~13_cout\,
	cout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[7]~15_cout\);

-- Location: LCCOMB_X36_Y24_N20
\Div0|auto_generated|divider|divider|add_sub_7_result_int[8]~16\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ = \Div0|auto_generated|divider|divider|add_sub_7_result_int[7]~15_cout\

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011110000",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	cin => \Div0|auto_generated|divider|divider|add_sub_7_result_int[7]~15_cout\,
	combout => \Div0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\);

-- Location: LCCOMB_X37_Y23_N22
\rres[0]~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \rres[0]~1_combout\ = (\op[3]~input_o\ & ((\op[2]~input_o\ & (!\op[1]~input_o\)) # (!\op[2]~input_o\ & (\op[1]~input_o\ & \op[0]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110000000100000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datab => \op[1]~input_o\,
	datac => \op[3]~input_o\,
	datad => \op[0]~input_o\,
	combout => \rres[0]~1_combout\);

-- Location: LCCOMB_X37_Y24_N22
\Mux8~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux8~1_combout\ = (\rres[0]~1_combout\ & (((\rres[0]~0_combout\) # (!\Div0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\)))) # (!\rres[0]~1_combout\ & (\Mux8~0_combout\ & ((!\rres[0]~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000000111010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux8~0_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datac => \rres[0]~1_combout\,
	datad => \rres[0]~0_combout\,
	combout => \Mux8~1_combout\);

-- Location: LCCOMB_X39_Y24_N0
\Add0~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~0_combout\ = (\op[2]~input_o\) # (\b[0]~input_o\ $ (\op[1]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1101110111101110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \op[2]~input_o\,
	datad => \op[1]~input_o\,
	combout => \Add0~0_combout\);

-- Location: LCCOMB_X38_Y24_N4
\Add0~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~2_cout\ = CARRY((!\op[2]~input_o\ & !\op[0]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000010001",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datab => \op[0]~input_o\,
	datad => VCC,
	cout => \Add0~2_cout\);

-- Location: LCCOMB_X38_Y24_N6
\Add0~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~3_combout\ = (\a[0]~input_o\ & ((\Add0~0_combout\ & (\Add0~2_cout\ & VCC)) # (!\Add0~0_combout\ & (!\Add0~2_cout\)))) # (!\a[0]~input_o\ & ((\Add0~0_combout\ & (!\Add0~2_cout\)) # (!\Add0~0_combout\ & ((\Add0~2_cout\) # (GND)))))
-- \Add0~4\ = CARRY((\a[0]~input_o\ & (!\Add0~0_combout\ & !\Add0~2_cout\)) # (!\a[0]~input_o\ & ((!\Add0~2_cout\) # (!\Add0~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000010111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \a[0]~input_o\,
	datab => \Add0~0_combout\,
	datad => VCC,
	cin => \Add0~2_cout\,
	combout => \Add0~3_combout\,
	cout => \Add0~4\);

-- Location: LCCOMB_X37_Y24_N18
\Mux8~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux8~2_combout\ = (\rres[0]~0_combout\ & ((\Mux8~1_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[56]~28_combout\)) # (!\Mux8~1_combout\ & ((\Add0~3_combout\))))) # (!\rres[0]~0_combout\ & (((\Mux8~1_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1101101011010000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[56]~28_combout\,
	datac => \Mux8~1_combout\,
	datad => \Add0~3_combout\,
	combout => \Mux8~2_combout\);

-- Location: LCCOMB_X37_Y24_N0
\Mux8~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux8~3_combout\ = (\rres[0]~4_combout\ & (((!\a[0]~input_o\ & !\b[0]~input_o\)))) # (!\rres[0]~4_combout\ & (\Mux8~2_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0100010001001110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~4_combout\,
	datab => \Mux8~2_combout\,
	datac => \a[0]~input_o\,
	datad => \b[0]~input_o\,
	combout => \Mux8~3_combout\);

-- Location: LCCOMB_X37_Y23_N6
\rres[0]~5\ : cycloneiii_lcell_comb
-- Equation(s):
-- \rres[0]~5_combout\ = (\op[2]~input_o\ & ((\op[1]~input_o\ & (\op[3]~input_o\)) # (!\op[1]~input_o\ & ((!\op[0]~input_o\) # (!\op[3]~input_o\))))) # (!\op[2]~input_o\ & ((\op[1]~input_o\) # ((\op[0]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1101011111100110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datab => \op[1]~input_o\,
	datac => \op[3]~input_o\,
	datad => \op[0]~input_o\,
	combout => \rres[0]~5_combout\);

-- Location: FF_X37_Y24_N1
\rres[0]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux8~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(0));

-- Location: LCCOMB_X37_Y23_N24
\Mux7~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux7~0_combout\ = (\rres[0]~3_combout\ & (\a[1]~input_o\ $ (((\b[1]~input_o\) # (\rres[0]~2_combout\))))) # (!\rres[0]~3_combout\ & ((\b[1]~input_o\ & ((\rres[0]~2_combout\) # (\a[1]~input_o\))) # (!\b[1]~input_o\ & (\rres[0]~2_combout\ & 
-- \a[1]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0001111011101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[1]~input_o\,
	datab => \rres[0]~2_combout\,
	datac => \rres[0]~3_combout\,
	datad => \a[1]~input_o\,
	combout => \Mux7~0_combout\);

-- Location: LCCOMB_X38_Y24_N24
\Add0~5\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~5_combout\ = (\op[2]~input_o\ & (((\op[0]~input_o\)))) # (!\op[2]~input_o\ & (\op[1]~input_o\ $ ((\b[1]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011111000010100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datab => \op[1]~input_o\,
	datac => \b[1]~input_o\,
	datad => \op[0]~input_o\,
	combout => \Add0~5_combout\);

-- Location: LCCOMB_X38_Y24_N8
\Add0~6\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~6_combout\ = ((\a[1]~input_o\ $ (\Add0~5_combout\ $ (!\Add0~4\)))) # (GND)
-- \Add0~7\ = CARRY((\a[1]~input_o\ & ((\Add0~5_combout\) # (!\Add0~4\))) # (!\a[1]~input_o\ & (\Add0~5_combout\ & !\Add0~4\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100110001110",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \a[1]~input_o\,
	datab => \Add0~5_combout\,
	datad => VCC,
	cin => \Add0~4\,
	combout => \Add0~6_combout\,
	cout => \Add0~7\);

-- Location: LCCOMB_X37_Y23_N10
\Mux7~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux7~1_combout\ = (\rres[0]~1_combout\ & (((\rres[0]~0_combout\)))) # (!\rres[0]~1_combout\ & ((\rres[0]~0_combout\ & ((\Add0~6_combout\))) # (!\rres[0]~0_combout\ & (\Mux7~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111101001000100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~1_combout\,
	datab => \Mux7~0_combout\,
	datac => \Add0~6_combout\,
	datad => \rres[0]~0_combout\,
	combout => \Mux7~1_combout\);

-- Location: LCCOMB_X36_Y22_N22
\Div0|auto_generated|divider|divider|selnose[54]\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose\(54) = (\Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\) # (\b[7]~input_o\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111111110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datac => \Div0|auto_generated|divider|divider|add_sub_6_result_int[7]~14_combout\,
	datad => \b[7]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose\(54));

-- Location: LCCOMB_X38_Y22_N0
\Mod0|auto_generated|divider|divider|StageOut[57]~29\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[57]~29_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~2_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110111000100010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[1]~2_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[48]~27_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[57]~29_combout\);

-- Location: LCCOMB_X37_Y23_N28
\Mux7~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux7~2_combout\ = (\Mux7~1_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[57]~29_combout\) # (!\rres[0]~1_combout\)))) # (!\Mux7~1_combout\ & (!\Div0|auto_generated|divider|divider|selnose\(54) & (\rres[0]~1_combout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011101000011010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux7~1_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose\(54),
	datac => \rres[0]~1_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[57]~29_combout\,
	combout => \Mux7~2_combout\);

-- Location: LCCOMB_X37_Y23_N8
\Mux7~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux7~3_combout\ = (\rres[0]~4_combout\ & (((!\b[1]~input_o\ & !\a[1]~input_o\)))) # (!\rres[0]~4_combout\ & (\Mux7~2_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0100010001001110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~4_combout\,
	datab => \Mux7~2_combout\,
	datac => \b[1]~input_o\,
	datad => \a[1]~input_o\,
	combout => \Mux7~3_combout\);

-- Location: FF_X37_Y23_N9
\rres[1]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux7~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(1));

-- Location: LCCOMB_X37_Y22_N4
\Div0|auto_generated|divider|divider|selnose[45]\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose\(45) = (\b[7]~input_o\) # ((\Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\) # (\b[6]~input_o\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111111111100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \b[7]~input_o\,
	datac => \Div0|auto_generated|divider|divider|add_sub_5_result_int[6]~12_combout\,
	datad => \b[6]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose\(45));

-- Location: LCCOMB_X36_Y24_N30
\Mux6~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux6~0_combout\ = (\rres[0]~3_combout\ & (\a[2]~input_o\ $ (((\b[2]~input_o\) # (\rres[0]~2_combout\))))) # (!\rres[0]~3_combout\ & ((\b[2]~input_o\ & ((\rres[0]~2_combout\) # (\a[2]~input_o\))) # (!\b[2]~input_o\ & (\rres[0]~2_combout\ & 
-- \a[2]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0001111011101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[2]~input_o\,
	datab => \rres[0]~2_combout\,
	datac => \rres[0]~3_combout\,
	datad => \a[2]~input_o\,
	combout => \Mux6~0_combout\);

-- Location: LCCOMB_X37_Y23_N14
\Mux6~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux6~1_combout\ = (\rres[0]~1_combout\ & (((\rres[0]~0_combout\)) # (!\Div0|auto_generated|divider|divider|selnose\(45)))) # (!\rres[0]~1_combout\ & (((\Mux6~0_combout\ & !\rres[0]~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010101001110010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~1_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose\(45),
	datac => \Mux6~0_combout\,
	datad => \rres[0]~0_combout\,
	combout => \Mux6~1_combout\);

-- Location: LCCOMB_X38_Y24_N26
\Add0~8\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~8_combout\ = (\op[2]~input_o\ & (((\op[0]~input_o\)))) # (!\op[2]~input_o\ & (\op[1]~input_o\ $ ((\b[2]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011111000010100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datab => \op[1]~input_o\,
	datac => \b[2]~input_o\,
	datad => \op[0]~input_o\,
	combout => \Add0~8_combout\);

-- Location: LCCOMB_X38_Y24_N10
\Add0~9\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~9_combout\ = (\Add0~8_combout\ & ((\a[2]~input_o\ & (\Add0~7\ & VCC)) # (!\a[2]~input_o\ & (!\Add0~7\)))) # (!\Add0~8_combout\ & ((\a[2]~input_o\ & (!\Add0~7\)) # (!\a[2]~input_o\ & ((\Add0~7\) # (GND)))))
-- \Add0~10\ = CARRY((\Add0~8_combout\ & (!\a[2]~input_o\ & !\Add0~7\)) # (!\Add0~8_combout\ & ((!\Add0~7\) # (!\a[2]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000010111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Add0~8_combout\,
	datab => \a[2]~input_o\,
	datad => VCC,
	cin => \Add0~7\,
	combout => \Add0~9_combout\,
	cout => \Add0~10\);

-- Location: LCCOMB_X38_Y22_N26
\Mod0|auto_generated|divider|divider|StageOut[58]~30\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[58]~30_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~4_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110111000100010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[2]~4_combout\,
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[49]~26_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[58]~30_combout\);

-- Location: LCCOMB_X37_Y23_N16
\Mux6~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux6~2_combout\ = (\rres[0]~0_combout\ & ((\Mux6~1_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[58]~30_combout\))) # (!\Mux6~1_combout\ & (\Add0~9_combout\)))) # (!\rres[0]~0_combout\ & (\Mux6~1_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110110001100100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \Mux6~1_combout\,
	datac => \Add0~9_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[58]~30_combout\,
	combout => \Mux6~2_combout\);

-- Location: LCCOMB_X37_Y23_N18
\Mux6~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux6~3_combout\ = (\rres[0]~4_combout\ & (!\b[2]~input_o\ & ((!\a[2]~input_o\)))) # (!\rres[0]~4_combout\ & (((\Mux6~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000110001011100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[2]~input_o\,
	datab => \Mux6~2_combout\,
	datac => \rres[0]~4_combout\,
	datad => \a[2]~input_o\,
	combout => \Mux6~3_combout\);

-- Location: FF_X37_Y23_N19
\rres[2]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux6~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(2));

-- Location: LCCOMB_X37_Y24_N10
\Div0|auto_generated|divider|divider|selnose[36]\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose\(36) = (\Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\) # ((\b[5]~input_o\) # ((\b[7]~input_o\) # (\b[6]~input_o\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111111111110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_4_result_int[5]~10_combout\,
	datab => \b[5]~input_o\,
	datac => \b[7]~input_o\,
	datad => \b[6]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose\(36));

-- Location: LCCOMB_X38_Y22_N4
\Mod0|auto_generated|divider|divider|StageOut[59]~31\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[59]~31_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~6_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110000110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[3]~6_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[50]~25_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[59]~31_combout\);

-- Location: LCCOMB_X38_Y24_N30
\Add0~11\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~11_combout\ = (\op[2]~input_o\ & (((\op[0]~input_o\)))) # (!\op[2]~input_o\ & (\op[1]~input_o\ $ ((\b[3]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011111000010100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[2]~input_o\,
	datab => \op[1]~input_o\,
	datac => \b[3]~input_o\,
	datad => \op[0]~input_o\,
	combout => \Add0~11_combout\);

-- Location: LCCOMB_X38_Y24_N12
\Add0~12\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~12_combout\ = ((\Add0~11_combout\ $ (\a[3]~input_o\ $ (!\Add0~10\)))) # (GND)
-- \Add0~13\ = CARRY((\Add0~11_combout\ & ((\a[3]~input_o\) # (!\Add0~10\))) # (!\Add0~11_combout\ & (\a[3]~input_o\ & !\Add0~10\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100110001110",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \Add0~11_combout\,
	datab => \a[3]~input_o\,
	datad => VCC,
	cin => \Add0~10\,
	combout => \Add0~12_combout\,
	cout => \Add0~13\);

-- Location: LCCOMB_X37_Y24_N20
\Mux5~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux5~0_combout\ = (\rres[0]~3_combout\ & (\a[3]~input_o\ $ (((\rres[0]~2_combout\) # (\b[3]~input_o\))))) # (!\rres[0]~3_combout\ & ((\rres[0]~2_combout\ & ((\b[3]~input_o\) # (\a[3]~input_o\))) # (!\rres[0]~2_combout\ & (\b[3]~input_o\ & 
-- \a[3]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0101011011101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~3_combout\,
	datab => \rres[0]~2_combout\,
	datac => \b[3]~input_o\,
	datad => \a[3]~input_o\,
	combout => \Mux5~0_combout\);

-- Location: LCCOMB_X37_Y24_N6
\Mux5~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux5~1_combout\ = (\rres[0]~0_combout\ & ((\rres[0]~1_combout\) # ((\Add0~12_combout\)))) # (!\rres[0]~0_combout\ & (!\rres[0]~1_combout\ & ((\Mux5~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011100110101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \rres[0]~1_combout\,
	datac => \Add0~12_combout\,
	datad => \Mux5~0_combout\,
	combout => \Mux5~1_combout\);

-- Location: LCCOMB_X37_Y24_N24
\Mux5~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux5~2_combout\ = (\rres[0]~1_combout\ & ((\Mux5~1_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[59]~31_combout\))) # (!\Mux5~1_combout\ & (!\Div0|auto_generated|divider|divider|selnose\(36))))) # (!\rres[0]~1_combout\ & 
-- (((\Mux5~1_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100111101010000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose\(36),
	datab => \Mod0|auto_generated|divider|divider|StageOut[59]~31_combout\,
	datac => \rres[0]~1_combout\,
	datad => \Mux5~1_combout\,
	combout => \Mux5~2_combout\);

-- Location: LCCOMB_X37_Y24_N2
\Mux5~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux5~3_combout\ = (\rres[0]~4_combout\ & (!\a[3]~input_o\ & (!\b[3]~input_o\))) # (!\rres[0]~4_combout\ & (((\Mux5~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0101011100000010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~4_combout\,
	datab => \a[3]~input_o\,
	datac => \b[3]~input_o\,
	datad => \Mux5~2_combout\,
	combout => \Mux5~3_combout\);

-- Location: FF_X37_Y24_N3
\rres[3]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux5~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(3));

-- Location: LCCOMB_X38_Y22_N6
\Mod0|auto_generated|divider|divider|StageOut[60]~32\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[60]~32_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~8_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111000011001100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[4]~8_combout\,
	datac => \Mod0|auto_generated|divider|divider|StageOut[51]~24_combout\,
	datad => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[60]~32_combout\);

-- Location: LCCOMB_X38_Y24_N0
\Add0~14\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~14_combout\ = (\op[2]~input_o\ & (((\op[0]~input_o\)))) # (!\op[2]~input_o\ & (\b[4]~input_o\ $ ((\op[1]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111011000000110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[4]~input_o\,
	datab => \op[1]~input_o\,
	datac => \op[2]~input_o\,
	datad => \op[0]~input_o\,
	combout => \Add0~14_combout\);

-- Location: LCCOMB_X38_Y24_N14
\Add0~15\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~15_combout\ = (\a[4]~input_o\ & ((\Add0~14_combout\ & (\Add0~13\ & VCC)) # (!\Add0~14_combout\ & (!\Add0~13\)))) # (!\a[4]~input_o\ & ((\Add0~14_combout\ & (!\Add0~13\)) # (!\Add0~14_combout\ & ((\Add0~13\) # (GND)))))
-- \Add0~16\ = CARRY((\a[4]~input_o\ & (!\Add0~14_combout\ & !\Add0~13\)) # (!\a[4]~input_o\ & ((!\Add0~13\) # (!\Add0~14_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000010111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \a[4]~input_o\,
	datab => \Add0~14_combout\,
	datad => VCC,
	cin => \Add0~13\,
	combout => \Add0~15_combout\,
	cout => \Add0~16\);

-- Location: LCCOMB_X36_Y23_N0
\Div0|auto_generated|divider|divider|selnose[27]\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose\(27) = ((\b[4]~input_o\) # (\Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\)) # (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111111110101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datac => \b[4]~input_o\,
	datad => \Div0|auto_generated|divider|divider|add_sub_3_result_int[4]~8_combout\,
	combout => \Div0|auto_generated|divider|divider|selnose\(27));

-- Location: LCCOMB_X38_Y23_N26
\Mux4~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux4~0_combout\ = (\rres[0]~3_combout\ & (\a[4]~input_o\ $ (((\rres[0]~2_combout\) # (\b[4]~input_o\))))) # (!\rres[0]~3_combout\ & ((\rres[0]~2_combout\ & ((\b[4]~input_o\) # (\a[4]~input_o\))) # (!\rres[0]~2_combout\ & (\b[4]~input_o\ & 
-- \a[4]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0001111011101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~2_combout\,
	datab => \b[4]~input_o\,
	datac => \rres[0]~3_combout\,
	datad => \a[4]~input_o\,
	combout => \Mux4~0_combout\);

-- Location: LCCOMB_X38_Y23_N20
\Mux4~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux4~1_combout\ = (\rres[0]~1_combout\ & (((\rres[0]~0_combout\)) # (!\Div0|auto_generated|divider|divider|selnose\(27)))) # (!\rres[0]~1_combout\ & (((\Mux4~0_combout\ & !\rres[0]~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1100110001110100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose\(27),
	datab => \rres[0]~1_combout\,
	datac => \Mux4~0_combout\,
	datad => \rres[0]~0_combout\,
	combout => \Mux4~1_combout\);

-- Location: LCCOMB_X38_Y23_N14
\Mux4~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux4~2_combout\ = (\rres[0]~0_combout\ & ((\Mux4~1_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[60]~32_combout\)) # (!\Mux4~1_combout\ & ((\Add0~15_combout\))))) # (!\rres[0]~0_combout\ & (((\Mux4~1_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1101110110100000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \Mod0|auto_generated|divider|divider|StageOut[60]~32_combout\,
	datac => \Add0~15_combout\,
	datad => \Mux4~1_combout\,
	combout => \Mux4~2_combout\);

-- Location: LCCOMB_X38_Y23_N16
\Mux4~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux4~3_combout\ = (\rres[0]~4_combout\ & (!\b[4]~input_o\ & ((!\a[4]~input_o\)))) # (!\rres[0]~4_combout\ & (((\Mux4~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000110001011100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[4]~input_o\,
	datab => \Mux4~2_combout\,
	datac => \rres[0]~4_combout\,
	datad => \a[4]~input_o\,
	combout => \Mux4~3_combout\);

-- Location: FF_X38_Y23_N17
\rres[4]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux4~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(4));

-- Location: LCCOMB_X38_Y22_N2
\Mod0|auto_generated|divider|divider|StageOut[61]~33\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[61]~33_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~10_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110000110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[5]~10_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[52]~23_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[61]~33_combout\);

-- Location: LCCOMB_X38_Y24_N2
\Add0~17\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~17_combout\ = (\op[2]~input_o\ & (((\op[0]~input_o\)))) # (!\op[2]~input_o\ & (\b[5]~input_o\ $ ((\op[1]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111011000000110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[5]~input_o\,
	datab => \op[1]~input_o\,
	datac => \op[2]~input_o\,
	datad => \op[0]~input_o\,
	combout => \Add0~17_combout\);

-- Location: LCCOMB_X38_Y24_N16
\Add0~18\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~18_combout\ = ((\a[5]~input_o\ $ (\Add0~17_combout\ $ (!\Add0~16\)))) # (GND)
-- \Add0~19\ = CARRY((\a[5]~input_o\ & ((\Add0~17_combout\) # (!\Add0~16\))) # (!\a[5]~input_o\ & (\Add0~17_combout\ & !\Add0~16\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0110100110001110",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \a[5]~input_o\,
	datab => \Add0~17_combout\,
	datad => VCC,
	cin => \Add0~16\,
	combout => \Add0~18_combout\,
	cout => \Add0~19\);

-- Location: LCCOMB_X38_Y23_N2
\Mux3~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux3~0_combout\ = (\rres[0]~3_combout\ & (\a[5]~input_o\ $ (((\rres[0]~2_combout\) # (\b[5]~input_o\))))) # (!\rres[0]~3_combout\ & ((\rres[0]~2_combout\ & ((\b[5]~input_o\) # (\a[5]~input_o\))) # (!\rres[0]~2_combout\ & (\b[5]~input_o\ & 
-- \a[5]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0001111011101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~2_combout\,
	datab => \b[5]~input_o\,
	datac => \rres[0]~3_combout\,
	datad => \a[5]~input_o\,
	combout => \Mux3~0_combout\);

-- Location: LCCOMB_X38_Y23_N4
\Mux3~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux3~1_combout\ = (\rres[0]~0_combout\ & ((\rres[0]~1_combout\) # ((\Add0~18_combout\)))) # (!\rres[0]~0_combout\ & (!\rres[0]~1_combout\ & ((\Mux3~0_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011100110101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \rres[0]~1_combout\,
	datac => \Add0~18_combout\,
	datad => \Mux3~0_combout\,
	combout => \Mux3~1_combout\);

-- Location: LCCOMB_X38_Y23_N8
\Div0|auto_generated|divider|divider|selnose[18]\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose\(18) = ((\Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\) # ((\b[4]~input_o\) # (\b[3]~input_o\))) # (!\Div0|auto_generated|divider|divider|selnose[36]~5_combout\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111111111111101",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|selnose[36]~5_combout\,
	datab => \Div0|auto_generated|divider|divider|add_sub_2_result_int[3]~6_combout\,
	datac => \b[4]~input_o\,
	datad => \b[3]~input_o\,
	combout => \Div0|auto_generated|divider|divider|selnose\(18));

-- Location: LCCOMB_X38_Y23_N22
\Mux3~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux3~2_combout\ = (\Mux3~1_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[61]~33_combout\) # ((!\rres[0]~1_combout\)))) # (!\Mux3~1_combout\ & (((!\Div0|auto_generated|divider|divider|selnose\(18) & \rres[0]~1_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1000101111001100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mod0|auto_generated|divider|divider|StageOut[61]~33_combout\,
	datab => \Mux3~1_combout\,
	datac => \Div0|auto_generated|divider|divider|selnose\(18),
	datad => \rres[0]~1_combout\,
	combout => \Mux3~2_combout\);

-- Location: LCCOMB_X38_Y23_N10
\Mux3~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux3~3_combout\ = (\rres[0]~4_combout\ & (((!\b[5]~input_o\ & !\a[5]~input_o\)))) # (!\rres[0]~4_combout\ & (\Mux3~2_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000101000111010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux3~2_combout\,
	datab => \b[5]~input_o\,
	datac => \rres[0]~4_combout\,
	datad => \a[5]~input_o\,
	combout => \Mux3~3_combout\);

-- Location: FF_X38_Y23_N11
\rres[5]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux3~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(5));

-- Location: LCCOMB_X35_Y23_N26
\Div0|auto_generated|divider|divider|selnose[9]~7\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Div0|auto_generated|divider|divider|selnose[9]~7_combout\ = ((\Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\ & (\b[1]~input_o\ & !\Div0|auto_generated|divider|divider|StageOut[0]~0_combout\)) # 
-- (!\Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\ & ((\b[1]~input_o\) # (!\Div0|auto_generated|divider|divider|StageOut[0]~0_combout\)))) # (!\Div0|auto_generated|divider|divider|selnose[0]~4_combout\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0111001111110111",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Div0|auto_generated|divider|divider|add_sub_1|_~0_combout\,
	datab => \Div0|auto_generated|divider|divider|selnose[0]~4_combout\,
	datac => \b[1]~input_o\,
	datad => \Div0|auto_generated|divider|divider|StageOut[0]~0_combout\,
	combout => \Div0|auto_generated|divider|divider|selnose[9]~7_combout\);

-- Location: LCCOMB_X38_Y23_N0
\Mux2~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux2~0_combout\ = (\a[6]~input_o\ & (\rres[0]~3_combout\ $ (((\rres[0]~2_combout\) # (\b[6]~input_o\))))) # (!\a[6]~input_o\ & ((\rres[0]~2_combout\ & ((\rres[0]~3_combout\) # (\b[6]~input_o\))) # (!\rres[0]~2_combout\ & (\rres[0]~3_combout\ & 
-- \b[6]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0011111001101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~2_combout\,
	datab => \a[6]~input_o\,
	datac => \rres[0]~3_combout\,
	datad => \b[6]~input_o\,
	combout => \Mux2~0_combout\);

-- Location: LCCOMB_X38_Y23_N18
\Mux2~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux2~1_combout\ = (\rres[0]~0_combout\ & (\rres[0]~1_combout\)) # (!\rres[0]~0_combout\ & ((\rres[0]~1_combout\ & (!\Div0|auto_generated|divider|divider|selnose[9]~7_combout\)) # (!\rres[0]~1_combout\ & ((\Mux2~0_combout\)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001110110001100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \rres[0]~1_combout\,
	datac => \Div0|auto_generated|divider|divider|selnose[9]~7_combout\,
	datad => \Mux2~0_combout\,
	combout => \Mux2~1_combout\);

-- Location: LCCOMB_X38_Y22_N28
\Mod0|auto_generated|divider|divider|StageOut[62]~34\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[62]~34_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~12_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110000110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[6]~12_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[53]~22_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[62]~34_combout\);

-- Location: LCCOMB_X38_Y24_N28
\Add0~20\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~20_combout\ = (\op[2]~input_o\ & (((\op[0]~input_o\)))) # (!\op[2]~input_o\ & (\b[6]~input_o\ $ ((\op[1]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111011000000110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[6]~input_o\,
	datab => \op[1]~input_o\,
	datac => \op[2]~input_o\,
	datad => \op[0]~input_o\,
	combout => \Add0~20_combout\);

-- Location: LCCOMB_X38_Y24_N18
\Add0~21\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~21_combout\ = (\a[6]~input_o\ & ((\Add0~20_combout\ & (\Add0~19\ & VCC)) # (!\Add0~20_combout\ & (!\Add0~19\)))) # (!\a[6]~input_o\ & ((\Add0~20_combout\ & (!\Add0~19\)) # (!\Add0~20_combout\ & ((\Add0~19\) # (GND)))))
-- \Add0~22\ = CARRY((\a[6]~input_o\ & (!\Add0~20_combout\ & !\Add0~19\)) # (!\a[6]~input_o\ & ((!\Add0~19\) # (!\Add0~20_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001011000010111",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \a[6]~input_o\,
	datab => \Add0~20_combout\,
	datad => VCC,
	cin => \Add0~19\,
	combout => \Add0~21_combout\,
	cout => \Add0~22\);

-- Location: LCCOMB_X38_Y23_N12
\Mux2~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux2~2_combout\ = (\rres[0]~0_combout\ & ((\Mux2~1_combout\ & (\Mod0|auto_generated|divider|divider|StageOut[62]~34_combout\)) # (!\Mux2~1_combout\ & ((\Add0~21_combout\))))) # (!\rres[0]~0_combout\ & (\Mux2~1_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1110011011000100",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \Mux2~1_combout\,
	datac => \Mod0|auto_generated|divider|divider|StageOut[62]~34_combout\,
	datad => \Add0~21_combout\,
	combout => \Mux2~2_combout\);

-- Location: LCCOMB_X38_Y23_N28
\Mux2~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux2~3_combout\ = (\rres[0]~4_combout\ & (((!\a[6]~input_o\ & !\b[6]~input_o\)))) # (!\rres[0]~4_combout\ & (\Mux2~2_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000101000111010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux2~2_combout\,
	datab => \a[6]~input_o\,
	datac => \rres[0]~4_combout\,
	datad => \b[6]~input_o\,
	combout => \Mux2~3_combout\);

-- Location: FF_X38_Y23_N29
\rres[6]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux2~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(6));

-- Location: LCCOMB_X37_Y24_N26
\Mux1~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux1~0_combout\ = (\rres[0]~3_combout\ & (\a[7]~input_o\ $ (((\b[7]~input_o\) # (\rres[0]~2_combout\))))) # (!\rres[0]~3_combout\ & ((\a[7]~input_o\ & ((\b[7]~input_o\) # (\rres[0]~2_combout\))) # (!\a[7]~input_o\ & (\b[7]~input_o\ & 
-- \rres[0]~2_combout\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0111011001101000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~3_combout\,
	datab => \a[7]~input_o\,
	datac => \b[7]~input_o\,
	datad => \rres[0]~2_combout\,
	combout => \Mux1~0_combout\);

-- Location: LCCOMB_X38_Y24_N22
\Add0~23\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~23_combout\ = (\op[2]~input_o\ & (((\op[0]~input_o\)))) # (!\op[2]~input_o\ & (\b[7]~input_o\ $ ((\op[1]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111011000000110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[7]~input_o\,
	datab => \op[1]~input_o\,
	datac => \op[2]~input_o\,
	datad => \op[0]~input_o\,
	combout => \Add0~23_combout\);

-- Location: LCCOMB_X38_Y24_N20
\Add0~24\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Add0~24_combout\ = \a[7]~input_o\ $ (\Add0~22\ $ (!\Add0~23_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0101101010100101",
	sum_lutc_input => "cin")
-- pragma translate_on
PORT MAP (
	dataa => \a[7]~input_o\,
	datad => \Add0~23_combout\,
	cin => \Add0~22\,
	combout => \Add0~24_combout\);

-- Location: LCCOMB_X37_Y24_N12
\Mux1~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux1~1_combout\ = (\rres[0]~0_combout\ & ((\rres[0]~1_combout\) # ((\Add0~24_combout\)))) # (!\rres[0]~0_combout\ & (!\rres[0]~1_combout\ & (\Mux1~0_combout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1011101010011000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \rres[0]~0_combout\,
	datab => \rres[0]~1_combout\,
	datac => \Mux1~0_combout\,
	datad => \Add0~24_combout\,
	combout => \Mux1~1_combout\);

-- Location: LCCOMB_X38_Y22_N30
\Mod0|auto_generated|divider|divider|StageOut[63]~35\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mod0|auto_generated|divider|divider|StageOut[63]~35_combout\ = (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & ((\Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\))) # 
-- (!\Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\ & (\Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~14_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1111110000110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datab => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[8]~16_combout\,
	datac => \Mod0|auto_generated|divider|divider|add_sub_7_result_int[7]~14_combout\,
	datad => \Mod0|auto_generated|divider|divider|StageOut[54]~21_combout\,
	combout => \Mod0|auto_generated|divider|divider|StageOut[63]~35_combout\);

-- Location: LCCOMB_X37_Y24_N30
\Mux1~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux1~2_combout\ = (\Mux1~1_combout\ & (((\Mod0|auto_generated|divider|divider|StageOut[63]~35_combout\)) # (!\rres[0]~1_combout\))) # (!\Mux1~1_combout\ & (\rres[0]~1_combout\ & ((!\Div0|auto_generated|divider|divider|selnose\(0)))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1010001011100110",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux1~1_combout\,
	datab => \rres[0]~1_combout\,
	datac => \Mod0|auto_generated|divider|divider|StageOut[63]~35_combout\,
	datad => \Div0|auto_generated|divider|divider|selnose\(0),
	combout => \Mux1~2_combout\);

-- Location: LCCOMB_X37_Y24_N28
\Mux1~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux1~3_combout\ = (\rres[0]~4_combout\ & (((!\a[7]~input_o\ & !\b[7]~input_o\)))) # (!\rres[0]~4_combout\ & (\Mux1~2_combout\))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000001110101010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux1~2_combout\,
	datab => \a[7]~input_o\,
	datac => \b[7]~input_o\,
	datad => \rres[0]~4_combout\,
	combout => \Mux1~3_combout\);

-- Location: FF_X37_Y24_N29
\rres[7]\ : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux1~3_combout\,
	ena => \rres[0]~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => rres(7));

-- Location: LCCOMB_X38_Y23_N6
\Mux0~3\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux0~3_combout\ = (\a[5]~input_o\ & (\b[5]~input_o\ & (\b[4]~input_o\ $ (!\a[4]~input_o\)))) # (!\a[5]~input_o\ & (!\b[5]~input_o\ & (\b[4]~input_o\ $ (!\a[4]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001000000001001",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \a[5]~input_o\,
	datab => \b[5]~input_o\,
	datac => \b[4]~input_o\,
	datad => \a[4]~input_o\,
	combout => \Mux0~3_combout\);

-- Location: LCCOMB_X37_Y24_N16
\RESULT~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \RESULT~0_combout\ = \b[7]~input_o\ $ (\a[7]~input_o\)

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000111111110000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	datac => \b[7]~input_o\,
	datad => \a[7]~input_o\,
	combout => \RESULT~0_combout\);

-- Location: LCCOMB_X36_Y24_N22
\Mux0~4\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux0~4_combout\ = (\Mux0~3_combout\ & (!\RESULT~0_combout\ & (\b[6]~input_o\ $ (!\a[6]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0010000000000010",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux0~3_combout\,
	datab => \RESULT~0_combout\,
	datac => \b[6]~input_o\,
	datad => \a[6]~input_o\,
	combout => \Mux0~4_combout\);

-- Location: LCCOMB_X36_Y24_N24
\Mux0~0\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux0~0_combout\ = (!\op[1]~input_o\ & (!\op[2]~input_o\ & (!\op[0]~input_o\ & !\op[3]~input_o\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "0000000000000001",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \op[1]~input_o\,
	datab => \op[2]~input_o\,
	datac => \op[0]~input_o\,
	datad => \op[3]~input_o\,
	combout => \Mux0~0_combout\);

-- Location: LCCOMB_X36_Y24_N26
\Mux0~1\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux0~1_combout\ = (\b[0]~input_o\ & (\a[0]~input_o\ & (\b[1]~input_o\ $ (!\a[1]~input_o\)))) # (!\b[0]~input_o\ & (!\a[0]~input_o\ & (\b[1]~input_o\ $ (!\a[1]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1001000000001001",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[0]~input_o\,
	datab => \a[0]~input_o\,
	datac => \b[1]~input_o\,
	datad => \a[1]~input_o\,
	combout => \Mux0~1_combout\);

-- Location: LCCOMB_X36_Y24_N28
\Mux0~2\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux0~2_combout\ = (\b[2]~input_o\ & (\a[2]~input_o\ & (\a[3]~input_o\ $ (!\b[3]~input_o\)))) # (!\b[2]~input_o\ & (!\a[2]~input_o\ & (\a[3]~input_o\ $ (!\b[3]~input_o\))))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1000001001000001",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \b[2]~input_o\,
	datab => \a[3]~input_o\,
	datac => \b[3]~input_o\,
	datad => \a[2]~input_o\,
	combout => \Mux0~2_combout\);

-- Location: LCCOMB_X36_Y24_N0
\Mux0~5\ : cycloneiii_lcell_comb
-- Equation(s):
-- \Mux0~5_combout\ = (\Mux0~4_combout\ & (\Mux0~0_combout\ & (\Mux0~1_combout\ & \Mux0~2_combout\)))

-- pragma translate_off
GENERIC MAP (
	lut_mask => "1000000000000000",
	sum_lutc_input => "datac")
-- pragma translate_on
PORT MAP (
	dataa => \Mux0~4_combout\,
	datab => \Mux0~0_combout\,
	datac => \Mux0~1_combout\,
	datad => \Mux0~2_combout\,
	combout => \Mux0~5_combout\);

-- Location: FF_X36_Y24_N1
z : dffeas
-- pragma translate_off
GENERIC MAP (
	is_wysiwyg => "true",
	power_up => "low")
-- pragma translate_on
PORT MAP (
	clk => \clk~inputclkctrl_outclk\,
	d => \Mux0~5_combout\,
	devclrn => ww_devclrn,
	devpor => ww_devpor,
	q => \z~q\);

ww_r(0) <= \r[0]~output_o\;

ww_r(1) <= \r[1]~output_o\;

ww_r(2) <= \r[2]~output_o\;

ww_r(3) <= \r[3]~output_o\;

ww_r(4) <= \r[4]~output_o\;

ww_r(5) <= \r[5]~output_o\;

ww_r(6) <= \r[6]~output_o\;

ww_r(7) <= \r[7]~output_o\;

ww_zf <= \zf~output_o\;

ww_cf <= \cf~output_o\;
END structure;


