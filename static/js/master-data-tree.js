(() => {
  'use strict';
  const tree = document.getElementById('tree');
  if (!tree || typeof DATA === 'undefined') return;

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
    boxes.forEach((box, boxIndex) => {
      box.hidden = boxIndex !== safe;
      box.setAttribute('aria-hidden', boxIndex === safe ? 'false' : 'true');
    });
    tabs.forEach((tab, tabIndex) => {
      const active = tabIndex === safe;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
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
    const option = select && typeId ? [...select.options].find((item) => String(item.value) === String(typeId)) : null;
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
    form.method = 'post';
    form.action = url;
    form.hidden = true;
    document.body.appendChild(form);
    form.submit();
  };

  const menu = document.createElement('div');
  menu.className = 'master-context-menu';
  menu.hidden = true;
  menu.dir = 'rtl';
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
      const id = ref.dataset.id;
      const kind = ref.dataset.refItem;
      const labels = { category: 'الفئة', type: 'نوع العتاد', brand: 'العلامة التجارية', spec: 'الخاصية' };
      if (!id || !labels[kind]) return;
      actions.push([`✏️ تعديل ${labels[kind]}`, () => editReference(ref)]);
      const routes = { category: `/equipment-types/categories/${id}/delete`, type: `/equipment-types/${id}/delete`, brand: `/equipment-types/brands/${id}/delete` };
      if (routes[kind]) actions.push([`🗑 حذف ${labels[kind]}`, () => postDelete(routes[kind], `حذف ${labels[kind]}؟`)]);
    } else return;
    menu.replaceChildren();
    actions.forEach(([label, action]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.onclick = () => { closeMenu(); action(); };
      menu.appendChild(button);
    });
    menu.hidden = false;
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(x, innerWidth - rect.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, innerHeight - rect.height - 8))}px`;
  };

  const root = (name) => tree.querySelector(`[data-ref="${name}"]`)?.closest('.tree-group');
  const makeInlineAction = (label, attributes) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tree-node master-inline-add';
    button.textContent = label;
    Object.entries(attributes).forEach(([key, value]) => { button.dataset[key] = String(value); });
    return button;
  };
  const buildHierarchy = () => {
    const categoryRoot = root('categories');
    const typeRoot = root('types');
    const modelRoot = root('models');
    const categoryChildren = categoryRoot?.querySelector(':scope > .children');
    const typeChildren = typeRoot?.querySelector(':scope > .children');
    const modelChildren = modelRoot?.querySelector(':scope > .children');
    if (!categoryChildren || !typeChildren || !modelChildren) return;
    if (tree.dataset.hierarchyBuilt === '1') return;

    const categories = [...categoryChildren.querySelectorAll(':scope > [data-ref-item="category"]')];
    const types = [...typeChildren.querySelectorAll(':scope > [data-ref-item="type"]')];
    const models = [...modelChildren.querySelectorAll(':scope > .model-group')];
    const byCategory = new Map();
    const byType = new Map();
    const categoryOf = (node) => String(node.dataset.categoryId || node.dataset.category || '');
    types.forEach((node) => {
      const key = categoryOf(node);
      if (!byCategory.has(key)) byCategory.set(key, []);
      byCategory.get(key).push(node);
    });
    models.forEach((group) => {
      const key = String(group.querySelector(':scope > [data-model-row]')?.dataset.equipmentTypeId || '');
      if (!byType.has(key)) byType.set(key, []);
      byType.get(key).push(group);
    });

    const appendType = (node, parent) => {
      const id = String(node.dataset.id || '');
      const group = document.createElement('div');
      group.className = 'tree-group master-type-group open';
      group.dataset.typeId = id;
      node.innerHTML = `<span class="tree-toggle">⌄</span><span>🗂 ${node.dataset.name || ''}</span><span class="tree-actions"><span class="tree-add" data-add="model">＋</span></span>`;
      const children = document.createElement('div');
      children.className = 'children';
      children.appendChild(makeInlineAction('＋ إضافة طراز', { newRef: 'model', newModelForType: id }));
      children.append(...(byType.get(id) || []));
      group.append(node, children);
      parent.appendChild(group);
    };

    categories.forEach((node) => {
      const id = String(node.dataset.id || '');
      const group = document.createElement('div');
      group.className = 'tree-group master-category-group open';
      node.innerHTML = `<span class="tree-toggle">⌄</span><span>📁 ${node.dataset.name || ''}</span><span class="tree-actions"><span class="tree-add" data-add="type">＋</span></span>`;
      const children = document.createElement('div');
      children.className = 'children';
      children.appendChild(makeInlineAction('＋ إضافة نوع عتاد', { newRef: 'type', newTypeForCategory: id }));
      (byCategory.get(id) || []).forEach((type) => appendType(type, children));
      group.append(node, children);
      categoryChildren.appendChild(group);
    });

    const orphanTypes = byCategory.get('') || [];
    if (orphanTypes.length) {
      const group = document.createElement('div');
      group.className = 'tree-group master-uncategorized open';
      const heading = document.createElement('button');
      heading.type = 'button';
      heading.className = 'tree-node';
      heading.innerHTML = '<span class="tree-toggle">⌄</span>🗂 أنواع عتاد غير مصنّفة';
      const children = document.createElement('div');
      children.className = 'children';
      orphanTypes.forEach((type) => appendType(type, children));
      group.append(heading, children);
      categoryChildren.appendChild(group);
    }
    tree.dataset.hierarchyBuilt = '1';
    syncArrows();
  };

  const revealAncestors = (node) => {
    let group = node.closest('.tree-group');
    while (group) {
      group.classList.add('open');
      const parentNode = group.querySelector(':scope > .tree-node');
      if (parentNode) parentNode.hidden = false;
      group = group.parentElement?.closest('.tree-group');
    }
  };
  const searchInput = $('treeSearch');
  searchInput?.addEventListener('input', () => {
    const query = searchInput.value.trim().toLocaleLowerCase();
    tree.querySelectorAll('.tree-node').forEach((node) => {
      node.hidden = !!query && !node.textContent.toLocaleLowerCase().includes(query);
      if (!node.hidden) revealAncestors(node);
    });
    syncArrows();
  });

  tree.addEventListener('contextmenu', (event) => {
    const node = event.target.closest('[data-model-row],[data-ref-item]');
    if (!node) return;
    event.preventDefault();
    showMenu(node, event.clientX, event.clientY);
  });

  let timer; let pressTarget; let sx; let sy;
  const cancelPress = () => { clearTimeout(timer); timer = null; pressTarget = null; };
  tree.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'touch') return;
    const node = event.target.closest('[data-model-row],[data-ref-item]');
    if (!node) return;
    cancelPress();
    pressTarget = node;
    sx = event.clientX; sy = event.clientY;
    timer = setTimeout(() => {
      if (!pressTarget) return;
      showMenu(pressTarget, event.clientX, event.clientY);
    }, 500);
  });
  tree.addEventListener('pointermove', (event) => {
    if (timer && (Math.abs(event.clientX - sx) > 10 || Math.abs(event.clientY - sy) > 10)) cancelPress();
  });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach((type) => tree.addEventListener(type, cancelPress));

  let dragged = null;
  tree.addEventListener('dragstart', (event) => {
    const row = event.target.closest('[data-model-row]');
    if (!row) return;
    dragged = row;
    row.classList.add('dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(row.dataset.modelRow));
  });
  tree.addEventListener('dragend', () => {
    dragged?.classList.remove('dragging');
    dragged = null;
  });
  tree.addEventListener('dragover', (event) => {
    const target = event.target.closest('[data-type-id]');
    if (dragged && target) {
      event.preventDefault();
      target.classList.add('drop-target');
    }
  });
  tree.addEventListener('dragleave', (event) => event.target.closest('[data-type-id]')?.classList.remove('drop-target'));

  const toast = (message, action) => {
    const box = document.getElementById('tree-toast');
    const msg = document.getElementById('toast-message');
    if (!box || !msg) return;
    msg.textContent = message;
    let undo = box.querySelector('[data-tree-toast-action]');
    if (!undo) {
      undo = document.createElement('button');
      undo.type = 'button';
      undo.dataset.treeToastAction = '1';
      undo.className = 'tree-toast-action';
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
    box.classList.remove('hidden');
    clearTimeout(window.__materielTreeToast);
    window.__materielTreeToast = setTimeout(() => {
      box.hidden = true;
      box.classList.add('hidden');
      undo.hidden = true;
    }, 5000);
  };

  tree.addEventListener('drop', async (event) => {
    const target = event.target.closest('[data-type-id]');
    if (!dragged || !target) return;
    event.preventDefault();
    target.classList.remove('drop-target');
    const id = dragged.dataset.modelRow;
    const typeId = target.dataset.typeId;
    const model = DATA[String(id)] || DATA[id] || {};
    if (String(model.equipment_type_id) === String(typeId)) return;
    const form = new FormData();
    form.append('equipment_type_id', typeId);
    try {
      const response = await fetch('/equipment-types/models/' + encodeURIComponent(id) + '/move', { method: 'POST', body: form, credentials: 'same-origin' });
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
      toast('تم نقل الطراز داخل الشجرة', undoMove);
      window.setTimeout(() => { if (!undone) window.location.reload(); }, 5200);
    } catch (_) {
      toast('تعذر نقل الطراز؛ لم يتم تغيير البيانات');
    }
  });

  const exportTree = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      categories: [...tree.querySelectorAll('[data-ref-item="category"]')].map((node) => ({ id: node.dataset.id || '', name: node.dataset.name || '' })),
      types: [...tree.querySelectorAll('[data-ref-item="type"]')].map((node) => ({ id: node.dataset.id || '', name: node.dataset.name || '', category_id: node.dataset.categoryId || node.dataset.category || '' })),
      models: [...tree.querySelectorAll('[data-model-row]')].map((node) => ({ id: node.dataset.modelRow || '', name: node.textContent.trim().replace(/^🚙\s*/, ''), equipment_type_id: node.dataset.equipmentTypeId || '' })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'materiel-equipment-tree.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast('تم تصدير شجرة المعدات');
  };

  $('btn-export-tree')?.addEventListener('click', exportTree);
  $('btn-tree-expand-all')?.addEventListener('click', () => { tree.querySelectorAll('.tree-group').forEach((group) => group.classList.add('open')); syncArrows(); });
  $('btn-tree-collapse-all')?.addEventListener('click', () => { tree.querySelectorAll('.tree-group').forEach((group) => group.classList.remove('open')); syncArrows(); });
  $('btn-add-root-category')?.addEventListener('click', () => { if (typeof refPanel === 'function') refPanel('category'); });

  tree.addEventListener('click', (event) => {
    const action = event.target.closest('[data-add],[data-new-ref],[data-new-type-for-category],[data-new-model-for-type]');
    if (action) {
      event.preventDefault();
      event.stopPropagation();
      const kind = action.dataset.add || action.dataset.newRef;
      if (action.dataset.newTypeForCategory) openTypeCreate(action.dataset.newTypeForCategory);
      else if (action.dataset.newModelForType) openModelCreate(action.dataset.newModelForType);
      else if (kind === 'model') openModelCreate();
      else if (kind && typeof refPanel === 'function') refPanel(kind);
      return;
    }
    const position = event.target.closest('[data-tree-add]');
    if (position) {
      event.preventDefault();
      event.stopPropagation();
      const model = event.target.closest('[data-model]');
      if (model && typeof editModel === 'function') editModel(model.dataset.model, position.dataset.treeAdd === 'size' ? 'sizes' : 'positions');
      return;
    }
    const copy = event.target.closest('[data-copy]');
    if (copy) { event.preventDefault(); event.stopPropagation(); copyModel(copy.dataset.copy); return; }
    const del = event.target.closest('[data-delete]');
    if (del) {
      event.preventDefault();
      event.stopPropagation();
      if (confirm('حذف الطراز؟')) {
        const form = document.createElement('form');
        form.method = 'post';
        form.action = `/equipment-types/models/${encodeURIComponent(del.dataset.delete)}/delete`;
        document.body.appendChild(form);
        form.submit();
      }
      return;
    }
    const toggle = event.target.closest('.tree-toggle');
    if (toggle) {
      event.preventDefault();
      event.stopPropagation();
      toggle.closest('.tree-group')?.classList.toggle('open');
      syncArrows();
      return;
    }
    const row = event.target.closest('[data-model-row]');
    if (row) { selectNode(row); window.viewModel?.(row.dataset.modelRow); selectSection(0); return; }
    const model = event.target.closest('[data-model]');
    if (model) {
      selectNode(model);
      window.viewModel?.(model.dataset.model);
      selectSection(sectionMap[model.dataset.section || 'basic'] || 0, { focus: true });
      return;
    }
    const item = event.target.closest('[data-ref-item]');
    if (item) { editReference(item); return; }
    const node = event.target.closest('.tree-node');
    if (node) selectNode(node);
  }, true);

  buildHierarchy();
  tree.querySelectorAll('[data-model-row]').forEach((row) => { row.draggable = true; });
  syncArrows();
  selectSection(0);
})();
