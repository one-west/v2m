import type { MeetingMeta } from "./types";

// Durable buffer for an in-progress recording, so it survives a page reload
// caused by sleep / refresh / crash. One active session at a time.

const DB_NAME = "v2m-recordings";
const META_STORE = "meta";
const CHUNK_STORE = "chunks";
const META_KEY = "active";

export interface SessionMeta {
  title: string;
  meta: MeetingMeta;
  language: string;
}

export interface PendingSession {
  meta: SessionMeta;
  audio: Blob;
}

const AUDIO_MIME = "audio/webm";

function blobToArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  // FileReader works everywhere (browsers + jsdom); Blob.arrayBuffer() is missing in jsdom.
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as ArrayBuffer);
    r.onerror = () => reject(r.error);
    r.readAsArrayBuffer(blob);
  });
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(META_STORE)) db.createObjectStore(META_STORE);
      if (!db.objectStoreNames.contains(CHUNK_STORE)) db.createObjectStore(CHUNK_STORE, { autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function runWrite(stores: string[], fn: (t: IDBTransaction) => void): Promise<void> {
  return openDb().then(
    (db) =>
      new Promise<void>((resolve, reject) => {
        const t = db.transaction(stores, "readwrite");
        fn(t);
        t.oncomplete = () => { db.close(); resolve(); };
        t.onerror = () => { db.close(); reject(t.error); };
      }),
  );
}

/** Start a fresh session: store its meta and drop any leftover chunks. */
export function beginSession(meta: SessionMeta): Promise<void> {
  return runWrite([META_STORE, CHUNK_STORE], (t) => {
    t.objectStore(CHUNK_STORE).clear();
    t.objectStore(META_STORE).put(meta, META_KEY);
  });
}

export async function appendChunk(blob: Blob): Promise<void> {
  // Store the raw bytes (ArrayBuffer), not the Blob: ArrayBuffers structured-clone
  // reliably across IndexedDB implementations.
  const buf = await blobToArrayBuffer(blob);
  return runWrite([CHUNK_STORE], (t) => {
    t.objectStore(CHUNK_STORE).add(buf);
  });
}

export function clearSession(): Promise<void> {
  return runWrite([META_STORE, CHUNK_STORE], (t) => {
    t.objectStore(META_STORE).delete(META_KEY);
    t.objectStore(CHUNK_STORE).clear();
  });
}

/** A session is "pending" only when it has meta AND at least one chunk. */
export function getPendingSession(): Promise<PendingSession | null> {
  return openDb().then(
    (db) =>
      new Promise<PendingSession | null>((resolve, reject) => {
        const t = db.transaction([META_STORE, CHUNK_STORE], "readonly");
        const metaReq = t.objectStore(META_STORE).get(META_KEY);
        const chunksReq = t.objectStore(CHUNK_STORE).getAll();
        t.oncomplete = () => {
          db.close();
          const meta = metaReq.result as SessionMeta | undefined;
          const buffers = (chunksReq.result as ArrayBuffer[]) ?? [];
          if (!meta || buffers.length === 0) {
            resolve(null);
            return;
          }
          resolve({ meta, audio: new Blob(buffers, { type: AUDIO_MIME }) });
        };
        t.onerror = () => { db.close(); reject(t.error); };
      }),
  );
}
