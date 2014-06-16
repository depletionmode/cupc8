import sys

idx = 0

def __render_op(op):
    global idx
    # when x"000" => data_out <= x"8c"; -- MOV R0, #3
    s = 'when x"{:03d}" => data_out <= x"{:02x}";'.format(idx, op)
    idx += 1
    return s


with open(sys.argv[1], "rb") as f:
    while True:
        b = f.read(1)
        if len(b) == 0: break
        print(__render_op(int.from_bytes(b, byteorder='little')))


