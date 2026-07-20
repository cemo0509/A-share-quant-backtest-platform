// 清理前端构建产物，避免旧 dist 残留混入打包（跨平台、零依赖）
import { rmSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const dist = resolve(__dirname, 'dist');

if (existsSync(dist)) {
  rmSync(dist, { recursive: true, force: true });
  console.log('[clean] removed dist/');
} else {
  console.log('[clean] dist/ not found, skip');
}
