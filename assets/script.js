'use strict';

/* ГДЗ НЭЛ — лендинг.
   Единственный скрипт: появление блоков при скролле (один раз, без повторения). */

(function () {
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var items = Array.prototype.slice.call(document.querySelectorAll('.reveal'));

  // если анимации отключены в системе или нет IntersectionObserver — показываем всё сразу
  if (reduced || !('IntersectionObserver' in window)) {
    return;
  }

  // прячем до появления; задержка создаёт лёгкую «лесенку» внутри одной сетки
  items.forEach(function (el) {
    var index = Array.prototype.indexOf.call(el.parentElement.children, el);
    el.style.transitionDelay = Math.min(index, 6) * 70 + 'ms';
    el.classList.add('is-hidden');
  });

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var el = entry.target;

      // после проигрывания убираем задержку, чтобы она не тормозила hover
      el.addEventListener('transitionend', function done() {
        el.style.transitionDelay = '0ms';
        el.removeEventListener('transitionend', done);
      });

      el.classList.remove('is-hidden');
      observer.unobserve(el); // один раз, при обратном скролле не повторяем
    });
  }, { threshold: 0.15, rootMargin: '0px 0px -30px 0px' });

  items.forEach(function (el) { observer.observe(el); });
})();
