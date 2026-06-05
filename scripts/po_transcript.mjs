// Self-contained YouTube transcript extractor that mints a Proof-of-Origin
// (PO) token via BotGuard (jnn-pa.googleapis.com) and then calls YouTube's
// InnerTube endpoints on www.youtube.com. Designed to run where www.youtube.com
// is reachable (e.g. GitHub Actions). Writes transcripts/<id>.txt.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { BG } = require('bgutils-js');
const { JSDOM } = require('jsdom');
import fs from 'fs';
import path from 'path';

const ARG = process.argv[2] || 'https://youtu.be/gTr3J33kQLA';
const VID = parseId(ARG);
const CV = '2.20240826.01.00';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36';
const HOST = 'https://www.youtube.com';
const KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8';
const OUT = 'transcripts';

function parseId(u) {
  const m = u.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([0-9A-Za-z_-]{11})/);
  return m ? m[1] : u;
}
function tsfmt(sec) { sec = Math.floor(sec); return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`; }

function writeOut(lines) {
  fs.mkdirSync(OUT, { recursive: true });
  const p = path.join(OUT, `${VID}.txt`);
  fs.writeFileSync(p, lines.join('\n').trim() + '\n');
  console.log(`[ok] wrote ${p} (${lines.length} lines)`);
}

async function getVisitorData() {
  const r = await fetch(`${HOST}/youtubei/v1/visitor_id?prettyPrint=false`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'User-Agent': UA },
    body: JSON.stringify({ context: { client: { clientName: 'WEB', clientVersion: CV } } }),
  });
  const j = await r.json().catch(() => ({}));
  return j?.responseContext?.visitorData;
}

async function mintPoToken(visitorData) {
  const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { url: HOST + '/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document });
  const bgConfig = { fetch: (u, o) => fetch(u, o), globalObj: globalThis, identifier: visitorData, requestKey: 'O43z0dpjhgX20SCx4KAo' };
  const challenge = await BG.Challenge.create(bgConfig);
  const ijs = challenge.interpreterJavascript?.privateDoNotAccessOrElseSafeScriptWrappedValue;
  if (!ijs) throw new Error('no interpreter JS in challenge');
  new Function(ijs)();
  const { poToken } = await BG.PoToken.generate({ program: challenge.program, globalName: challenge.globalName, bgConfig });
  return poToken;
}

function ctx(visitorData) {
  return { client: { clientName: 'WEB', clientVersion: CV, hl: 'en', gl: 'US', visitorData } };
}
async function inn(method, body, visitorData) {
  const r = await fetch(`${HOST}/youtubei/v1/${method}?prettyPrint=false&key=${KEY}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json', 'User-Agent': UA, 'Origin': HOST,
      'X-Goog-Visitor-Id': visitorData, 'X-Youtube-Client-Name': '1', 'X-Youtube-Client-Version': CV,
    },
    body: JSON.stringify(body),
  });
  return { status: r.status, json: await r.json().catch(() => null) };
}

function findTranscriptToken(o) {
  let out = [];
  if (o && typeof o === 'object') {
    if (o.getTranscriptEndpoint) out.push(o.getTranscriptEndpoint.params);
    for (const k in o) out = out.concat(findTranscriptToken(o[k]));
  } else if (Array.isArray(o)) { for (const v of o) out = out.concat(findTranscriptToken(v)); }
  return out.filter(Boolean);
}
function collectSegments(o) {
  let out = [];
  if (o && typeof o === 'object') {
    if (o.transcriptSegmentRenderer) out.push(o.transcriptSegmentRenderer);
    for (const k in o) out = out.concat(collectSegments(o[k]));
  } else if (Array.isArray(o)) { for (const v of o) out = out.concat(collectSegments(v)); }
  return out;
}
function segText(s) {
  const sn = s.snippet || {};
  if (sn.runs) return sn.runs.map((r) => r.text || '').join('');
  return sn.simpleText || '';
}

// --- Method A: InnerTube get_transcript (www.youtube.com) -------------------
async function tryGetTranscript(visitorData, poToken) {
  const nx = await inn('next', { context: ctx(visitorData), videoId: VID }, visitorData);
  if (nx.status !== 200) { console.log(`[A] next status ${nx.status}`); return false; }
  const tok = findTranscriptToken(nx.json)[0];
  if (!tok) { console.log('[A] no transcript token in next'); return false; }
  for (const withPo of [true, false]) {
    const body = { context: ctx(visitorData), params: tok };
    if (withPo) body.serviceIntegrityDimensions = { poToken };
    const gt = await inn('get_transcript', body, visitorData);
    const segs = collectSegments(gt.json);
    console.log(`[A] get_transcript po=${withPo} status=${gt.status} segs=${segs.length}`);
    if (segs.length) {
      const lines = segs.map((s) => `[${tsfmt((parseInt(s.startMs || '0', 10)) / 1000)}] ${segText(s).trim()}`).filter((l) => l.replace(/\[\d+:\d+\]\s*/, ''));
      writeOut(lines);
      return true;
    }
  }
  return false;
}

// --- Method B: player captionTracks -> timedtext (json3) --------------------
async function tryTimedText(visitorData, poToken) {
  const pl = await inn('player', {
    context: ctx(visitorData), videoId: VID, contentCheckOk: true, racyCheckOk: true,
    serviceIntegrityDimensions: { poToken },
  }, visitorData);
  const tracks = pl.json?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
  console.log(`[B] player status=${pl.json?.playabilityStatus?.status} tracks=${tracks.length}`);
  if (!tracks.length) return false;
  const pick = tracks.find((t) => (t.languageCode || '').startsWith('en')) || tracks[0];
  let url = pick.baseUrl;
  url += (url.includes('?') ? '&' : '?') + 'fmt=json3';
  const r = await fetch(url, { headers: { 'User-Agent': UA } });
  const j = await r.json().catch(() => null);
  const events = j?.events || [];
  const lines = [];
  for (const e of events) {
    if (!e.segs) continue;
    const text = e.segs.map((s) => s.utf8 || '').join('').replace(/\n/g, ' ').trim();
    if (text) lines.push(`[${tsfmt((e.tStartMs || 0) / 1000)}] ${text}`);
  }
  if (lines.length) { writeOut(lines); return true; }
  return false;
}

async function main() {
  console.log(`[info] video id: ${VID}`);
  const visitorRaw = await getVisitorData();
  const visitorData = visitorRaw ? decodeURIComponent(visitorRaw) : undefined;
  if (!visitorData) throw new Error('could not obtain visitorData');
  const poToken = await mintPoToken(visitorData);
  console.log(`[info] poToken length=${poToken.length}, visitorData=${visitorData.slice(0, 16)}...`);

  if (await tryGetTranscript(visitorData, poToken)) return;
  if (await tryTimedText(visitorData, poToken)) return;
  throw new Error('all PO-token strategies failed');
}

main().catch((e) => { console.error('[error]', e.message || e); process.exit(1); });
