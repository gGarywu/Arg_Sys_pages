import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist');

await fs.rm(dist, { recursive: true, force: true });
await fs.mkdir(path.join(dist, 'data'), { recursive: true });
await fs.mkdir(path.join(dist, 'assets'), { recursive: true });

for (const file of ['index.html', 'styles.css', 'app.mjs', '.nojekyll']) {
  await fs.copyFile(path.join(root, file), path.join(dist, file));
}

await fs.copyFile(
  path.join(root, 'data', 'catalog.json'),
  path.join(dist, 'data', 'catalog.json'),
);

await fs.copyFile(
  path.join(root, 'assets', 'birdmen.png'),
  path.join(dist, 'assets', 'birdmen.png'),
);

console.log('Built static site in dist/');
