// The real ROM image: the boot ROM (rom/boot.s) and the kernel, as simtest
// builds it (tools/simtest.nim buildKernelRom).
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

export const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');

export function kernelRom() {
  // the layout kernel/assemble.sh uses (code $1000, data $4000, bss $6000).
  // a private directory, so tests running side by side can't clobber each
  // other's build (kernel/assemble.sh merges in place): the same merge, here
  fs.mkdirSync(path.join(ROOT, 'build'), { recursive: true });
  const out = fs.mkdtempSync(path.join(ROOT, 'build', 'rom-'));
  const kdir = path.join(ROOT, 'kernel');
  const merged = fs.readdirSync(kdir).filter((f) => f.endsWith('.s')).sort()
    .map((f) => `; @file ${f}\n` + fs.readFileSync(path.join(kdir, f), 'utf8') + '\n').join('');
  fs.writeFileSync(path.join(out, 'merged.ss'), merged);
  execFileSync('python3', [path.join(ROOT, 'tools/as.py'), 'merged.ss', 'kernel.o', '0x1000,0x4000,0x6000', '--map'], { cwd: out, stdio: 'pipe' });
  execFileSync('python3', [path.join(ROOT, 'tools/as.py'), path.join(ROOT, 'rom/boot.s'), path.join(out, 'boot.bin'), '0xe000,0xe600,0x0f00'], { stdio: 'pipe' });
  execFileSync('python3', [path.join(ROOT, 'tools/mkrom.py'), path.join(out, 'boot.bin'), path.join(out, 'kernel.o'), '-o', path.join(out, 'kernel.rom')], { stdio: 'pipe' });
  const rom = fs.readFileSync(path.join(out, 'kernel.rom'));
  fs.rmSync(out, { recursive: true });
  return rom;
}
