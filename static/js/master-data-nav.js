(() => {
  'use strict';
  /* تنقّل مركز البيانات الأساسية: شرائح الفئات (الفئة عنوان رئيسي، وتحتَها أنواع العتاد
     ثم طرازاتها). كل عملية قائمة في الواجهة القديمة موجودة هنا بنفس نقاطها:
     إنشاء/تعديل/حذف الفئة والنوع والطراز · نسخ الطراز · نقل الطراز بالسحب بين الأنواع ·
     فتح قسم من أقسام الطراز في المحرر · البحث · توسيب/طي · تصدير البنية · قائمة السياق. */
  const nav = document.getElementById('nav');
  if (!nav) return;
  const $ = (id) => document.getElementById(id);
  const sectionMap = { basic: 0, tires: 1, sizes: 1, batteries: 2, specs: 3 };
  const masterData = () => (window.MATERIEL_MASTER_DATA && window.MATERIEL_MASTER_DATA.DATA) || {};
  /* The inline workspace script owns refPanel/editModel/viewModel/... and publishes them on window.
     If it failed to run, say so instead of leaving the buttons silently dead. */
  const workspaceReady = (...names) => {
    const missing = names.filter((name) => typeof window[name] !== 'function');
    if (!missing.length) return true;
    console.error('Master Data workspace API missing:', missing.join(', '));
    toast('تعذر تحميل مساحة العمل بالكامل؛ أعد تحميل الصفحة (Ctrl+F5).');
    return false;
  };
  const selectNode = (node) => {
    nav.querySelectorAll('.tree-node.active').forEach((item) => item.classList.remove('active'));
    node?.classList.add('active');
  };
  const syncArrows = () => nav.querySelectorAll('.tree-toggle').forEach((toggle) => {
    toggle.textContent = toggle.closest('.tree-group')?.classList.contains('open') ? '⌄' : '›';
  });
  const toggleGroup = (node) => {
    const group = node?.closest('.tree-group');
    if (!group) return;
    group.classList.toggle('open');
    syncArrows();
  };
  const selectSection = (index, options = {}) => {
    const boxes = [...document.querySelectorAll('#modelPanel [data-workspace-section]')];
    const tabs = [...document.querySelectorAll('[data-model-workspace-tab]')];
    if (!boxes.length) return;
    const safe = Math.max(0, Math.min(Number(index) || 0, boxes.length - 1));
    const showAll = options.all === true;
    boxes.forEach((box, i) => { const visible = showAll || i === safe; box.hidden = !visible; box.setAttribute('aria-hidden', visible ? 'false' : 'true'); });
    tabs.forEach((tab, i) => { const active = i === safe; tab.classList.toggle('is-active', active); tab.setAttribute('aria-selected', active ? 'true' : 'false'); });
    if (options.focus) boxes[safe]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };
  window.MATERIEL_MODEL_WORKSPACE_SELECT = selectSection;
  /* Section name -> box index. The inline workspace script opens the editor on a
     named section (sheets click, ✎ تعديل الطراز); without this map it could only
     ever ask for a number and would guess wrong for tires/positions/sizes. */
  window.MATERIEL_MODEL_WORKSPACE_SECTIONS = sectionMap;

  /* "＋" beside a category  ->  refPanel('type', null, '', {categoryId: CATEGORY_ID}) with the category preselected. */
  const openTypeCreate = (categoryId) => {
    if (!workspaceReady('refPanel')) return;
    const id = String(categoryId || '');
    window.refPanel('type', null, '', { categoryId: id });
    const input = document.querySelector('#refBody form [name="category_id"]');
    if (input && id) input.value = id;
    document.querySelector('#refBody form [name="name"]')?.focus();
  };
  /* "＋" beside a type  ->  new model form with equipment_type_id preselected from that type. */
  const openModelCreate = (typeId) => {
    if (!workspaceReady('openNewModel')) return;
    window.openNewModel(typeId ? String(typeId) : '');
    selectSection(0, { all: true });
  };
  window.openTypeCreate = openTypeCreate;
  window.openModelCreate = openModelCreate;
  const editReference = (node) => {
    if (!workspaceReady('refPanel')) return;
    window.refPanel(node.dataset.refItem, node.dataset.id, node.dataset.name || '', node.dataset);
    selectNode(node);
  };
  const copyModel = (id) => {
    if (!workspaceReady('editModel')) return;
    window.editModel(id);
    selectSection(0, { all: true });
    if ($('modelName')) $('modelName').value += ' - نسخة';
    if ($('modelId')) $('modelId').value = '';
    if ($('modelForm')) $('modelForm').action = '/equipment-types/models/create';
  };
  const postDelete = (url, message) => {
    if (!confirm(message)) return;
    const form = document.createElement('form');
    form.method = 'post'; form.action = url; form.hidden = true;
    document.body.appendChild(form); form.submit();
  };

  const menu = document.createElement('div');
  menu.className = 'master-context-menu'; menu.hidden = true; menu.dir = 'rtl';
  document.body.appendChild(menu);
  const closeMenu = () => { menu.hidden = true; menu.replaceChildren(); };
  const showMenu = (node, x, y) => {
    const model = node.closest('[data-model-row]');
    const ref = node.closest('[data-ref-item]');
    const actions = [];
    if (model) {
      const id = model.dataset.modelRow;
      actions.push(['👁 عرض الطراز', () => window.viewModel?.(id)]);
      actions.push(['✏️ تعديل الطراز', () => window.editModel?.(id)]);
      actions.push(['⧉ نسخ الطراز', () => copyModel(id)]);
      actions.push(['🗑 حذف الطراز', () => postDelete(`/equipment-types/models/${encodeURIComponent(id)}/delete`, 'حذف الطراز؟')]);
    } else if (ref) {
      const id = ref.dataset.id; const kind = ref.dataset.refItem;
      const labels = { category: 'الفئة', type: 'نوع العتاد', brand: 'العلامة التجارية', spec: 'الخاصية' };
      if (!id || !labels[kind]) return;
      actions.push([`✏️ تعديل ${labels[kind]}`, () => editReference(ref)]);
      const routes = { category: `/equipment-types/categories/${id}/delete`, type: `/equipment-types/${id}/delete`, brand: `/equipment-types/brands/${id}/delete` };
      if (routes[kind]) actions.push([`🗑 حذف ${labels[kind]}`, () => postDelete(routes[kind], `حذف ${labels[kind]}؟`)]);
    } else return;
    menu.replaceChildren();
    actions.forEach(([label, action]) => { const button = document.createElement('button'); button.type = 'button'; button.textContent = label; button.onclick = () => { closeMenu(); action(); }; menu.appendChild(button); });
    menu.hidden = false;
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(x, innerWidth - rect.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, innerHeight - rect.height - 8))}px`;
  };

  /* The template renders the whole hierarchy server-side (فئة ← أنواع ← طرازات) with
     every parent id already on the child, so the only normalisation left is the
     drag payload of each model row and its parent type. */
  const prepareSheets = () => {
    const store = masterData();
    nav.querySelectorAll('[data-model-row]').forEach((row) => {
      const modelId = String(row.dataset.modelRow || '');
      const typeId = String(row.dataset.equipmentTypeId || '');
      if (modelId && store[modelId]) store[modelId].equipment_type_id = typeId || store[modelId].equipment_type_id;
      row.draggable = true;
    });
  };

  const search = $('navSearch');
  search?.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    const matches = (group) => !query || group.textContent.toLocaleLowerCase().includes(query);
    nav.querySelectorAll('.model-group, .type-group, .mdx-sheet').forEach((group) => {
      group.hidden = !matches(group);
      if (query && !group.classList.contains('model-group')) group.classList.add('open');
    });
    syncArrows();
  });

  nav.addEventListener('contextmenu', (event) => { const node = event.target.closest('[data-model-row],[data-ref-item]'); if (!node) return; event.preventDefault(); showMenu(node, event.clientX, event.clientY); });
  let timer; let pressTarget; let sx; let sy;
  const cancelPress = () => { clearTimeout(timer); timer = null; pressTarget = null; };
  nav.addEventListener('pointerdown', (event) => { if (event.pointerType !== 'touch') return; const node = event.target.closest('[data-model-row],[data-ref-item]'); if (!node) return; cancelPress(); pressTarget = node; sx = event.clientX; sy = event.clientY; timer = setTimeout(() => { showMenu(pressTarget, sx, sy); cancelPress(); }, 650); });
  nav.addEventListener('pointermove', (event) => { if (timer && (Math.abs(event.clientX - sx) > 10 || Math.abs(event.clientY - sy) > 10)) cancelPress(); });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach((type) => nav.addEventListener(type, cancelPress));

  const exportStructure = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      categories: [...nav.querySelectorAll('[data-ref-item="category"]')].map((node) => ({ id: node.dataset.id || '', name: node.dataset.name || '' })),
      types: [...nav.querySelectorAll('[data-ref-item="type"]')].map((node) => ({ id: node.dataset.id || '', name: node.dataset.name || '', category_id: node.dataset.categoryId || '' })),
      models: [...nav.querySelectorAll('[data-model-row]')].map((node) => ({ id: node.dataset.modelRow || '', name: node.querySelector('.model-text')?.textContent.trim() || '', equipment_type_id: node.dataset.equipmentTypeId || '' }))
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = 'materiel-equipment-structure.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast('تم تصدير بنية الفئات والأنواع والطرازات');
  };

  $('btn-export-structure')?.addEventListener('click', exportStructure);
  $('btn-nav-expand-all')?.addEventListener('click', () => {
    nav.querySelectorAll('.mdx-sheet, .type-group').forEach((group) => group.classList.add('open'));
    syncArrows();
  });
  $('btn-nav-collapse-all')?.addEventListener('click', () => {
    nav.querySelectorAll('.mdx-sheet, .type-group, .model-group').forEach((group) => group.classList.remove('open'));
    syncArrows();
  });
  $('btn-add-root-category')?.addEventListener('click', () => {
    if (workspaceReady('refPanel')) refPanel('category');
  });

  let dragged = null;
  nav.addEventListener('dragstart', (event) => { const row = event.target.closest('[data-model-row]'); if (!row) return; dragged = row; row.classList.add('dragging'); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', row.dataset.modelRow); });
  nav.addEventListener('dragend', () => { dragged?.classList.remove('dragging'); dragged = null; });
  nav.addEventListener('dragover', (event) => { const target = event.target.closest('[data-type-id]'); if (dragged && target) { event.preventDefault(); target.classList.add('drop-target'); } });
  nav.addEventListener('dragleave', (event) => event.target.closest('[data-type-id]')?.classList.remove('drop-target'));
  const toast = (message, action) => {
    const box = document.getElementById('nav-toast');
    const msg = document.getElementById('toast-message');
    if (!box || !msg) return;
    msg.textContent = message;
    let undo = box.querySelector('[data-nav-toast-action]');
    if (!undo) {
      undo = document.createElement('button');
      undo.type = 'button';
      undo.dataset.navToastAction = '1';
      undo.className = 'nav-toast-action';
      undo.textContent = 'تراجع';
      box.appendChild(undo);
    }
    undo.hidden = typeof action !== 'function';
    undo.onclick = typeof action === 'function' ? async () => {
      undo.disabled = true;
      try { await action(); }
      finally { undo.disabled = false; }
    } : null;
    box.hidden = false;
    clearTimeout(window.__materielNavToast);
    window.__materielNavToast = setTimeout(() => {
      box.hidden = true;
      undo.hidden = true;
    }, 5000);
  };
  nav.addEventListener('drop', async (event) => {
    const target = event.target.closest('[data-type-id]');
    if (!dragged || !target) return;
    event.preventDefault(); target.classList.remove('drop-target');
    const id = dragged.dataset.modelRow; const typeId = target.dataset.typeId;
    const model = masterData()[String(id)] || {};
    if (String(model.equipment_type_id) === String(typeId)) return;
    const form = new FormData(); form.append('equipment_type_id', typeId);
    try {
      const response = await fetch('/equipment-types/models/' + encodeURIComponent(id) + '/move', {method:'POST', body:form, credentials:'same-origin'});
      if (!response.ok) throw new Error('move failed');
      let undone = false;
      const undoMove = async () => {
        if (undone) return;
        const undoForm = new FormData();
        undoForm.append('equipment_type_id', String(model.equipment_type_id || ''));
        const undoResponse = await fetch('/equipment-types/models/' + encodeURIComponent(id) + '/move', { method: 'POST', body: undoForm, credentials: 'same-origin' });
        if (!undoResponse.ok) throw new Error('undo failed');
        undone = true;
        toast('تم التراجع عن نقل الطراز');
        window.setTimeout(() => window.location.reload(), 250);
      };
      toast('تم نقل الطراز إلى نوع العتاد الجديد', undoMove);
      window.setTimeout(() => { if (!undone) window.location.reload(); }, 5200);
    } catch (_) { toast('تعذر نقل الطراز؛ لم يتم تغيير البيانات'); }
  });

  /* Single owner of every click inside #nav (the inline workspace script no longer binds one).
     Capture phase + stopPropagation on the "action" branches guarantees that a "＋" or "✎"
     inside a row never also selects/toggles/edits that row. */
  const stop = (event) => { event.preventDefault(); event.stopPropagation(); };
  nav.addEventListener('click', (event) => {
    const action = event.target.closest('[data-add],[data-new-ref]');
    if (action) {
      stop(event);
      const kind = action.dataset.add || action.dataset.newRef;
      if (kind === 'type') openTypeCreate(action.dataset.newTypeForCategory);
      else if (kind === 'model') openModelCreate(action.dataset.newModelForType);
      else if (typeof refPanel === 'function') refPanel(kind);
      else workspaceReady('refPanel');
      return;
    }
    const position = event.target.closest('[data-tree-add]');
    if (position) {
      stop(event);
      const targetModel = event.target.closest('[data-model]');
      if (targetModel && workspaceReady('editModel', 'addSize')) {
        window.editModel(targetModel.dataset.model, 'tires');
        selectSection(sectionMap.tires, { focus: true });
        window.addSize();
      }
      return;
    }
    const copy = event.target.closest('[data-copy]');
    if (copy) { stop(event); copyModel(copy.dataset.copy); return; }
    const del = event.target.closest('[data-delete]');
    if (del) { stop(event); postDelete(`/equipment-types/models/${encodeURIComponent(del.dataset.delete)}/delete`, 'حذف الطراز؟'); return; }
    const edit = event.target.closest('[data-edit]');
    if (edit) { stop(event); selectNode(edit.closest('[data-model-row]')); if (workspaceReady('editModel')) { window.editModel(edit.dataset.edit); selectSection(0, { all: true }); } return; }
    const toggle = event.target.closest('.tree-toggle');
    if (toggle) { stop(event); const group = toggle.closest('.tree-group'); group.classList.toggle('open'); syncArrows(); return; }
    const expand = event.target.closest('[data-expand]');
    if (expand) { stop(event); toggleGroup(expand); return; }
    const row = event.target.closest('[data-model-row]');
    if (row) {
      selectNode(row); row.closest('.tree-group')?.classList.add('open'); syncArrows();
      if (workspaceReady('viewModel')) { window.viewModel(row.dataset.modelRow); selectSection(0, { all: true }); }
      return;
    }
    const model = event.target.closest('[data-model]');
    if (model) {
      stop(event); selectNode(model.closest('[data-model-row]') || model);
      if (workspaceReady('viewModel')) { window.viewModel(model.dataset.model); selectSection(sectionMap[model.dataset.section || 'basic'] || 0, { focus: true }); }
      return;
    }
    const ref = event.target.closest('[data-ref-item]');
    if (ref) {
      selectNode(ref);
      if (ref.dataset.system === '1') { toggleGroup(ref); return; }
      editReference(ref);
      return;
    }
    const node = event.target.closest('.tree-node');
    if (node) {
      selectNode(node);
      const group = node.closest('.tree-group');
      if (group && node.querySelector('.tree-toggle')) { group.classList.toggle('open'); syncArrows(); }
    }
  }, true);

  const style = document.createElement('style');
  style.textContent = `.master-context-menu{position:fixed;z-index:99999;min-width:200px;padding:6px;background:#fff;border:1px solid rgba(18,53,36,.1);border-radius:12px;box-shadow:0 18px 44px rgba(16,60,32,.2);direction:rtl}.master-context-menu button{display:block;width:100%;border:0;background:transparent;text-align:right;padding:10px 12px;border-radius:8px;font:inherit;font-weight:700;color:#2e5a3a;cursor:pointer;transition:background .14s ease,color .14s ease}.master-context-menu button:hover{background:#eaf7ef;color:#0f3d21}.model-line[draggable=true]{cursor:grab}.model-line.dragging{opacity:.45}.type-group.drop-target{outline:2px dashed var(--accent-2);outline-offset:2px;border-radius:14px;background:#eaf7ef}@media(max-width:640px){.master-context-menu{max-width:calc(100vw - 16px)}}`;
  document.head.appendChild(style);
  prepareSheets();
  syncArrows(); selectSection(0);
})();
