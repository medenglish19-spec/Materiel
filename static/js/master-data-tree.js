(() => {
  'use strict';

  const tree = document.getElementById('tree');
  if (!tree) return;

  const sectionMap = {basic: 0, tires: 1, positions: 1, sizes: 1, batteries: 2, specs: 3};

  const syncArrows = () => {
    tree.querySelectorAll('.tree-group > .tree-node > .tree-toggle').forEach((toggle) => {
      const group = toggle.closest('.tree-group');
      toggle.textContent = group?.classList.contains('open') ? '⌄' : '›';
    });
  };

  const selectSection = (index, options = {}) => {
    const sections = Array.from(document.querySelectorAll('#modelPanel [data-workspace-section]'));
    const tabs = Array.from(document.querySelectorAll('[data-model-workspace-tab]'));
    if (!sections.length) return;
    const safeIndex = Math.min(Math.max(Number(index) || 0, 0), sections.length - 1);
    sections.forEach((box, boxIndex) => {
      const active = boxIndex === safeIndex;
      box.hidden = !active;
      box.setAttribute('aria-hidden', active ? 'false' : 'true');
    });
    tabs.forEach((tab, tabIndex) => {
      const active = tabIndex === safeIndex;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    if (options.focus) {
      const target = sections[safeIndex];
      if (target) target.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    }
  };

  window.MATERIEL_MODEL_WORKSPACE_SELECT = selectSection;

  const openTypeCreate = (categoryId) => {
    if (typeof resetModel === 'function') resetModel();
    if (typeof refPanel === 'function') refPanel('type', null, '', {categoryId: String(categoryId || '')});
    const form = document.querySelector('#refBody form');
    const categoryInput = form?.querySelector('[name="category_id"]');
    if (categoryInput && categoryId !== undefined && categoryId !== null && categoryId !== '') {
      categoryInput.value = String(categoryId);
    }
  };

  const openModelCreate = (typeId) => {
    if (typeof resetModel === 'function') resetModel();
    const typeSelect = document.getElementById('modelType');
    const categorySelect = document.getElementById('modelCategory');
    if (typeId !== undefined && typeId !== null && typeId !== '') {
      const option = typeSelect?.querySelector(`option[value="${CSS.escape(String(typeId))}"]`);
      if (option && typeSelect) {
        typeSelect.value = String(typeId);
        if (categorySelect && option.dataset.category) categorySelect.value = option.dataset.category;
      }
    }
    if (typeof title === 'function') title('إضافة طراز', 'الطرازات');
    if (typeof show === 'function') show(document.getElementById('modelPanel'));
    window.MATERIEL_MODEL_WORKSPACE_SELECT?.(0);
  };

  const buildHierarchy = () => {
    const categoryRoot = tree.querySelector('[data-ref="categories"]')?.closest('.tree-group');
    const typeRoot = tree.querySelector('[data-ref="types"]')?.closest('.tree-group');
    const modelRoot = tree.querySelector('[data-ref="models"]')?.closest('.tree-group');
    if (!categoryRoot || !typeRoot || !modelRoot) return;

    const categoryChildren = categoryRoot.querySelector(':scope > .children');
    const typeChildren = typeRoot.querySelector(':scope > .children');
    const modelChildren = modelRoot.querySelector(':scope > .children');
    if (!categoryChildren || !typeChildren || !modelChildren) return;

    const categoryNodes = Array.from(categoryChildren.querySelectorAll(':scope > [data-ref-item="category"]'));
    const typeNodes = Array.from(typeChildren.querySelectorAll(':scope > [data-ref-item="type"]'));
    const modelGroups = Array.from(modelChildren.querySelectorAll(':scope > .model-group'));

    const typeByCategory = new Map();
    typeNodes.forEach((node) => {
      const key = String(node.dataset.categoryId || '');
      if (!typeByCategory.has(key)) typeByCategory.set(key, []);
      typeByCategory.get(key).push(node);
    });

    const modelsByType = new Map();
    modelGroups.forEach((group) => {
      const row = group.querySelector(':scope > [data-model-row]');
      const key = String(row?.dataset.equipmentTypeId || '');
      if (!modelsByType.has(key)) modelsByType.set(key, []);
      modelsByType.get(key).push(group);
    });

    const addButton = (label, attrs) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tree-node master-inline-add';
      button.textContent = label;
      Object.entries(attrs).forEach(([key, value]) => button.dataset[key] = String(value));
      return button;
    };

    categoryNodes.forEach((categoryNode) => {
      const categoryId = String(categoryNode.dataset.id || '');
      const categoryGroup = document.createElement('div');
      categoryGroup.className = 'tree-group master-category-group open';
      categoryGroup.dataset.categoryId = categoryId;

      const categoryButton = categoryNode;
      categoryButton.classList.add('master-category-node');
      categoryButton.innerHTML = '<span class="tree-toggle">⌄</span><span>📁 ' +
        (categoryButton.dataset.name || categoryButton.textContent.replace(/^•\s*/, '').trim()) +
        '</span><span class="tree-actions"></span>';
      const actions = categoryButton.querySelector('.tree-actions');
      const addType = document.createElement('span');
      addType.className = 'tree-add';
      addType.textContent = '＋';
      addType.dataset.add = 'type';
      addType.dataset.newTypeForCategory = categoryId;
      addType.title = 'إضافة نوع عتاد داخل هذه الفئة';
      actions.appendChild(addType);

      const children = document.createElement('div');
      children.className = 'children';
      children.appendChild(addButton('＋ إضافة نوع عتاد', {newRef: 'type', newTypeForCategory: categoryId}));

      (typeByCategory.get(categoryId) || []).forEach((typeNode) => {
        appendType(typeNode, children, modelsByType);
      });

      categoryGroup.append(categoryButton, children);
      categoryNode.replaceWith(categoryGroup);
    });

    const uncategorizedTypes = typeByCategory.get('');
    const uncategorizedGroup = document.createElement('div');
    uncategorizedGroup.className = 'tree-group master-uncategorized open';
    const uncategorizedButton = document.createElement('button');
    uncategorizedButton.type = 'button';
    uncategorizedButton.className = 'tree-node';
    uncategorizedButton.innerHTML = '<span class="tree-toggle">⌄</span>🗂 أنواع عتاد غير مصنّفة';
    const uncategorizedChildren = document.createElement('div');
    uncategorizedChildren.className = 'children';
    const addType = addButton('＋ إضافة نوع عتاد', {newRef: 'type'});
    addType.classList.add('master-inline-add-type');
    uncategorizedChildren.appendChild(addType);
    let hasUncategorized = false;
    (uncategorizedTypes || []).forEach((typeNode) => {
      hasUncategorized = true;
      appendType(typeNode, uncategorizedChildren, modelsByType);
    });
    if (hasUncategorized || addType) categoryChildren.appendChild(uncategorizedGroup);

    typeNodes.forEach((node) => node.remove());
    modelGroups.forEach((group) => group.remove());

    function appendType(typeNode, parent, modelMap) {
      const typeId = String(typeNode.dataset.id || '');
      const typeGroup = document.createElement('div');
      typeGroup.className = 'tree-group master-type-group open';
      typeGroup.dataset.typeId = typeId;
      typeNode.classList.add('master-type-node');
      typeNode.innerHTML = '<span class="tree-toggle">⌄</span><span>🗂 ' +
        (typeNode.dataset.name || typeNode.textContent.replace(/^•\s*/, '').trim()) +
        '</span><span class="tree-actions"></span>';
      const actions = typeNode.querySelector('.tree-actions');
      const addModel = document.createElement('span');
      addModel.className = 'tree-add';
      addModel.textContent = '＋';
      addModel.dataset.add = 'model';
      addModel.dataset.newModelForType = typeId;
      addModel.title = 'إضافة طراز داخل هذا النوع';
      actions.appendChild(addModel);

      const children = document.createElement('div');
      children.className = 'children';
      children.appendChild(addButton('＋ إضافة طراز', {newRef: 'model', newModelForType: typeId}));
      (modelMap.get(typeId) || []).forEach((group) => {
        children.appendChild(group);
      });
      typeGroup.append(typeNode, children);
      parent.appendChild(typeGroup);
    }
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

  const setupSearch = () => {
    const searchInput = document.getElementById('treeSearch');
    if (!searchInput) return;
    searchInput.addEventListener('input', () => {
      const query = searchInput.value.trim().toLocaleLowerCase();
      const nodes = Array.from(tree.querySelectorAll('.tree-node'));
      nodes.forEach((node) => {
        node.hidden = query ? !node.textContent.toLocaleLowerCase().includes(query) : false;
      });
      if (query) nodes.filter((node) => !node.hidden).forEach((node) => revealAncestors(node));
      syncArrows();
    });
  };

  const selectNode = (node) => {
    tree.querySelectorAll('.tree-node.active').forEach((item) => item.classList.remove('active'));
    node?.classList.add('active');
  };

  const editReference = (node) => {
    const kind = node.dataset.refItem;
    const id = node.dataset.id;
    if (!kind || !id || typeof refPanel !== 'function') return;
    refPanel(kind, id, node.dataset.name || '', node.dataset);
    selectNode(node);
  };

  const copyModel = (id) => {
    if (typeof editModel !== 'function') return;
    editModel(id);
    const name = document.getElementById('modelName');
    const modelId = document.getElementById('modelId');
    const form = document.getElementById('modelForm');
    if (name) name.value = `${name.value} - نسخة`;
    if (modelId) modelId.value = '';
    if (form) form.action = '/equipment-types/models/create';
    currentModel = null;
  };

  const postDelete = (action, message) => {
    if (!window.confirm(message)) return;
    const form = document.createElement('form');
    form.method = 'post';
    form.action = action;
    form.hidden = true;
    document.body.appendChild(form);
    form.submit();
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
      actions.push(['🗑 حذف الطراز', () => postDelete('/equipment-types/models/' + encodeURIComponent(id) + '/delete', 'حذف الطراز؟ سيتم تطبيق حماية النظام الحالية.')]);
    } else if (ref) {
      const kind = ref.dataset.refItem;
      const id = ref.dataset.id;
      const labels = {category:'الفئة', type:'نوع العتاد', brand:'العلامة التجارية', spec:'الخاصية'};
      if (!labels[kind] || !id) return;
      actions.push(['✏️ تعديل ' + labels[kind], () => editReference(ref)]);
      if (kind === 'category') actions.push(['🗑 حذف الفئة', () => postDelete('/equipment-types/categories/' + encodeURIComponent(id) + '/delete', 'حذف الفئة؟ إذا كانت مرتبطة بأنواع عتاد سيمنع النظام الحذف.')]);
      if (kind === 'type') actions.push(['🗑 حذف نوع العتاد', () => postDelete('/equipment-types/' + encodeURIComponent(id) + '/delete', 'حذف نوع العتاد؟ إذا كان مرتبطاً بطرازات سيمنع النظام الحذف.')]);
      if (kind === 'brand') actions.push(['🗑 حذف العلامة التجارية', () => postDelete('/equipment-types/brands/' + encodeURIComponent(id) + '/delete', 'حذف العلامة التجارية؟ إذا كانت مرتبطة بطرازات سيمنع النظام الحذف.')]);
    } else {
      return;
    }

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

  const menu = document.createElement('div');
  menu.className = 'master-context-menu';
  menu.hidden = true;
  menu.dir = 'rtl';
  document.body.appendChild(menu);

  const closeMenu = () => {
    menu.hidden = true;
    menu.replaceChildren();
  };

  tree.addEventListener('contextmenu', (event) => {
    const node = event.target.closest('[data-model-row],[data-ref-item],[data-model],[data-item]');
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
    const node = event.target.closest('[data-model-row],[data-ref-item],[data-model],[data-item]');
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
  ['pointerup', 'pointercancel', 'pointerleave'].forEach((type) => tree.addEventListener(type, cancelLongPress));

  document.addEventListener('pointerdown', (event) => {
    if (!menu.hidden && !menu.contains(event.target)) closeMenu();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });

  const style = document.createElement('style');
  style.textContent = `
    .master-context-menu{position:fixed;z-index:99999;min-width:190px;padding:5px;background:#fff;border:1px solid #dbe3ec;border-radius:10px;box-shadow:0 10px 30px rgba(15,23,42,.16);direction:rtl}
    .master-context-menu button{display:block;width:100%;border:0;background:transparent;text-align:right;padding:10px 11px;border-radius:7px;font:inherit;font-size:13px;font-weight:700;color:#26384a;cursor:pointer;min-height:40px}
    .master-context-menu button:hover{background:#edf4fa;color:#173b63}
    .mdx .layout{display:grid;grid-template-columns:minmax(300px,390px) minmax(0,1fr);gap:16px;align-items:start}
    .mdx .tree-card{min-width:0;overflow:hidden}
    .mdx .tree-node{min-height:42px;display:flex;align-items:center;gap:8px}
    .mdx .tree-add,.mdx .tree-toggle{min-width:32px;min-height:32px;display:inline-flex;align-items:center;justify-content:center}
    .mdx .master-inline-add{font-size:12px;color:#315f88}
    @media(max-width:900px){.mdx .layout{grid-template-columns:1fr}.mdx{padding:10px}.mdx .tree-card{width:100%}}
    @media(max-width:640px){.mdx-head h1{font-size:24px}.mdx .tree-node{padding:10px 12px;font-size:14px}.mdx .editor{padding:0}.master-context-menu{max-width:min(300px,calc(100vw - 16px));min-width:170px}}
  `;
  document.head.appendChild(style);

  buildHierarchy();
  setupSearch();
  syncArrows();

  tree.addEventListener('click', (event) => {
    const add = event.target.closest('[data-add],[data-new-ref]');
    if (add) {
      event.preventDefault();
      event.stopPropagation();
      const kind = add.dataset.add || add.dataset.newRef;
      if (kind === 'model') {
        openModelCreate(add.dataset.newModelForType || '');
      } else if (kind === 'type' && add.dataset.newTypeForCategory) {
        openTypeCreate(add.dataset.newTypeForCategory);
      } else if (kind) {
        if (typeof refPanel === 'function') refPanel(kind);
      }
      syncArrows();
      return;
    }

    const treeAdd = event.target.closest('[data-tree-add]');
    if (treeAdd) {
      event.preventDefault();
      event.stopPropagation();
      const modelNode = event.target.closest('[data-model]');
      if (!modelNode) return;
      editModel(modelNode.dataset.model, treeAdd.dataset.treeAdd === 'position' ? 'positions' : 'sizes');
      treeAdd.dataset.treeAdd === 'position' ? addPos() : addSize();
      return;
    }

    const toggle = event.target.closest('.tree-toggle');
    if (toggle) {
      event.preventDefault();
      event.stopPropagation();
      const group = toggle.closest('.tree-group');
      if (group) group.classList.toggle('open');
      syncArrows();
      return;
    }

    const modelRow = event.target.closest('[data-model-row]');
    if (modelRow) {
      event.preventDefault();
      event.stopPropagation();
      selectNode(modelRow);
      const group = modelRow.closest('.tree-group');
      if (group) group.classList.add('open');
      viewModel(modelRow.dataset.modelRow);
      return;
    }

    const model = event.target.closest('[data-model]');
    if (model) {
      event.preventDefault();
      event.stopPropagation();
      selectNode(model);
      const section = model.dataset.section || 'basic';
      viewModel(model.dataset.model);
      const sectionIndex = sectionMap[section] ?? 0;
      window.MATERIEL_MODEL_WORKSPACE_SELECT?.(sectionIndex, {focus:true});
      return;
    }

    const item = event.target.closest('[data-ref-item]');
    if (item) {
      event.preventDefault();
      event.stopPropagation();
      editReference(item);
      return;
    }

    const node = event.target.closest('.tree-node');
    if (node) {
      event.preventDefault();
      event.stopPropagation();
      selectNode(node);
    }
  });

  if (typeof setupModelWorkspace === 'function') setupModelWorkspace();
  window.MATERIEL_MODEL_WORKSPACE_SELECT?.(0);
})();
