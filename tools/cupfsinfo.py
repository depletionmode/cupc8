#!/usr/bin/env python3

# Display CupFS image metadata

import sys

img = sys.argv[1]

metadata = None
with open(img, 'rb') as f:
    metadata = f.read(256)

if len(metadata) == 256:
    # check magic number
    if (metadata[-1] << 8 | metadata[-2]) != 0xf00d:
        print('Error: Invalid magic number!')
        sys.exit(1)

    print('Version: {}.{}'.format(metadata[0], metadata[1]))
    for i in range(15):
        fileinfo = metadata[8+(16*i):8+(16*i)+16]
        if (fileinfo[15] & 1) == 1:
            # file is valid
            print('File entry #{}:'.format(i))
            print('  File name: {}'.format(fileinfo[0:10]))
            print('  File size: {}'.format(fileinfo[11] << 8 | fileinfo[10]))
            print('  File offset: {}'.format(fileinfo[12] << 16 | fileinfo[13] << 8 | fileinfo[14]))

else:
    print('Error: File too short!')


