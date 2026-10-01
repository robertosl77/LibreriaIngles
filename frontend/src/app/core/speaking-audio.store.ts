import { Injectable } from '@angular/core';

import { RecordedAudio } from '../shared/audio-recorder.component';

export interface StoredSpeakingAudio {
  key: string;
  classId: number;
  attempt: number;
  exerciseId: number;
  blob: Blob;
  durationMs: number;
  mimeType: string;
  processed: boolean;
  updatedAt: string;
}

const DB_NAME = 'libreria-ingles-audio-drafts';
const DB_VERSION = 1;
const STORE = 'speaking-audios';

@Injectable({ providedIn: 'root' })
export class SpeakingAudioStore {
  async put(
    classId: number,
    attempt: number,
    exerciseId: number,
    recording: RecordedAudio
  ): Promise<void> {
    const row: StoredSpeakingAudio = {
      key: this.key(classId, attempt, exerciseId),
      classId,
      attempt,
      exerciseId,
      blob: recording.blob,
      durationMs: recording.durationMs,
      mimeType: recording.blob.type || 'audio/webm',
      processed: false,
      updatedAt: new Date().toISOString()
    };
    await this.request('readwrite', (store) => store.put(row));
  }

  async get(
    classId: number,
    attempt: number,
    exerciseId: number
  ): Promise<StoredSpeakingAudio | null> {
    const row = await this.request<StoredSpeakingAudio | undefined>(
      'readonly',
      (store) => store.get(this.key(classId, attempt, exerciseId))
    );
    return row ?? null;
  }

  async markProcessed(classId: number, attempt: number, exerciseId: number): Promise<void> {
    const row = await this.get(classId, attempt, exerciseId);
    if (!row) return;
    row.processed = true;
    row.updatedAt = new Date().toISOString();
    await this.request('readwrite', (store) => store.put(row));
  }

  async markUnprocessed(classId: number, attempt: number, exerciseId: number): Promise<void> {
    const row = await this.get(classId, attempt, exerciseId);
    if (!row || !row.processed) return;
    row.processed = false;
    row.updatedAt = new Date().toISOString();
    await this.request('readwrite', (store) => store.put(row));
  }

  async clearAttempt(classId: number, attempt: number): Promise<void> {
    const rows = await this.request<StoredSpeakingAudio[]>('readonly', (store) => store.getAll());
    const matching = (rows ?? []).filter((row) => row.classId === classId && row.attempt === attempt);
    if (!matching.length) return;

    const db = await this.open();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      const store = tx.objectStore(STORE);
      matching.forEach((row) => store.delete(row.key));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error('No se pudo limpiar el audio local.'));
      tx.onabort = () => reject(tx.error ?? new Error('No se pudo limpiar el audio local.'));
    });
    db.close();
  }

  private key(classId: number, attempt: number, exerciseId: number): string {
    return classId + ':' + attempt + ':' + exerciseId;
  }

  private async open(): Promise<IDBDatabase> {
    if (!('indexedDB' in window)) {
      throw new Error('Este navegador no permite guardar temporalmente la grabación.');
    }
    return new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'key' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(request.error ?? new Error('No se pudo abrir el almacenamiento local.'));
    });
  }

  private async request<T = unknown>(
    mode: IDBTransactionMode,
    action: (store: IDBObjectStore) => IDBRequest<T>
  ): Promise<T> {
    const db = await this.open();
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const request = action(tx.objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error('No se pudo guardar el audio local.'));
      tx.oncomplete = () => db.close();
      tx.onerror = () => {
        db.close();
        reject(tx.error ?? new Error('No se pudo guardar el audio local.'));
      };
      tx.onabort = () => {
        db.close();
        reject(tx.error ?? new Error('No se pudo guardar el audio local.'));
      };
    });
  }
}
