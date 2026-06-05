// Mint a WEB Proof-of-Origin token + visitorData via BotGuard and print JSON
// to stdout: {"visitorData":"...","poToken":"..."}. Diagnostics go to stderr.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { BG } = require('bgutils-js');
const { JSDOM } = require('jsdom');

const HOST = 'https://www.youtube.com';
const CV = '2.20240826.01.00';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36';

async function getVisitorData() {
  const r = await fetch(`${HOST}/youtubei/v1/visitor_id?prettyPrint=false`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'User-Agent': UA },
    body: JSON.stringify({ context: { client: { clientName: 'WEB', clientVersion: CV } } }),
  });
  const j = await r.json().catch(() => ({}));
  return j?.responseContext?.visitorData;
}

const visitorRaw = await getVisitorData();
const visitorData = visitorRaw ? decodeURIComponent(visitorRaw) : undefined;
if (!visitorData) { console.error('no visitorData'); process.exit(2); }

const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { url: HOST + '/' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document });
const bgConfig = { fetch: (u, o) => fetch(u, o), globalObj: globalThis, identifier: visitorData, requestKey: 'O43z0dpjhgX20SCx4KAo' };
const challenge = await BG.Challenge.create(bgConfig);
const ijs = challenge.interpreterJavascript?.privateDoNotAccessOrElseSafeScriptWrappedValue;
if (!ijs) { console.error('no interpreter JS'); process.exit(2); }
new Function(ijs)();
const { poToken } = await BG.PoToken.generate({ program: challenge.program, globalName: challenge.globalName, bgConfig });
console.error(`minted poToken length=${poToken.length} visitorData=${visitorData.slice(0, 16)}...`);
process.stdout.write(JSON.stringify({ visitorData, poToken }));
