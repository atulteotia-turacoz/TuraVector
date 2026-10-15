// Provide the Apryse/PDFTron WebViewer runtime at public/webviewer/lib (served at /webviewer/lib).
//
// Production runs the server's WebViewer 8.10.0 SDK build. If public/webviewer/lib already
// exists (copied from the server's static/dist/lib), it is left untouched. To (re)install from
// a server copy:  WEBVIEWER_SDK_DIR=~/Downloads/static/dist/lib node scripts/copy-webviewer.mjs
// Otherwise it falls back to the npm package's runtime (same 8.10.0 version).
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';

const target = 'public/webviewer/lib';
const sdk = process.env.WEBVIEWER_SDK_DIR;
if (sdk) {
  rmSync(target, { recursive: true, force: true });
  mkdirSync(target, { recursive: true });
  cpSync(sdk, target, { recursive: true });
  console.log(`WebViewer SDK copied from ${sdk}`);
} else if (existsSync(`${target}/core`)) {
  console.log('WebViewer runtime already present — leaving it as is');
} else if (existsSync('node_modules/@pdftron/webviewer/public')) {
  mkdirSync(target, { recursive: true });
  cpSync('node_modules/@pdftron/webviewer/public', target, { recursive: true });
  console.log('WebViewer copied from npm package');
}
