// Last modified: 2026-09-18 — v4
(() => {
  'use strict';

  const tree = document.getElementById('tree');
  if (!tree) return;

  // Only context actions live here. Normal clicks and the original page design
  // remain owned by master_data_workspace.html.
  const style = document.createElement('style');
  style.textContent = `
    .master-context-menu{position:fixed;z-index:99999;min-width:190px;padding:5px;background:#fff;border:1px solid #dbe3ec;border-radius:10px;box-shadow:0 10px 30px rgba(15,23,42,.16);direction:rtl}
    .master-context-menu button{display:block;width:100%;border:0;background:transparent;text-align:right;padding:9px 11px;border-radius:7px;font:inherit;font-size:13px;font-weight:700;color:#26384e;cursor:pointer}
    .master-context-menu button:hover{background:#edf4fa;color:#173b63}
  `;
  document.head.appendChild(style);

  const menu = document.createElement('div');
  menu.className = 'master-context-menu';
  menu.hidden = true;
  menu.dir = 'rtl';
  document.body.appendChild(menu);

  const closeMenu = () => {
    menu.hidden = true;
    menu.replaceChildren();
  };

  const postDelete = (action, message) => {
    if (!window.confirm(message)) return;
    const form = document.createElement('form');
    form.method = 'post';
    form.action = action;
    form.style.display = 'none';
    document.body.appendChild(form);
    form.submit();
  };

  const editReference = (node) => {
    const kind = node.dataset.refItem;
    const id = node.dataset.id;
    if (!kind || !id || typeof refPanel !== 'function') return;
    refPanel(kind, id, node.dataset.name || '', node.dataset);
    if (typeof selectNode === 'function') selectNode(node);
  };

  const copyModel = (id) => {
    if (typeof editModel !== 'function') return;
    editModel(id);
    const name = document.getElementById('modelName');
    const hidden = document.getElementById('modelId');
    const form = document.getElementById('modelForm');
    if (name) name.value += ' - نسخة';
    if (hidden) hidden.value = '';
    if (form) form.action = '/equipment-types/models/create';
  };

  const showMenu = (node, x, y) => {
    const model = node.closest('[data-model-row]');
    const ref = node.closest('[data-ref-item]');
    const actions = [];

    if (model) {
      const id = model.dataset.modelRow;
      actions.push(['👁 عرض الطراز', () => typeof viewModel === 'function' && viewModel(id)]);
      actions.push(['✏️ تعديل الطراز', () => typeof editModel === 'function' && editModel(id)]);
      actions.push(['⧉ نسخ الطراز', () => copyModel(id)]);
      actions.push(['🗑 حذف الطراز', () => postDelete(
        '/equipment-types/models/' + encodeURIComponent(id) + '/delete',
        'حذف الطراز؟ سيتم تطبيق حماية النظام الحالية.'
      )]);
    } else if (ref) {
      const kind = ref.dataset.refItem;
      const id = ref.dataset.id;
      const labels = {category:'الفئة',type:'نوع العتاد',brand:'العلامة التجارية',spec:'الخاصية'};
      if (!labels[kind] || !id) return;

      actions.push(['✏️ تعديل ' + labels[kind], () => editReference(ref)]);
      if (kind === 'category') {
        actions.push(['🗑 حذف الفئة', () => postDelete(
          '/equipment-types/categories/' + encodeURIComponent(id) + '/delete',
          'حذف الفئة؟ إذا كانت مرتبطة بأنواع عتاد سيمنع النظام الحذف.'
        )]);
      } else if (kind === 'type') {
        actions.push(['🗑 حذف نوع العتاد', () => postDelete(
          '/equipment-types/' + encodeURIComponent(id) + '/delete',
          'حذف نوع العتاد؟ إذا كان مرتبطاً بطرازات سيمنع النظام الحذف.'
        )]);
      } else if (kind === 'brand') {
        actions.push(['🗑 حذف العلامة التجارية', () => postDelete(
          '/equipment-types/brands/' + encodeURIComponent(id) + '/delete',
          'حذف العلامة التجارية؟ إذا كانت مرتبطة بطرازات سيمنع النظام الحذف.'
        )]);
      }
    } else return;

    menu.replaceChildren();
    actions.forEach(([label, action]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.addEventListener('click', () => { closeMenu(); action(); });
      menu.appendChild(button);
    });

    menu.hidden = false;
    const rect = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(Number(x) || 8, innerWidth - rect.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(Number(y) || 8, innerHeight - rect.height - 8)) + 'px';
  };

  tree.addEventListener('contextmenu', (event) => {
    const node = event.target.closest('[data-model-row],[data-ref-item]');
    if (!node || !tree.contains(node)) return;
    event.preventDefault();
    event.stopPropagation();
    showMenu(node, event.clientX, event.clientY);
  });

  let timer = null;
  let target = null;
  let startX = 0;
  let startY = 0;

  const cancelLongPress = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    target = null;
  };

  tree.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'touch') return;
    const node = event.target.closest('[data-model-row],[data-ref-item]');
    if (!node || !tree.contains(node)) return;
    cancelLongPress();
    target = node;
    startX = event.clientX;
    startY = event.clientY;
    timer = setTimeout(() => {
      if (!target) return;
      showMenu(target, startX, startY);
      timer = null;
      target = null;
    }, 650);
  });

  tree.addEventListener('pointermove', (event) => {
    if (!timer || event.pointerType !== 'touch') return;
    if (Math.abs(event.clientX - startX) > 10 || Math.abs(event.clientY - startY) > 10) cancelLongPress();
  });

  ['pointerup','pointercancel','pointerleave'].forEach(type => tree.addEventListener(type, cancelLongPress));
  document.addEventListener('pointerdown', event => {
    if (!menu.hidden && !menu.contains(event.target)) closeMenu();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeMenu();
  });
})();