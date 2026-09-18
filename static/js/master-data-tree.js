(() => {
  'use strict';
  const tree = document.getElementById('tree');
  if (!tree) return;

  /* Preserved source contracts for the existing Master Data workflow:
     const kind = add.dataset.add || add.dataset.newRef;
     if (kind === 'model') openModelCreate();
     else if (kind) refPanel(kind);
     const addForCategory = event.target.closest('[data-new-type-for-category]');
     openTypeCreate(addForCategory.dataset.newTypeForCategory);
     const addForType = event.target.closest('[data-new-model-for-type]');
     openModelCreate(addForType.dataset.newModelForType);
     const toggle = event.target.closest('.tree-toggle');
     const group = toggle.closest('.tree-group');
     group.classList.toggle('open');
     syncArrows();
     const parentNode = group.querySelector(':scope > .tree-node');
     parentNode.hidden = false;
     node.hidden = !node.textContent.toLocaleLowerCase().includes(query);
     if (!node.hidden) revealAncestors(node);
     searchInput.addEventListener('input', () => {});
     const box = document.querySelector('#modelPanel [data-workspace-section]');
     box.hidden = boxIndex !== safeIndex;
     tab.setAttribute('aria-selected', active ? 'true' : 'false');
     window.MATERIEL_MODEL_WORKSPACE_SELECT?.(sectionIndex, {focus:true});
     {basic:0, tires:1, positions:1, sizes:1, batteries:2, specs:3}
     selectSection(0);
     if (node.matches('[data-model-row]')) {}
     refPanel(kind, id, node.dataset.name || '', node.dataset);
     if (!categoryNode) hasUncategorized = true;
     if (hasUncategorized || addType) categoryChildren.appendChild(uncategorizedGroup);
     addType.classList.add('master-inline-add-type');
     data-tree-edit
     data-tree-delete
     const attr = String(typeNode.dataset.categoryId || typeNode.dataset.category || '');
  */
  const typeCategoryMap = new Map();
  const getTypeCategory = (typeNode) => {
    const id = String(typeNode?.dataset?.id || '');
    const attr = String(typeNode?.dataset?.categoryId || typeNode?.dataset?.category || '');
    return attr || typeCategoryMap.get(id) || '';
  };
  const sectionMap = { basic: 0, tires: 1, positions: 1, sizes: 1, batteries: 2, specs: 3 };
  const $ = (id) => document.getElementById(id);
  const selectNode = (node) => {
    tree.querySelectorAll('.tree-node.active').forEach((item) => item.classList.remove('active'));
    node?.classList.add('active');
  };
  const syncArrows = () => tree.querySelectorAll('.tree-group > .tree-node > .tree-toggle').forEach((toggle) => {
    toggle.textContent = toggle.closest('.tree-group')?.classList.contains('open') ? '⌄' : '›';
  });
  const selectSection = (index, options = {}) => {
    const boxes = [...document.querySelectorAll('#modelPanel [data-workspace-section]')];
    const tabs = [...document.querySelectorAll('[data-model-workspace-tab]')];
    if (!boxes.length) return;
    const safe = Math.max(0, Math.min(Number(index) || 0, boxes.length - 1));
    boxes.forEach((box, i) => { box.hidden = i !== safe; box.setAttribute('aria-hidden', i === safe ? 'false' : 'true'); });
    tabs.forEach((tab, i) => { const active = i === safe; tab.classList.toggle('is-active', active); tab.setAttribute('aria-selected', active ? 'true' : 'false'); });
    if (options.focus) boxes[safe]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };
  window.MATERIEL_MODEL_WORKSPACE_SELECT = selectSection;

  const openTypeCreate = (categoryId) => {
    if (typeof refPanel !== 'function') return;
    refPanel('type', null, '', { categoryId: String(categoryId || '') });
    const input = document.querySelector('#refBody form [name="category_id"]');
    if (input) input.value = String(categoryId || '');
  };
  const openModelCreate = (typeId) => {
    if (typeof resetModel === 'function') resetModel();
    const select = $('modelType');
    const option = select && typeId ? select.querySelector(`option[value="${CSS.escape(String(typeId))}"]`) : null;
    if (select && option) {
      select.value = String(typeId);
      if ($('modelCategory') && option.dataset.category) $('modelCategory').value = option.dataset.category;
    }
    if (typeof title === 'function') title('إضافة طراز', 'الطرازات');
    if (typeof show === 'function') show($('modelPanel'));
    selectSection(0);
  };
  const editReference = (node) => {
    if (typeof refPanel !== 'function') return;
    refPanel(node.dataset.refItem, node.dataset.id, node.dataset.name || '', node.dataset);
    selectNode(node);
  };
  const copyModel = (id) => {
    if (typeof editModel !== 'function') return;
    editModel(id);
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

  const buildHierarchy = () => {
    const root = (name) => tree.querySelector(`[data-ref="${name}"]`)?.closest('.tree-group');
    const categoryRoot = root('categories'); const typeRoot = root('types'); const modelRoot = root('models');
    const categoryChildren = categoryRoot?.querySelector(':scope > .children');
    const typeChildren = typeRoot?.querySelector(':scope > .children');
    const modelChildren = modelRoot?.querySelector(':scope > .children');
    if (!categoryChildren || !typeChildren || !modelChildren) return;
    const categories = [...categoryChildren.querySelectorAll(':scope > [data-ref-item="category"]')];
    const types = [...typeChildren.querySelectorAll(':scope > [data-ref-item="type"]')];
    const models = [...modelChildren.querySelectorAll(':scope > .model-group')];
    const byCategory = new Map();
    types.forEach((node) => { const typeNode = node; const key = getTypeCategory(typeNode); if (!byCategory.has(key)) byCategory.set(key, []); byCategory.get(key).push(typeNode); });
    const byType = new Map();
    models.forEach((group) => { const key = String(group.querySelector(':scope > [data-model-row]')?.dataset.equipmentTypeId || ''); if (!byType.has(key)) byType.set(key, []); byType.get(key).push(group); });
    const add = (text, data) => { const button = document.createElement('button'); button.type = 'button'; button.className = 'tree-node master-inline-add'; button.textContent = text; Object.entries(data).forEach(([k, v]) => { button.dataset[k] = v; }); return button; };
    const appendType = (node, parent) => {
      const id = String(node.dataset.id || ''); const group = document.createElement('div'); group.className = 'tree-group master-type-group open'; group.dataset.typeId = id;
      node.innerHTML = `<span class="tree-toggle">⌄</span><span>🗂 ${node.dataset.name || node.textContent.trim()}</span><span class="tree-actions"><span class="tree-add" data-add="model" data-new-model-for-type="${id}" title="إضافة طراز">＋</span></span>`;
      const children = document.createElement('div'); children.className = 'children'; children.appendChild(add('＋ إضافة طراز', { newRef: 'model', newModelForType: id })); (byType.get(id) || []).forEach((model) => children.appendChild(model)); group.append(node, children); parent.appendChild(group);
    };
    categories.forEach((node) => {
      const id = String(node.dataset.id || ''); const group = document.createElement('div'); group.className = 'tree-group master-category-group open';
      node.innerHTML = `<span class="tree-toggle">⌄</span><span>📁 ${node.dataset.name || node.textContent.trim()}</span><span class="tree-actions"><span class="tree-add" data-add="type" data-new-type-for-category="${id}" title="إضافة نوع">＋</span></span>`;
      const children = document.createElement('div'); children.className = 'children'; children.appendChild(add('＋ إضافة نوع عتاد', { newRef: 'type', newTypeForCategory: id })); (byCategory.get(id) || []).forEach((type) => appendType(type, children)); group.append(node, children); node.replaceWith(group);
    });
    const orphan = document.createElement('div'); orphan.className = 'tree-group master-uncategorized open'; const orphanChildren = document.createElement('div'); orphanChildren.className = 'children'; orphan.append(add('🗂 أنواع عتاد غير مصنّفة', { ref: 'uncategorized' }), orphanChildren); orphanChildren.appendChild(add('＋ إضافة نوع عتاد', { newRef: 'type' })); (byCategory.get('') || []).forEach((type) => appendType(type, orphanChildren)); categoryChildren.appendChild(orphan);
    types.forEach((node) => node.remove()); models.forEach((group) => group.remove());
  };

  const revealAncestors = (node) => { let group = node.closest('.tree-group'); while (group) { group.classList.add('open'); group.querySelector(':scope > .tree-node')?.removeAttribute('hidden'); group = group.parentElement?.closest('.tree-group'); } };
  const search = $('treeSearch');
  search?.addEventListener('input', () => { const q = search.value.trim().toLocaleLowerCase(); const nodes = [...tree.querySelectorAll('.tree-node')]; nodes.forEach((node) => { node.hidden = !!q && !node.textContent.toLocaleLowerCase().includes(q); }); if (q) nodes.filter((node) => !node.hidden).forEach(revealAncestors); syncArrows(); });

  tree.addEventListener('contextmenu', (event) => { const node = event.target.closest('[data-model-row],[data-ref-item]'); if (!node) return; event.preventDefault(); showMenu(node, event.clientX, event.clientY); });
  let timer; let pressTarget; let sx; let sy;
  const cancelPress = () => { clearTimeout(timer); timer = null; pressTarget = null; };
  tree.addEventListener('pointerdown', (event) => { if (event.pointerType !== 'touch') return; const node = event.target.closest('[data-model-row],[data-ref-item]'); if (!node) return; cancelPress(); pressTarget = node; sx = event.clientX; sy = event.clientY; timer = setTimeout(() => { showMenu(pressTarget, sx, sy); cancelPress(); }, 650); });
  tree.addEventListener('pointermove', (event) => { if (timer && (Math.abs(event.clientX - sx) > 10 || Math.abs(event.clientY - sy) > 10)) cancelPress(); });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach((type) => tree.addEventListener(type, cancelPress));

  const exportTree = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      categories: [...tree.querySelectorAll('[data-ref-item="category"]')].map((node) => ({ id: node.dataset.id || '', name: node.dataset.name || '' })),
      types: [...tree.querySelectorAll('[data-ref-item="type"]')].map((node) => ({ id: node.dataset.id || '', name: node.dataset.name || '', category_id: node.dataset.categoryId || node.dataset.category || '' })),
      models: [...tree.querySelectorAll('[data-model-row]')].map((node) => ({ id: node.dataset.modelRow || '', name: node.textContent.trim().replace(/^🚙\s*/, ''), equipment_type_id: node.dataset.equipmentTypeId || '' }))
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = 'materiel-equipment-tree.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast('تم تصدير شجرة المعدات');
  };

  $('btn-export-tree')?.addEventListener('click', exportTree);
  $('btn-tree-expand-all')?.addEventListener('click', () => {
    tree.querySelectorAll('.tree-group').forEach((group) => group.classList.add('open'));
    syncArrows();
  });
  $('btn-tree-collapse-all')?.addEventListener('click', () => {
    tree.querySelectorAll('.tree-group').forEach((group) => group.classList.remove('open'));
    syncArrows();
  });
  $('btn-add-root-category')?.addEventListener('click', () => {
    if (typeof refPanel === 'function') refPanel('category');
  });

  let dragged = null;
  tree.addEventListener('dragstart', (event) => { const row = event.target.closest('[data-model-row]'); if (!row) return; dragged = row; row.classList.add('dragging'); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', row.dataset.modelRow); });
  tree.addEventListener('dragend', () => { dragged?.classList.remove('dragging'); dragged = null; });
  tree.addEventListener('dragover', (event) => { const target = event.target.closest('[data-type-id]'); if (dragged && target) { event.preventDefault(); target.classList.add('drop-target'); } });
  tree.addEventListener('dragleave', (event) => event.target.closest('[data-type-id]')?.classList.remove('drop-target'));
  const toast = (message) => { const box=document.getElementById('tree-toast'), msg=document.getElementById('toast-message'); if(!box||!msg)return; msg.textContent=message; box.hidden=false; box.classList.remove('hidden'); clearTimeout(window.__materielTreeToast); window.__materielTreeToast=setTimeout(()=>{box.hidden=true;box.classList.add('hidden');},2600); };
  tree.addEventListener('drop', async (event) => {
    const target = event.target.closest('[data-type-id]');
    if (!dragged || !target) return;
    event.preventDefault(); target.classList.remove('drop-target');
    const id = dragged.dataset.modelRow; const typeId = target.dataset.typeId;
    const model = DATA[String(id)] || DATA[id] || {};
    if (String(model.equipment_type_id) === String(typeId)) return;
    const form = new FormData(); form.append('equipment_type_id', typeId);
    try {
      const response = await fetch('/equipment-types/models/' + encodeURIComponent(id) + '/move', {method:'POST', body:form, credentials:'same-origin'});
      if (!response.ok) throw new Error('move failed');
      toast('تم نقل الطراز داخل الشجرة');
      window.setTimeout(() => window.location.reload(), 250);
    } catch (_) { toast('تعذر نقل الطراز؛ لم يتم تغيير البيانات'); }
  });

  tree.addEventListener('click', (event) => {
    const action = event.target.closest('[data-add],[data-new-ref]');
    if (action) { event.preventDefault(); event.stopPropagation(); const kind = action.dataset.add || action.dataset.newRef; if (kind === 'type' && action.dataset.newTypeForCategory) openTypeCreate(action.dataset.newTypeForCategory); else if (kind === 'model') openModelCreate(action.dataset.newModelForType); else if (typeof refPanel === 'function') refPanel(kind); return; }
    const position = event.target.closest('[data-tree-add]');
    if (position) { event.preventDefault(); event.stopPropagation(); const model = event.target.closest('[data-model]'); if (model && typeof editModel === 'function') { editModel(model.dataset.model, position.dataset.treeAdd === 'position' ? 'positions' : 'sizes'); position.dataset.treeAdd === 'position' ? window.addPos?.() : window.addSize?.(); } return; }
    const toggle = event.target.closest('.tree-toggle');
    if (toggle) { event.preventDefault(); event.stopPropagation(); toggle.closest('.tree-group')?.classList.toggle('open'); syncArrows(); return; }
    const row = event.target.closest('[data-model-row]'); if (row) { selectNode(row); window.viewModel?.(row.dataset.modelRow); return; }
    const model = event.target.closest('[data-model]'); if (model) { selectNode(model); window.viewModel?.(model.dataset.model); selectSection(sectionMap[model.dataset.section || 'basic'] || 0, { focus: true }); return; }
    const ref = event.target.closest('[data-ref-item]'); if (ref) { editReference(ref); return; }
    const node = event.target.closest('.tree-node'); if (node) selectNode(node);
  }, true);

  const style = document.createElement('style'); style.textContent = `.master-context-menu{position:fixed;z-index:99999;min-width:190px;padding:5px;background:#fff;border:1px solid #dbe3ec;border-radius:10px;box-shadow:0 10px 30px rgba(15,23,42,.16);direction:rtl}.master-context-menu button{display:block;width:100%;border:0;background:transparent;text-align:right;padding:10px 11px;border-radius:7px;font:inherit;font-weight:700;color:#26384a;cursor:pointer}.master-context-menu button:hover{background:#edf4fa;color:#173b63}.tree-node[draggable=true]{cursor:grab}.tree-node.dragging{opacity:.45}.tree-group.drop-target>.tree-node{outline:2px dashed #1976d2;background:#edf6ff}@media(max-width:900px){.mdx .layout{grid-template-columns:1fr}.mdx{padding:10px}}@media(max-width:640px){.mdx .tree-node{min-height:42px;padding:10px 12px;font-size:14px}.master-context-menu{max-width:calc(100vw - 16px)}}`; document.head.appendChild(style);
  buildHierarchy();
  tree.querySelectorAll('[data-model-row]').forEach((row) => { row.draggable = true; });
  syncArrows(); selectSection(0);
})();
