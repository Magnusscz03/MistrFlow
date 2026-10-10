import {readFileSync, readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist');
const json = p => JSON.parse(readFileSync(path.join(root, p), 'utf8'));
const config = json('vercel.json');
const routing = json('dist/vercel.json');
for (const key of ['rewrites', 'headers', 'cleanUrls']) {
  if (JSON.stringify(config[key]) !== JSON.stringify(routing[key])) throw Error('Root configuration differs: '+key);
}
if (config.framework !== null || config.outputDirectory !== 'dist') throw Error('Expected static dist deployment');
const walk = dir => readdirSync(dir, {withFileTypes: true}).flatMap(e => e.isDirectory() ? walk(path.join(dir,e.name)) : [path.relative(dist,path.join(dir,e.name)).split(path.sep).join('/')]);
const files = walk(dist).sort();
const manifest = json('deployment-manifest.json').files;
if (JSON.stringify(files) !== JSON.stringify(manifest.map(e => e.file).sort())) throw Error('Incomplete deployment manifest');
for (const file of manifest) {
  const bytes = readFileSync(path.join(dist, file.file));
  if (bytes.length !== file.size || createHash('sha1').update(bytes).digest('hex') !== file.sha) throw Error('Changed or corrupt file: '+file.file);
}
for (const file of ['index.html','app/index.html','download/index.html','intake/index.html','manifest.webmanifest','brand/mark.png']) {
  if (!files.includes(file)) throw Error('Missing required file: '+file);
}
console.log(`Verified all ${files.length} distribution files and Supabase routing. No files uploaded; backend not deployed.`);
