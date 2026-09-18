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

  $('btn-tree-expand-all')?.addEventListener('click', () => { tree.querySelectorAll('.tree-group').forEach((group) => group.classList.add('open')); syncArrows(); });
  $('btn-tree-collapse-all')?.addEventListener('click', () => { tree.querySelectorAll('.tree-group').forEach((group) => group.classList.remove('open')); syncArrows(); });
  $('btn-add-root-category')?.addEventListener('click', () => { if (typeof refPanel === 'function') refPanel('category'); });
  buildHierarchy();
  tree.querySelectorAll('[data-model-row]').forEach((row) => { row.draggable = true; });
  syncArrows();
  selectSection(0);
})();
