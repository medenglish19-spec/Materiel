/* Server-backed deletion impact confirmation shared by operational modules. */
(function (global) {
  'use strict';
  if (!document.getElementById('delete-impact-styles')) {
    const style = document.createElement('style');
    style.id = 'delete-impact-styles';
    style.textContent = '.delete-impact-backdrop{position:fixed;inset:0;z-index:2000;background:#11182788;display:flex;align-items:center;justify-content:center;padding:16px}.delete-impact-dialog{width:min(520px,100%);max-height:80vh;overflow:auto;background:#fff;border-radius:10px;padding:20px;box-shadow:0 18px 50px #0003;color:#111827}.delete-impact-dialog h2{font:700 18px Cairo,sans-serif;margin:0 0 10px}.delete-impact-intro{margin:0 0 10px;color:#4b5563}.delete-impact-dialog ul{padding-right:22px;line-height:1.8;font-size:13px}.delete-impact-dialog footer{display:flex;gap:8px;justify-content:flex-start;margin-top:18px}.delete-impact-dialog button{border:1px solid #d1d5db;border-radius:6px;padding:9px 14px;background:#fff;cursor:pointer;font:inherit}.delete-impact-dialog .delete-impact-confirm{background:#b91c1c;border-color:#b91c1c;color:#fff}.delete-impact-dialog .delete-impact-confirm:disabled{opacity:.45;cursor:not-allowed}.delete-impact-blocked{color:#b91c1c;font-weight:700}.delete-impact-warning{color:#9a6700;font-weight:700}';
    document.head.append(style);
  }
  function show(rows, title, blocked) {
    return new Promise(resolve => {
      const backdrop = document.createElement('div');
      backdrop.className = 'delete-impact-backdrop';
      backdrop.innerHTML = '<section class="delete-impact-dialog" role="dialog" aria-modal="true" aria-labelledby="deleteImpactTitle"><h2 id="deleteImpactTitle"></h2><p class="delete-impact-intro">سيؤدي هذا الحذف إلى الآثار التالية:</p><ul></ul><footer><button type="button" class="delete-impact-cancel">إلغاء</button><button type="button" class="delete-impact-confirm">تأكيد الحذف</button></footer></section>';
      backdrop.querySelector('h2').textContent = title || 'تأكيد الحذف';
      const list = backdrop.querySelector('ul');
      (rows || []).filter(row => Number(row.count) > 0).forEach(row => {
        const li = document.createElement('li');
        li.textContent = row.kind === 'blocked' ? row.label : row.kind === 'warning' ? `تنبيه: ${row.label}` : `${row.label}: ${row.count}${row.kind === 'unlink' ? ' (سيبقى السجل دون ارتباط)' : row.kind === 'remain' ? ' (سيبقى محفوظًا)' : row.kind === 'recalculate' ? ' (سيعاد احتسابه)' : ''}`;
        if (row.kind === 'blocked') li.className = 'delete-impact-blocked';
        if (row.kind === 'warning') li.className = 'delete-impact-warning';
        list.append(li);
      });
      if (!list.children.length) {
        const li = document.createElement('li'); li.textContent = 'لن تتأثر سجلات أخرى.'; list.append(li);
      }
      if (blocked) { const li = document.createElement('li'); li.className = 'delete-impact-blocked'; li.textContent = `الحذف ممنوع: ${blocked}`; list.prepend(li); backdrop.querySelector('.delete-impact-confirm').disabled = true; }
      const finish = value => { backdrop.remove(); resolve(value); };
      backdrop.querySelector('.delete-impact-cancel').addEventListener('click', () => finish(false));
      backdrop.querySelector('.delete-impact-confirm').addEventListener('click', () => finish(true));
      backdrop.addEventListener('click', event => { if (event.target === backdrop) finish(false); });
      document.addEventListener('keydown', function escape(event) { if (event.key === 'Escape' && backdrop.isConnected) { document.removeEventListener('keydown', escape); finish(false); } });
      document.body.append(backdrop);
      backdrop.querySelector('.delete-impact-cancel').focus();
    });
  }
  async function get(url) {
    const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail && data.detail !== 'Not Found'
        ? data.detail
        : response.status === 404
          ? 'مسار معاينة الحذف أو السجل غير متاح على الخادم الحالي. لم يتم حذف أي بيانات.'
          : 'تعذر تحميل أثر الحذف. لم يتم حذف أي بيانات.';
      throw new Error(detail);
    }
    return data;
  }
  async function confirmOne(url, title) {
    try {
      const data = await get(url);
      return await show(data.effects || [], title || (data.label ? `حذف «${data.label}»؟` : 'تأكيد الحذف'), data.blocked);
    } catch (error) {
      global.alert(error.message || 'تعذر التحقق من أثر الحذف. لم يتم حذف أي بيانات.');
      return false;
    }
  }
  async function confirmMany(urls, title) {
    try {
      const previews = await Promise.all(urls.map(get));
      const rows = [];
      const blocked = [];
      previews.forEach(preview => {
        rows.push({ label: preview.label || 'عنصر', count: 1 });
        (preview.effects || []).forEach(effect => rows.push({ ...effect, label: `${preview.label || 'العنصر'} — ${effect.label}` }));
        if (preview.blocked) blocked.push(`${preview.label || 'العنصر'}: ${preview.blocked}`);
      });
      return await show(rows, title || 'مراجعة أثر الحذف المحدد', blocked.join('؛ ') || null);
    } catch (error) {
      global.alert(error.message || 'تعذر التحقق من أثر الحذف. لم يتم حذف أي بيانات.');
      return false;
    }
  }
  document.addEventListener('submit', async event => {
    const form = event.target.closest('form[data-delete-impact]');
    if (!form || form.dataset.deleteImpactApproved === '1') return;
    event.preventDefault();
    const button = form.querySelector('[type="submit"]');
    if (button) button.disabled = true;
    try {
      if (await confirmOne(form.dataset.deleteImpact, form.dataset.deleteImpactTitle)) {
        form.dataset.deleteImpactApproved = '1';
        form.requestSubmit(button || undefined);
        setTimeout(() => { delete form.dataset.deleteImpactApproved; }, 0);
      }
    } catch (error) { global.alert(error.message || 'تعذر التحقق من أثر الحذف.'); }
    finally { if (button && form.isConnected) button.disabled = false; }
  });
  global.MaterielDeleteImpact = { confirmOne, confirmMany };
})(window);
