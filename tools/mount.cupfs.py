#!/usr/bin/env python2

# uses fusepy from - https://github.com/terencehonles/fusepy

from collections import defaultdict
from errno import ENOENT, EDQUOT
from stat import S_IFDIR, S_IFLNK, S_IFREG
from sys import argv, exit
from time import time
import struct

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

if not hasattr(__builtins__, 'bytes'):
    bytes = str


class File():
    def __init__(self, fileinfo):
        self.name = str(fileinfo[:10]).split('\x00')[0]
        self.size = fileinfo[11] << 8 | fileinfo[10]
        self.position = fileinfo[14] << 16 | fileinfo[13] << 8 | fileinfo[12]
        self.is_valid = fileinfo[15] & 1 == 1
        self.current_offset = 0

    @classmethod
    def FromPath(cls, path):
        fileinfo = bytearray(16)
        path = str(path.split('/')[-1])
        struct.pack_into('10s', fileinfo, 0, path[:10])
        fileinfo[15] = 1
        return cls(fileinfo)

    def Rename(self, new):
        self.name = str(new.split('/')[:10])

    def SetPosition(self, pos):
        self.position = pos

    def SetSize(self, size):
        if size > 64 * 1024:
            return None
        self.size = size
        return size

    def ToBinary(self):
        entry = bytearray(16)
        struct.pack_into('<10sHHBB', entry, 0, str(self.name), self.size, self.position & 0xffff, self.position >> 16, self.is_valid)
        #import binascii
        #print(binascii.hexlify(entry))
        return entry

def get_file_entry_idx(files, path):
    idx = 0
    for f in files:
        if f.name == str(path.split('/')[-1][:10]):
            return idx
        idx += 1
    return None

def get_file_entry(files, path):
    fe = get_file_entry_idx(files, path)
    if fe != None:
        return files[get_file_entry_idx(files, path)]
    return None
    
def get_first_open_file_entry_idx(files):
    idx = 0
    for f in files:
        if idx >= 14: return None
        if not f.is_valid:
            return idx
        idx += 1
    return None

class CupFS(LoggingMixIn, Operations):
    def __init__(self, img):
        self.f = open(img, 'r+b')

        metadata = bytearray(self.f.read(256))
        if len(metadata) != 256:
            pass #raise exception

        # check magic number
        if (metadata[-1] << 8 | metadata[-2]) != 0xf00d:
            print('Invalid magic number!')
            pass #raise exception
        
        self.ver_maj = metadata[0]
        self.ver_min = metadata[1]

        self.files = []
        for i in range(15):
            self.files.append(File(metadata[8+(16*i):8+(16*i)+16]))

    def UpdateMetadata(self):
        self.f.seek(8)
        # write file entries
        for fe in self.files:
            self.f.write(fe.ToBinary())
        self.f.flush()

    def chmod(self, path, mode):
        return 0;

    def chown(self, path, uid, gid):
        return 0;

    def create(self, path, mode):
        idx = get_first_open_file_entry_idx(self.files)
        if idx == None:
            print('Disk Full')
            raise FuseOSError(EDQUOT)
            pass # raise disk full

        self.files[idx] = File.FromPath(path)

        self.files[idx].SetPosition(256+idx*64*1024)

        self.UpdateMetadata()

        return idx

    def getattr(self, path, fh=None):
        fe = get_file_entry(self.files, path)
        if fe == None:
            raise FuseOSError(ENOENT)

        if path[-1] == '/':
            return dict(st_mode=S_IFDIR | 0755, st_nlink=1, st_size=0, st_ctime=time(), st_mtime=time(), st_atime=time())
        return dict(st_mode=S_IFREG | 0777, st_nlink=1, st_size=fe.size, st_ctime=time(), st_mtime=time(), st_atime=time())

    def getxattr(self, path, name, position=0):
        return ''

    def listxattr(self, path):
        return None #todo
        attrs = self.files[path].get('attrs', {})
        return attrs.keys()

    def mkdir(self, path, mode):
        print('Flat filesystem. Ignoring mkdir.')
        pass

    def open(self, path, flags):
        return get_file_entry_idx(self.files, path)

    def read(self, path, size, offset, fh):
        fe = get_file_entry(self.files, path)
        self.f.seek(fe.position + offset)
        if size > fe.size - offset:
            size = fe.size - offset
        data = self.f.read(size)
        return data

    def readdir(self, path, fh):
        return ['.', '..'] + [f.name for f in self.files if f.is_valid]

    def readlink(self, path):
        fe = get_file_entry(self.files, path)
        self.f.seek(fe.position)
        return self.f.read(fe.size)

    def removexattr(self, path, name):
        pass

    def rename(self, old, new):
        f = get_file_entry(self.files, old)
        f.Rename(new)
        self.UpdateMetadata()

    def rmdir(self, path):
        print('Flat filesystem. Ignoring rmdir.')
        pass

    def setxattr(self, path, name, value, options, position=0):
        pass

    def statfs(self, path):
        free_file_count = 0
        for f in self.files:
            if not f.is_valid:
                free_file_count += 1

        return dict(f_bsize=256, f_blocks=3841, f_bavail=free_file_count*64*1024/256)

    def symlink(self, target, source):
        pass

    def truncate(self, path, length, fh=None):
        f = get_file_entry(self.files, path)
        f.size = length

    def unlink(self, path):
        fe = get_file_entry(self.files, path)
        if fe != None:
            fe.is_valid = False

    def utimens(self, path, times=None):
        pass

    def write(self, path, data, offset, fh):
        # to make things easy, give each file unoccupied 64k block
        fe = get_file_entry(self.files, path)
        n = fe.SetSize(len(data) + offset)
        if n == None:
            pass #todo invalid write - no space left
            return 0
        self.f.seek(fe.position + offset)
        self.f.write(data)
        self.f.flush()
        self.UpdateMetadata()
        return n

if __name__ == '__main__':
    if len(argv) != 3:
        print('usage: %s <diskimage> <mountpoint>' % argv[0])
        exit(1)

    fuse = FUSE(CupFS(argv[1]), argv[2], foreground=True)
