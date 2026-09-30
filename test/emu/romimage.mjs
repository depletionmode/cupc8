// The real ROM image: the boot ROM (rom/boot.s), the kernel and BASIC
// (basic/build.sh, after the kernel in ROM), as simtest builds it (tools/simmachine.nim
// buildKernelRom).
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

export const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');

export function kernelRom() {
  // the layout kernel/assemble.sh uses (code $1000, data $6000, bss $e000).
  // a private directory, so tests running side by side can't clobber each
  // other's build (kernel/assemble.sh merges in place): the same merge, here
  fs.mkdirSync(path.join(ROOT, 'build'), { recursive: true });
  const out = fs.mkdtempSync(path.join(ROOT, 'build', 'rom-'));
  // Build output belongs in the private build directory. Regular file
  // descriptors also let these local tools run where captured child-process
  // pipes are unavailable. Keep the diagnostic output if a command fails.
  const build = (command, args, options = {}) => {
    const log = path.join(out, 'build.log');
    const fd = fs.openSync(log, 'a');
    try {
      execFileSync(command, args, { ...options, stdio: ['ignore', fd, fd] });
    } catch (error) {
      error.message += `\nROM build log: ${log}\n${fs.readFileSync(log, 'utf8')}`;
      throw error;
    } finally {
      fs.closeSync(fd);
    }
  };
  const kdir = path.join(ROOT, 'kernel');
  const merged = fs.readdirSync(kdir).filter((f) => f.endsWith('.s')).sort()
    .map((f) => `; @file ${f}\n` + fs.readFileSync(path.join(kdir, f), 'utf8') + '\n').join('');
  fs.writeFileSync(path.join(out, 'merged.ss'), merged);
  // the kernel's code/data/bss bases, as kernel/assemble.sh gives them
  const bases = /as\.py merged\.ss kernel\.o (0x[0-9a-fA-F]+,0x[0-9a-fA-F]+,0x[0-9a-fA-F]+)/.exec(
    fs.readFileSync(path.join(kdir, 'assemble.sh'), 'utf8'));
  build('python3', [path.join(ROOT, 'tools/as.py'), 'merged.ss', 'kernel.o', ...(bases ? [bases[1]] : []), '--map'], { cwd: out });
  build('python3', [path.join(ROOT, 'tools/as.py'), path.join(ROOT, 'rom/boot.s'), path.join(out, 'boot.bin'), '0xe000,0xe600,0x0f00']);
  build('bash', [path.join(ROOT, 'basic/build.sh'), out]);
  build('python3', [path.join(ROOT, 'tools/mkrom.py'), path.join(out, 'boot.bin'), path.join(out, 'kernel.o'),
    '--basic', path.join(out, 'BASIC.PRG'), '-o', path.join(out, 'kernel.rom')]);
  const rom = fs.readFileSync(path.join(out, 'kernel.rom'));
  fs.rmSync(out, { recursive: true });
  return rom;
}
