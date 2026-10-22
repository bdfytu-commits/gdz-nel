'use strict';

/* Офлайн-учебники в профиле. Отдельный классический скрипт: работает даже
   если модуль Supabase не загрузился (нет сети). */
(function () {
  var list = document.getElementById('offline-books');
  var empty = document.getElementById('offline-empty');
  var estimate = document.getElementById('offline-estimate');
  var status = document.getElementById('offline-status');
  if (!list || !empty || !estimate || !status) return;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatBytes(bytes) {
    var value = Number(bytes) || 0;
    if (value < 1024) return value + ' Б';
    if (value < 1024 * 1024) return (value / 1024).toFixed(1).replace('.', ',') + ' КБ';
    return (value / (1024 * 1024)).toFixed(1).replace('.', ',') + ' МБ';
  }

  function render() {
    if (!window.GdzOffline) {
      empty.textContent = 'Офлайн-хранилище недоступно в этом браузере.';
      return;
    }
    window.GdzOffline.listOfflineBooks().then(function (books) {
      list.innerHTML = books.map(function (book) {
        var href = 'app/index.html#/' + encodeURIComponent(book.grade || '') + '/' +
          encodeURIComponent(book.subject || '') + '/' + encodeURIComponent(book.id || '');
        var meta = [];
        if (book.taskCount) meta.push(book.taskCount + ' заданий');
        if (book.bytes) meta.push(formatBytes(book.bytes));
        if (book.imageCount) meta.push(book.imageCount + ' картинок');
        return '<li class="offline-book">' +
          '<span class="offline-book-main"><a class="offline-book-title" href="' + href + '">' +
          esc(book.title || book.file) + '</a>' +
          '<span class="offline-book-meta">' + esc((book.author ? book.author + ' · ' : '') + meta.join(' · ')) + '</span></span>' +
          '<span class="offline-actions">' +
          '<button class="btn btn-outline btn-sm" type="button" data-offline-remove="' + esc(book.file) + '">Удалить</button>' +
          '</span></li>';
      }).join('');
      empty.hidden = books.length > 0;
      window.GdzOffline.estimate().then(function (info) {
        estimate.textContent = info.books
          ? 'Всего: ' + info.books + ' ' + (info.books === 1 ? 'книга' : 'книг') + ' · ' +
            formatBytes(info.bytes) + ' · ' + info.tasks + ' заданий'
          : '';
      });
    }).catch(function (err) {
      status.className = 'form-status is-err';
      status.textContent = 'Не удалось прочитать офлайн-хранилище: ' + err.message;
    });
  }

  list.addEventListener('click', function (event) {
    var btn = event.target.closest('[data-offline-remove]');
    if (!btn) return;
    var file = btn.getAttribute('data-offline-remove');
    if (!window.confirm('Удалить учебник из офлайна? Скачанные задания и картинки будут удалены.')) return;
    btn.disabled = true;
    status.className = 'form-status';
    status.textContent = 'Удаляю…';
    window.GdzOffline.clearTextbookFromOffline(file).then(function () {
      status.className = 'form-status is-ok';
      status.textContent = 'Учебник удалён из офлайна.';
      render();
    }).catch(function (err) {
      btn.disabled = false;
      status.className = 'form-status is-err';
      status.textContent = 'Не удалось удалить: ' + err.message;
    });
  });

  window.addEventListener('gdz-offline-change', render);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
