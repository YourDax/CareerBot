INDEX_HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>CareerBot</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #ffffff);
    --text: var(--tg-theme-text-color, #1c1c1e);
    --hint: var(--tg-theme-hint-color, #8e8e93);
    --link: var(--tg-theme-link-color, #2481cc);
    --btn: var(--tg-theme-button-color, #2481cc);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
    --card: var(--tg-theme-secondary-bg-color, #f2f2f7);
    --danger: #e5484d;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 16px/1.4 -apple-system, system-ui, "Segoe UI", sans-serif;
         padding: 12px 16px calc(76px + env(safe-area-inset-bottom)); }
  h2 { font-size: 20px; margin: 4px 0 12px; }
  .card { background: var(--card); border-radius: 14px; padding: 12px 14px; margin-bottom: 10px; }
  .row { display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
  .hint { color: var(--hint); font-size: 14px; }
  .title { font-weight: 600; }
  a { color: var(--link); text-decoration: none; word-break: break-all; }
  input, select, textarea { width: 100%; padding: 10px 12px; margin: 4px 0 8px; font: inherit; color: var(--text);
         background: var(--bg); border: 1px solid rgba(128,128,128,.3); border-radius: 10px; }
  textarea { min-height: 90px; resize: vertical; }
  button { font: inherit; border: 0; border-radius: 10px; padding: 10px 16px; background: var(--btn); color: var(--btn-text); }
  button.ghost { background: transparent; color: var(--link); padding: 6px 4px; }
  button.danger { background: var(--danger); }
  button:disabled { opacity: .5; }
  .big { font-size: 34px; font-weight: 700; text-align: center; margin: 8px 0; font-variant-numeric: tabular-nums; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0 10px; }
  .chip { background: var(--card); color: var(--text); border-radius: 999px; padding: 6px 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  td, th { text-align: left; padding: 6px 4px; border-bottom: 1px solid rgba(128,128,128,.2); }
  nav { position: fixed; left: 0; right: 0; bottom: 0; display: flex; background: var(--card);
        padding-bottom: env(safe-area-inset-bottom); border-top: 1px solid rgba(128,128,128,.2); }
  nav button { flex: 1; background: transparent; color: var(--hint); border-radius: 0; padding: 12px 4px; font-size: 13px; }
  nav button.active { color: var(--btn); font-weight: 600; }
  .toast { position: fixed; left: 16px; right: 16px; bottom: calc(80px + env(safe-area-inset-bottom)); background: #333; color: #fff;
           padding: 10px 14px; border-radius: 10px; text-align: center; display: none; }
</style>
</head>
<body>
<main id="view"></main>
<nav id="nav"></nav>
<div class="toast" id="toast"></div>
<script>
(function () {
  var tg = window.Telegram && window.Telegram.WebApp;
  if (tg) { tg.ready(); tg.expand(); }
  var S = { tab: 'apps', data: null, jobs: null, tick: null };
  var TABS = [['apps', 'Отклики'], ['time', 'Время'], ['jobs', 'Вакансии'], ['profile', 'Профиль']];

  // Весь текст из внешних источников вставляется только через textContent.
  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'on') Object.keys(attrs.on).forEach(function (e) { el.addEventListener(e, attrs.on[e]); });
      else if (k === 'class') el.className = attrs[k];
      else if (k === 'value') el.value = attrs[k];
      else el.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      el.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    }
    return el;
  }

  function toast(msg) {
    var t = document.getElementById('toast');
    t.textContent = msg; t.style.display = 'block';
    setTimeout(function () { t.style.display = 'none'; }, 2200);
  }

  function api(path, body) {
    var opts = { headers: { 'X-Init-Data': tg ? tg.initData : '' } };
    if (body !== undefined) { opts.method = 'POST'; opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch(path, opts).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (e) { throw new Error(e.detail || ('Ошибка ' + r.status)); });
      return r.json();
    });
  }

  function reload() { return api('/api/app/state').then(function (d) { S.data = d; render(); }); }
  function act(path, body, ok) {
    return api(path, body).then(function () { if (ok) toast(ok); return reload(); }).catch(function (e) { toast(e.message); });
  }
  function openLink(url) {
    if (!/^https?:\/\//.test(url)) return;
    if (tg && tg.openLink) tg.openLink(url); else window.open(url, '_blank');
  }
  function fmtDate(iso) { var d = new Date(iso); return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function clock(sec) { return Math.floor(sec / 3600) + ':' + pad(Math.floor(sec % 3600 / 60)) + ':' + pad(Math.floor(sec % 60)); }

  function viewApps() {
    var d = S.data, form = h('div', { class: 'card', style: 'display:none' });
    var f = { company: h('input', { placeholder: 'Компания' }), position: h('input', { placeholder: 'Позиция' }),
              url: h('input', { placeholder: 'Ссылка (необязательно)' }), days: h('input', { type: 'number', value: 7, min: 1, max: 90 }) };
    form.append(f.company, f.position, f.url, h('div', { class: 'hint' }, 'Напомнить через (дней)'), f.days,
      h('button', { on: { click: function () {
        if (!f.company.value.trim() || !f.position.value.trim()) return toast('Заполни компанию и позицию');
        act('/api/app/apply', { company: f.company.value, position: f.position.value, url: f.url.value || null,
                                 remind_days: parseInt(f.days.value, 10) || 7 }, 'Отклик добавлен');
      } } }, 'Сохранить'));
    var root = h('div', {}, h('h2', {}, 'Отклики'),
      h('button', { on: { click: function () { form.style.display = form.style.display === 'none' ? 'block' : 'none'; } } }, '+ Добавить отклик'),
      h('div', { style: 'height:10px' }), form);
    if (!d.apps.length) root.append(h('div', { class: 'hint' }, 'Откликов пока нет.'));
    d.apps.forEach(function (a) {
      var sel = h('select', { on: { change: function () { act('/api/app/status', { id: a.id, status: sel.value }, 'Статус обновлён'); } } });
      Object.keys(d.statuses).forEach(function (k) {
        var o = h('option', { value: k }, d.statuses[k]); if (k === a.status) o.selected = true; sel.append(o);
      });
      root.append(h('div', { class: 'card' },
        h('div', { class: 'row' }, h('span', { class: 'title' }, a.company), h('span', { class: 'hint' }, fmtDate(a.applied_at))),
        h('div', {}, a.position),
        a.url ? h('div', {}, h('a', { href: '#', on: { click: function (e) { e.preventDefault(); openLink(a.url); } } }, 'Открыть вакансию')) : null,
        sel));
    });
    return root;
  }

  function viewTime() {
    var d = S.data, root = h('div', {}, h('h2', {}, 'Время'));
    if (d.timer) {
      var big = h('div', { class: 'big' }, '0:00:00');
      var start = new Date(d.timer.started_at).getTime();
      function upd() { big.textContent = clock((Date.now() - start) / 1000); }
      upd(); S.tick = setInterval(upd, 1000);
      root.append(h('div', { class: 'card' }, h('div', { class: 'hint' }, 'Идёт: ' + d.timer.project), big,
        h('button', { class: 'danger', style: 'width:100%', on: { click: function () { act('/api/app/timer/stop', {}, 'Остановлен'); } } }, 'Стоп')));
    } else {
      var inp = h('input', { placeholder: 'Название проекта', list: 'projects' });
      var dl = h('datalist', { id: 'projects' }); d.recent_projects.forEach(function (p) { dl.append(h('option', { value: p })); });
      var chips = h('div', { class: 'chips' });
      d.recent_projects.slice(0, 6).forEach(function (p) { chips.append(h('button', { class: 'chip', on: { click: function () { inp.value = p; } } }, p)); });
      root.append(h('div', { class: 'card' }, inp, dl, chips,
        h('button', { style: 'width:100%', on: { click: function () {
          if (!inp.value.trim()) return toast('Укажи проект'); act('/api/app/timer/start', { project: inp.value }, 'Запущен'); } } }, 'Старт')));
    }
    var ip = h('input', { placeholder: 'Проект', list: 'projects' }), ia = h('input', { placeholder: 'Сумма', type: 'number', inputmode: 'decimal' });
    root.append(h('div', { class: 'card' }, h('div', { class: 'title' }, 'Записать доход'), ip, ia,
      h('button', { on: { click: function () {
        var amount = parseFloat(ia.value); if (!ip.value.trim() || !(amount > 0)) return toast('Укажи проект и сумму');
        act('/api/app/income', { project: ip.value, amount: amount }, 'Записано'); } } }, 'Сохранить')));
    var tbl = h('table', {}, h('tr', {}, h('th', {}, 'Проект'), h('th', {}, 'Часы'), h('th', {}, 'Доход'), h('th', {}, 'В час')));
    d.stats.forEach(function (s) {
      tbl.append(h('tr', {}, h('td', {}, s.project), h('td', {}, s.hours.toFixed(1)), h('td', {}, String(Math.round(s.earned))),
        h('td', {}, s.rate == null ? '—' : String(Math.round(s.rate)))));
    });
    root.append(h('div', { class: 'card' }, h('div', { class: 'title' }, 'Статистика'), d.stats.length ? tbl : h('div', { class: 'hint' }, 'Данных пока нет.')));
    return root;
  }

  function viewJobs() {
    var d = S.data, on = !!(d.profile && d.profile.digest);
    var box = h('div', {});
    function draw() {
      box.textContent = '';
      if (S.jobs === 'loading') return box.append(h('div', { class: 'hint' }, 'Ищу по источникам…'));
      if (!S.jobs) return;
      if (!S.jobs.length) return box.append(h('div', { class: 'hint' }, 'Новых подходящих вакансий нет.'));
      S.jobs.forEach(function (j) {
        box.append(h('div', { class: 'card' }, h('div', { class: 'title' }, j.title),
          h('div', { class: 'hint' }, (j.company ? j.company + ' · ' : '') + j.source + ' · ' + (j.freelance ? 'фриланс' : 'вакансия')),
          h('div', { class: 'hint' }, 'Совпало: ' + j.hits.join(', ')),
          h('a', { href: '#', on: { click: function (e) { e.preventDefault(); openLink(j.url); } } }, 'Открыть')));
      });
    }
    var cb = h('input', { type: 'checkbox', style: 'width:auto;margin:0' }); cb.checked = on;
    cb.addEventListener('change', function () { act('/api/app/digest', { enabled: cb.checked }, cb.checked ? 'Дайджест включён' : 'Дайджест выключен'); });
    draw();
    return h('div', {}, h('h2', {}, 'Вакансии и заказы'),
      h('button', { style: 'width:100%;margin-bottom:10px', on: { click: function () {
        S.jobs = 'loading'; draw();
        api('/api/app/jobs').then(function (r) { S.jobs = r; draw(); }).catch(function (e) { S.jobs = null; draw(); toast(e.message); });
      } } }, 'Подобрать по навыкам'),
      h('label', { class: 'row card' }, h('span', {}, 'Ежедневный дайджест в 11:00 МСК'), cb), box);
  }

  function viewProfile() {
    var p = S.data.profile || {};
    var f = { full_name: h('input', { value: p.full_name || '', placeholder: 'Имя' }), title: h('input', { value: p.title || '', placeholder: 'Должность' }),
              skills: h('textarea', { placeholder: 'Навыки через запятую' }), about: h('textarea', { placeholder: 'О себе' }) };
    f.skills.value = p.skills || ''; f.about.value = p.about || '';
    return h('div', {}, h('h2', {}, 'Профиль'), h('div', { class: 'card' },
      h('div', { class: 'hint' }, 'Имя'), f.full_name, h('div', { class: 'hint' }, 'Должность'), f.title,
      h('div', { class: 'hint' }, 'Навыки (по ним ищутся вакансии)'), f.skills, h('div', { class: 'hint' }, 'О себе'), f.about,
      h('button', { on: { click: function () {
        act('/api/app/profile', { full_name: f.full_name.value, title: f.title.value, skills: f.skills.value, about: f.about.value }, 'Профиль сохранён');
      } } }, 'Сохранить')),
      h('div', { class: 'card' }, h('a', { href: '#', on: { click: function (e) { e.preventDefault(); openLink(location.origin + '/portfolio'); } } }, 'Открыть портфолио-сайт')));
  }

  function render() {
    if (S.tick) { clearInterval(S.tick); S.tick = null; }
    var nav = document.getElementById('nav'); nav.textContent = '';
    TABS.forEach(function (t) {
      nav.append(h('button', { class: S.tab === t[0] ? 'active' : '', on: { click: function () { S.tab = t[0]; render(); } } }, t[1]));
    });
    var view = document.getElementById('view'); view.textContent = '';
    view.append({ apps: viewApps, time: viewTime, jobs: viewJobs, profile: viewProfile }[S.tab]());
  }

  reload().catch(function (e) {
    document.getElementById('view').textContent = 'Не удалось загрузить: ' + e.message + '. Открой приложение из бота.';
  });
})();
</script>
</body>
</html>
"""
