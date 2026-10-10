import { spawnSync } from 'node:child_process';
import path from 'node:path';

if (!process.env.DATABASE_URL) {
  process.env.DATABASE_URL = process.env.tm_DATABASE_URL || 'postgresql://localhost/trainme';
}

const prismaCli = path.join(process.cwd(), 'node_modules', 'prisma', 'build', 'index.js');
const result = spawnSync(process.execPath, [prismaCli, ...process.argv.slice(2)], {
  stdio: 'inherit',
  env: process.env,
});

process.exit(result.status ?? 1);
