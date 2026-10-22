'use strict';

/* =========================================================
   ГДЗ НЭЛ — офлайн-хранилище (IndexedDB).

   Хранит:
     books  — метаданные скачанных учебников;
     tasks  — задания (по одному, ключ "<file>::<number>");
     images — картинки решений (Blob, ключ — абсолютный URL).

   Публичный API (window.GdzOffline):
     downloadBook(book, onProgress)  — скачать учебник и картинки;
     saveTextbookToOffline(...)      — алиас downloadBook;
     getTaskFromOffline(file, num)   — задание или null;
     getBookFromOffline(file)        — { tasks: [...] } или null;
     listOfflineBooks()              — массив метаданных;
     isBookOffline(file)             — boolean;
     clearTextbookFromOffline(file)  — удалить учебник;
     getImage(url)                   — Blob или null;
     estimate()                      — { bytes, books }.
   ========================================================= */

(function () {
  var DB_NAME = 'gdz-nel-offline';
  var DB_VERSION = 1;
  var IMAGE_CONCURRENCY = 4;
  var dbPromise = null;

  function openDB() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise(function (resolve, reject) {
      if (!('indexedDB' in window)) {
        reject(new Error('IndexedDB не поддерживается'));
        return;
      }
      var request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = function () {
        var db = request.result;
        if (!db.objectStoreNames.contains('books')) {
          db.createObjectStore('books', { keyPath: 'file' });
        }
        if (!db.objectStoreNames.contains('tasks')) {
          var tasks = db.createObjectStore('tasks', { keyPath: 'key' });
          tasks.createIndex('file', 'file', { unique: false });
        }
        if (!db.objectStoreNames.contains('images')) {
          var images = db.createObjectStore('images', { keyPath: 'url' });
          images.createIndex('file', 'file', { unique: false });
        }
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error || new Error('Не удалось открыть IndexedDB')); };
    });
    return dbPromise;
  }

  function requestResult(request) {
    return new Promise(function (resolve, reject) {
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error || new Error('Ошибка IndexedDB')); };
    });
  }

  function transactionDone(tx) {
    return new Promise(function (resolve, reject) {
      tx.oncomplete = function () { resolve(); };
      tx.onerror = function () { reject(tx.error || new Error('Ошибка транзакции')); };
      tx.onabort = function () { reject(tx.error || new Error('Транзакция отменена')); };
    });
  }

  function normalizeUrl(url) {
    try {
      return new URL(url, location.href).href;
    } catch (err) {
      return String(url || '');
    }
  }

  function taskKey(file, number) {
    return file + '::' + String(number);
  }

  function notifyChange() {
    try {
      window.dispatchEvent(new CustomEvent('gdz-offline-change'));
    } catch (err) { /* старые браузеры */ }
  }

  function safeProgress(onProgress, payload) {
    if (typeof onProgress !== 'function') return;
    try { onProgress(payload); } catch (err) { /* не ломаем скачивание */ }
  }

  function collectImages(tasks) {
    var seen = Object.create(null);
    var urls = [];
    tasks.forEach(function (task) {
      var list = Array.isArray(task && task.images) ? task.images : [];
      list.forEach(function (raw) {
        var url = normalizeUrl(raw);
        if (!url || url.indexOf('data:') === 0 || seen[url]) return;
        seen[url] = true;
        urls.push(url);
      });
    });
    return urls;
  }

  function bookMeta(book, doc) {
    var tasks = (doc && Array.isArray(doc.tasks)) ? doc.tasks : [];
    return {
      file: book.file,
      id: book.id || '',
      title: book.title || '',
      author: book.author || '',
      year: book.year || '',
      grade: book.grade || '',
      gradeTitle: book.gradeTitle || '',
      subject: book.subject || '',
      subjectTitle: book.subjectTitle || '',
      taskCount: tasks.length,
      imageCount: 0,
      failedImages: 0,
      bytes: 0,
      downloadedAt: Date.now()
    };
  }

  function saveTasks(meta, tasks) {
    return openDB().then(function (db) {
      var tx = db.transaction('tasks', 'readwrite');
      var store = tx.objectStore('tasks');
      tasks.forEach(function (task, index) {
        store.put({
          key: taskKey(meta.file, task.number),
          file: meta.file,
          number: String(task.number),
          index: index,
          data: task
        });
      });
      return transactionDone(tx);
    });
  }

  function putBook(meta) {
    return openDB().then(function (db) {
      var tx = db.transaction('books', 'readwrite');
      tx.objectStore('books').put(meta);
      return transactionDone(tx).then(function () { return meta; });
    });
  }

  function putImage(db, file, url, blob) {
    return new Promise(function (resolve, reject) {
      var tx = db.transaction('images', 'readwrite');
      tx.objectStore('images').put({
        url: url,
        file: file,
        blob: blob,
        bytes: blob.size,
        type: blob.type || '',
        savedAt: Date.now()
      });
      tx.oncomplete = resolve;
      tx.onerror = function () { reject(tx.error || new Error('Не удалось сохранить картинку')); };
    });
  }

  // Скачивание картинок с ограничением параллельности. Ошибки CORS/404
  // не валят всё скачивание: текстовые задания уже доступны офлайн.
  function downloadImages(db, meta, urls, onProgress) {
    var total = urls.length;
    var done = 0;
    var failed = 0;
    var bytes = 0;
    if (!total) {
      safeProgress(onProgress, { phase: 'images', done: 0, total: 0, percent: 100 });
      return Promise.resolve({ failed: 0, bytes: 0, saved: 0 });
    }

    safeProgress(onProgress, { phase: 'images', done: 0, total: total, percent: 25 });

    return new Promise(function (resolve) {
      var next = 0;
      var saved = 0;

      function finishOne(ok, size) {
        done++;
        if (!ok) failed++;
        else {
          saved++;
          bytes += size || 0;
        }
        var percent = 25 + Math.round((done / total) * 75);
        safeProgress(onProgress, {
          phase: 'images', done: done, total: total, percent: percent, failed: failed
        });
        if (done >= total) {
          resolve({ failed: failed, bytes: bytes, saved: saved });
        } else {
          worker();
        }
      }

      function worker() {
        var index = next++;
        if (index >= total) return;
        var url = urls[index];
        fetch(url, { credentials: 'omit' })
          .then(function (res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return res.blob();
          })
          .then(function (blob) {
            if (!blob || !blob.size) throw new Error('пустой файл');
            return putImage(db, meta.file, url, blob).then(function () {
              finishOne(true, blob.size);
            });
          })
          .catch(function () {
            // CORS/404: попросим SW сохранить opaque-копию в Cache API
            try {
              if (navigator.serviceWorker && navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({ type: 'CACHE_IMAGES', urls: [url] });
              }
            } catch (err) { /* ignore */ }
            finishOne(false, 0);
          });
      }

      for (var i = 0; i < Math.min(IMAGE_CONCURRENCY, total); i++) worker();
    });
  }

  function saveTextbookToOffline(book, onProgress) {
    if (!book || !book.file) return Promise.reject(new Error('не указан файл учебника'));
    var url = book.url || ('data/' + book.file);
    return fetch(url, { cache: 'no-store' }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (doc) {
      var tasks = Array.isArray(doc.tasks) ? doc.tasks : [];
      if (!tasks.length) throw new Error('в учебнике нет заданий');
      var meta = bookMeta(book, doc);
      var textBytes = 0;
      try { textBytes = new Blob([JSON.stringify(tasks)]).size; } catch (err) { textBytes = 0; }
      meta.textBytes = textBytes;
      safeProgress(onProgress, { phase: 'tasks', done: 0, total: tasks.length, percent: 5 });
      return saveTasks(meta, tasks).then(function () {
        safeProgress(onProgress, {
          phase: 'tasks', done: tasks.length, total: tasks.length, percent: 25
        });
        return putBook(meta);
      }).then(function () {
        var urls = collectImages(tasks);
        return openDB().then(function (db) {
          return downloadImages(db, meta, urls, onProgress).then(function (result) {
            meta.imageCount = result.saved;
            meta.failedImages = result.failed;
            meta.bytes = result.bytes + textBytes;
            meta.downloadedAt = Date.now();
            return putBook(meta).then(function () {
              safeProgress(onProgress, { phase: 'done', done: 1, total: 1, percent: 100 });
              notifyChange();
              return meta;
            });
          });
        });
      });
    });
  }

  function getTaskFromOffline(file, number) {
    return openDB().then(function (db) {
      var tx = db.transaction('tasks', 'readonly');
      return requestResult(tx.objectStore('tasks').get(taskKey(file, number)));
    }).then(function (row) {
      return row ? row.data : null;
    });
  }

  function getBookFromOffline(file) {
    return openDB().then(function (db) {
      var tx = db.transaction('tasks', 'readonly');
      var index = tx.objectStore('tasks').index('file');
      return requestResult(index.getAll(IDBKeyRange.only(file)));
    }).then(function (rows) {
      if (!rows || !rows.length) return null;
      rows.sort(function (a, b) { return a.index - b.index; });
      return { tasks: rows.map(function (row) { return row.data; }) };
    });
  }

  function listOfflineBooks() {
    return openDB().then(function (db) {
      var tx = db.transaction('books', 'readonly');
      return requestResult(tx.objectStore('books').getAll());
    }).then(function (rows) {
      return (rows || []).sort(function (a, b) { return (b.downloadedAt || 0) - (a.downloadedAt || 0); });
    });
  }

  function isBookOffline(file) {
    return openDB().then(function (db) {
      var tx = db.transaction('books', 'readonly');
      return requestResult(tx.objectStore('books').get(file));
    }).then(function (row) { return !!row; });
  }

  function deleteByIndex(db, storeName, indexName, value) {
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(storeName, 'readwrite');
      var index = tx.objectStore(storeName).index(indexName);
      var cursor = index.openCursor(IDBKeyRange.only(value));
      cursor.onsuccess = function () {
        var row = cursor.result;
        if (!row) return;
        row.delete();
        row.continue();
      };
      tx.oncomplete = resolve;
      tx.onerror = function () { reject(tx.error || new Error('Не удалось удалить данные')); };
    });
  }

  function clearTextbookFromOffline(file) {
    return openDB().then(function (db) {
      return Promise.all([
        deleteByIndex(db, 'tasks', 'file', file),
        deleteByIndex(db, 'images', 'file', file)
      ]).then(function () {
        return new Promise(function (resolve, reject) {
          var tx = db.transaction('books', 'readwrite');
          tx.objectStore('books').delete(file);
          tx.oncomplete = resolve;
          tx.onerror = function () { reject(tx.error || new Error('Не удалось удалить учебник')); };
        });
      });
    }).then(function () {
      notifyChange();
      return true;
    });
  }

  function getImage(url) {
    var absolute = normalizeUrl(url);
    return openDB().then(function (db) {
      var tx = db.transaction('images', 'readonly');
      return requestResult(tx.objectStore('images').get(absolute));
    }).then(function (row) { return row ? row.blob : null; });
  }

  function estimate() {
    return listOfflineBooks().then(function (books) {
      var bytes = books.reduce(function (sum, book) { return sum + (book.bytes || 0); }, 0);
      var tasks = books.reduce(function (sum, book) { return sum + (book.taskCount || 0); }, 0);
      return { bytes: bytes, books: books.length, tasks: tasks };
    });
  }

  window.GdzOffline = {
    supported: (function () { try { return 'indexedDB' in window; } catch (err) { return false; } })(),
    downloadBook: saveTextbookToOffline,
    saveTextbookToOffline: saveTextbookToOffline,
    getTaskFromOffline: getTaskFromOffline,
    getBookFromOffline: getBookFromOffline,
    getTask: getTaskFromOffline,
    getBook: getBookFromOffline,
    listOfflineBooks: listOfflineBooks,
    listBooks: listOfflineBooks,
    isBookOffline: isBookOffline,
    clearTextbookFromOffline: clearTextbookFromOffline,
    removeBook: clearTextbookFromOffline,
    getImage: getImage,
    estimate: estimate
  };
})();
