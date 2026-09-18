(() => {
  'use strict';

  const tree = document.getElementById('tree');
  if (!tree) return;

  const style = document.createElement('style');
  style.textContent = `
    #tree .master-hierarchy-group{margin-bottom:3px}
    #tree .master-hierarchy-group>.children{padding-right:20px}
    #tree .master-category-types-label,#tree .master-type-models-label{font-weight:800;color:#475569}
    #tree .master-category-types-section>.children,#tree .master-type-models-section>.children{display:block}
    #tree .master-uncategorized{margin-top:8px;padding-top:6px;border-top:1px dashed #cbd5e1}
    #tree .master-unassigned-models{margin-top:8px;padding-top:6px;border-top:1px dashed #cbd5e1}
    #tree .master-inline-add{margin:4px 0 4px}
    #tree .master-inline-add-type{margin:4px 0 6px;font-size:12px}
    .master-context-menu{position:fixed;z-index:99999;min-width:180px;padding:5px;background:#fff;border:1px solid #dbe3ec;border-radius:10px;box-shadow:0 10px 30px rgba(15,23,42,.16);direction:rtl}
    .master-context-menu button{display:block;width:100%;border:0;background:transparent;text-align:right;padding:9px 11px;border-radius:7px;font:inherit;font-size:13px;font-weight:700;color:#26384e;cursor:pointer}
    .master-context-menu button:hover{background:#edf4fa;color:#173b63}
  `;
  document.head.appendChild(style);

  const textById = (selector) => {
    const map = new Map();
    tree.querySelectorAll(selector).forEach((node) => {
      if (node.dataset.id) map.set(String(node.dataset.id), node.dataset.name || node.textContent.trim());
    });
    return map;
  };

  const categories = textById('[data-ref-item="category"]');
  const types = textById('[data-ref-item="type"]');
  const typeCategoryMap = new Map();
  document.querySelectorAll('#modelType option[data-category]').forEach((option) => {
    if (option.value) typeCategoryMap.set(String(option.value), String(option.dataset.category || ''));
  });

  const findTypeNode = (id) => tree.querySelector(`[data-ref-item="type"][data-id="${CSS.escape(String(id))}"]`);
  const findCategoryNode = (id) => tree.querySelector(`[data-ref-item="category"][data-id="${CSS.escape(String(id))}"]`);

  const buildRealHierarchy = () => {
    const categoryRoot = tree.querySelector('[data-ref="categories"]')?.closest('.tree-group');
    const typeRoot = tree.querySelector('[data-ref="types"]')?.closest('.tree-group');
    const modelRoot = tree.querySelector('[data-ref="models"]')?.closest('.tree-group');
    if (!categoryRoot || !typeRoot || !modelRoot || typeof DATA === 'undefined') return;

    const categoryChildren = categoryRoot.querySelector(':scope > .children');
    const typeChildren = typeRoot.querySelector(':scope > .children');
    const modelChildren = modelRoot.querySelector(':scope > .children');
    if (!categoryChildren || !typeChildren || !modelChildren) return;
    if (categoryRoot.dataset.hierarchyBuilt === '1') return;

    // Preserve the original controls. They are moved into explicit fallback groups
    // instead of being removed and recreated.
    const addType = typeChildren.querySelector('[data-new-ref="type"]');
    const addModel = modelChildren.querySelector('[data-new-ref="model"]');

    const categoryItems = Array.from(categoryChildren.querySelectorAll(':scope > [data-ref-item="category"]'));
    categoryItems.forEach((categoryNode) => {
      const categoryGroup = document.createElement('div');
      categoryGroup.className = 'tree-group master-hierarchy-group open';
      const categoryId = String(categoryNode.dataset.id || '');
      const categoryNested = document.createElement('div');
      categoryNested.className = 'children';
      categoryGroup.appendChild(categoryNode);
      categoryGroup.appendChild(categoryNested);
      categoryChildren.appendChild(categoryGroup);

      const typeSection = document.createElement('div');
      typeSection.className = 'master-category-types-section';
      const typeLabel = document.createElement('div');
      typeLabel.className = 'tree-node master-category-types-label';
      typeLabel.textContent = '🗂 أنواع العتاد';
      const typeList = document.createElement('div');
      typeList.className = 'children';
      const addTypeForCategory = document.createElement('button');
      addTypeForCategory.type = 'button';
      addTypeForCategory.className = 'tree-node master-inline-add-type';
      addTypeForCategory.dataset.newTypeForCategory = categoryId;
      addTypeForCategory.textContent = '＋ إضافة نوع عتاد';
      typeSection.append(typeLabel, typeList, addTypeForCategory);
      categoryNested.appendChild(typeSection);
    });

    const uncategorizedGroup = document.createElement('div');
    uncategorizedGroup.className = 'tree-group master-uncategorized open';
    const uncategorizedNode = document.createElement('button');
    uncategorizedNode.className = 'tree-node';
    uncategorizedNode.type = 'button';
    uncategorizedNode.innerHTML = '<span class="tree-toggle">⌄</span>🗂 أنواع عتاد غير مصنّفة';
    const uncategorizedChildren = document.createElement('div');
    uncategorizedChildren.className = 'children';
    uncategorizedGroup.append(uncategorizedNode, uncategorizedChildren);

    const typeGroupsById = new Map();
    let hasUncategorized = false;
    const typeNodes = Array.from(typeChildren.querySelectorAll(':scope > [data-ref-item="type"]'));

    const getTypeCategoryId = (typeNode) => {
      const id = String(typeNode.dataset.id || '');
      const attr = String(typeNode.dataset.categoryId || typeNode.dataset.category || '');
      return attr || typeCategoryMap.get(id) || '';
    };

    typeNodes.forEach((typeNode) => {
      const typeId = String(typeNode.dataset.id || '');
      if (!typeId) return;
      const categoryId = getTypeCategoryId(typeNode);
      const categoryNode = categoryId ? findCategoryNode(categoryId) : null;
      if (!categoryNode) hasUncategorized = true;
      const categoryGroup = categoryNode?.closest('.tree-group');
      const typeSection = categoryGroup?.querySelector(':scope > .children > .master-category-types-section');
      const destination = typeSection?.querySelector(':scope > .children') || uncategorizedChildren;
      if (!typeSection) hasUncategorized = true;

      const typeGroup = document.createElement('div');
      typeGroup.className = 'tree-group master-hierarchy-group open';
      const typeNested = document.createElement('div');
      typeNested.className = 'children';
      typeGroup.append(typeNode, typeNested);
      destination.appendChild(typeGroup);
      typeGroupsById.set(typeId, typeGroup);

      const modelSection = document.createElement('div');
      modelSection.className = 'master-type-models-section';
      const modelLabel = document.createElement('div');
      modelLabel.className = 'tree-node master-type-models-label';
      modelLabel.textContent = '🚙 الطرازات';
      const modelList = document.createElement('div');
      modelList.className = 'children';
      const addForType = document.createElement('button');
      addForType.className = 'tree-node master-inline-add';
      addForType.type = 'button';
      addForType.dataset.newModelForType = typeId;
      addForType.textContent = '＋ إضافة طراز';
      modelSection.append(modelLabel, modelList, addForType);
      typeNested.appendChild(modelSection);
    });

    // Keep original type-create control reachable, without deleting it.
    if (addType) {
      addType.classList.add('master-inline-add-type');
      uncategorizedChildren.appendChild(addType);
    }
    if (hasUncategorized || addType) categoryChildren.appendChild(uncategorizedGroup);

    const unassignedModelsGroup = document.createElement('div');
    unassignedModelsGroup.className = 'tree-group master-unassigned-models open';
    const unassignedModelsNode = document.createElement('button');
    unassignedModelsNode.className = 'tree-node';
    unassignedModelsNode.type = 'button';
    unassignedModelsNode.innerHTML = '<span class="tree-toggle">⌄</span>🚙 طرازات غير مرتبطة بنوع عتاد';
    const unassignedModelsChildren = document.createElement('div');
    unassignedModelsChildren.className = 'children';
    unassignedModelsGroup.append(unassignedModelsNode, unassignedModelsChildren);

    const modelGroups = Array.from(modelChildren.querySelectorAll(':scope > .model-group'));
    let hasUnassignedModels = false;
    modelGroups.forEach((modelGroup) => {
      const row = modelGroup.querySelector(':scope > [data-model-row]');
      if (!row) return;
      const id = String(row.dataset.modelRow || '');
      const model = DATA[id] || DATA[Number(id)];
      if (!model) return;
      const typeGroup = typeGroupsById.get(String(model.equipment_type_id));
      const modelSection = typeGroup?.querySelector(':scope > .children > .master-type-models-section');
      const modelList = modelSection?.querySelector(':scope > .children');
      if (modelList) {
        modelList.appendChild(modelGroup);
      } else {
        hasUnassignedModels = true;
        unassignedModelsChildren.appendChild(modelGroup);
      }
    });

    // Preserve the original model-create control. It remains functional as a
    // general create action when no parent type is supplied.
    if (addModel) {
      addModel.classList.add('master-inline-add');
      unassignedModelsChildren.appendChild(addModel);
    }
    if (hasUnassignedModels || addModel) categoryChildren.appendChild(unassignedModelsGroup);

    typeRoot.remove();
    modelRoot.remove();
    categoryRoot.dataset.hierarchyBuilt = '1';
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildRealHierarchy, { once: true });
  } else {
    buildRealHierarchy();
  }
  const setupModelWorkspace = () => {
    const panel = document.getElementById('modelPanel');
    if (!panel || panel.dataset.workspaceReady === '1') return;
    const boxes = Array.from(panel.querySelectorAll('.box'));
    if (!boxes.length) return;
    const nav = document.createElement('nav');
    nav.className = 'model-workspace-nav';
    nav.setAttribute('aria-label', 'أقسام الطراز');
    const icons = ['📄', '🛞', '🔋', '⚙'];
    const tabs = [];
    const selectSection = (index, options = {}) => {
      const safeIndex = Math.max(0, Math.min(Number(index) || 0, boxes.length - 1));
      boxes.forEach((box, boxIndex) => {
        box.hidden = boxIndex !== safeIndex;
        box.dataset.workspaceActive = boxIndex === safeIndex ? '1' : '0';
      });
      tabs.forEach((tab, tabIndex) => {
        const active = tabIndex === safeIndex;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      if (options.focus) {
        const box = boxes[safeIndex];
        box.classList.add('workspace-focus');
        window.setTimeout(() => box.classList.remove('workspace-focus'), 900);
      }
      if (options.scroll) boxes[safeIndex]?.scrollIntoView({behavior:'smooth', block:'start'});
      panel.dataset.workspaceSection = String(safeIndex);
    };
    boxes.forEach((box, index) => {
      box.classList.add('model-workspace-box');
      box.dataset.workspaceSection = String(index);
      const heading = box.querySelector(':scope > .box-head h3');
      const text = heading?.textContent.trim() || `القسم ${index + 1}`;
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.className = 'model-workspace-tab';
      tab.dataset.workspaceTarget = String(index);
      tab.setAttribute('aria-controls', `model-workspace-section-${index}`);
      tab.setAttribute('aria-selected', 'false');
      box.id = box.id || `model-workspace-section-${index}`;
      tab.innerHTML = `<span class="tab-icon">${icons[index] || '•'}</span>${text}`;
      tab.addEventListener('click', () => selectSection(index, {focus:true}));
      tabs.push(tab);
      nav.appendChild(tab);
    });
    const summary = document.createElement('div');
    summary.className = 'model-workspace-summary';
    summary.innerHTML = '<strong>مساحة عمل الطراز</strong><span>اختر قسمًا واحدًا لإدارة بياناته دون ازدحام باقي الأقسام</span>';
    panel.insertBefore(summary, boxes[0]);
    panel.insertBefore(nav, boxes[0]);
    panel.dataset.workspaceReady = '1';
    window.MATERIEL_MODEL_WORKSPACE_SELECT = selectSection;
    selectSection(0);
  };
  setupModelWorkspace();

  const openModelCreate = (typeId) => {
    if (typeof resetModel === 'function') resetModel();
    if (typeId) {
      const typeSelect = document.getElementById('modelType');
      const categorySelect = document.getElementById('modelCategory');
      const option = typeSelect?.querySelector(`option[value="${CSS.escape(String(typeId))}"]`);
      if (typeSelect && option) {
        typeSelect.value = String(typeId);
        if (categorySelect && option.dataset.category) categorySelect.value = option.dataset.category;
      }
    }
    if (typeof title === 'function') title('إضافة طراز', 'الطرازات');
    if (typeof show === 'function') show(document.getElementById('modelPanel'));
    window.MATERIEL_MODEL_WORKSPACE_SELECT?.(0);
    document.getElementById('modelPanel')?.scrollIntoView({behavior:'smooth', block:'start'});
  };

  const openTypeCreate = (categoryId) => {
    if (typeof refPanel !== 'function') return;
    refPanel('type');
    const form = document.querySelector('#refBody form');
    const category = form?.querySelector('[name="category_id"]');
    if (category && categoryId) category.value = String(categoryId);
  };

  const postDelete = (kind, id, message, action) => {
    if (!id) return;
    if (!window.confirm(message)) return;
    const form = document.createElement('form');
    form.method = 'post';
    form.action = action;
    form.style.display = 'none';
    document.body.appendChild(form);
    form.submit();
  };
  const deleteModel = (id) => postDelete('model', id, 'حذف الطراز؟ سيتم تطبيق حماية النظام الحالية ولن يتم حذف طراز مرتبط ببيانات تمنع الحذف.', `/equipment-types/models/${encodeURIComponent(id)}/delete`);
  const deleteHierarchyItem = (kind, id) => {
    if (kind === 'category') postDelete(kind, id, 'حذف الفئة؟ إذا كانت مرتبطة بأنواع عتاد سيمنع النظام الحذف.', `/equipment-types/categories/${encodeURIComponent(id)}/delete`);
    if (kind === 'type') postDelete(kind, id, 'حذف نوع العتاد؟ إذا كان مرتبطاً بطرازات سيمنع النظام الحذف.', `/equipment-types/${encodeURIComponent(id)}/delete`);
  };
  const editHierarchyItem = (kind, id) => {
    const node = tree.querySelector(`[data-ref-item="${kind}"][data-id="${CSS.escape(String(id))}"]`);
    if (!node || typeof refPanel !== 'function') return;
    refPanel(kind, id, node.dataset.name || '', node.dataset);
    selectNode(node);
  };
  const contextMenu = document.createElement('div');
  contextMenu.className = 'master-context-menu';
  contextMenu.hidden = true;
  contextMenu.setAttribute('dir', 'rtl');
  document.body.appendChild(contextMenu);
  const closeContextMenu = () => { contextMenu.hidden = true; contextMenu.replaceChildren(); };
  const deleteBrand = (id) => postDelete('brand', id, 'حذف العلامة التجارية؟ إذا كانت مرتبطة بطرازات سيمنع النظام الحذف.', '/equipment-types/brands/' + encodeURIComponent(id) + '/delete');
  const showContextMenu = (node, x, y) => {
    const model = node.closest('[data-model-row]');
    const ref = node.closest('[data-ref-item]');
    const actions = [];
    if (model) {
      const id = model.dataset.modelRow;
      actions.push(['👁 عرض الطراز', () => viewModel(id)]);
      actions.push(['✏️ تعديل الطراز', () => editModel(id)]);
      actions.push(['⧉ نسخ الطراز', () => {
        editModel(id);
        const name = document.getElementById('modelName');
        const form = document.getElementById('modelForm');
        const hidden = document.getElementById('modelId');
        if (name) name.value += ' - نسخة';
        if (hidden) hidden.value = '';
        if (form) form.action = '/equipment-types/models/create';
        currentModel = null;
      }]);
      actions.push(['🗑 حذف الطراز', () => deleteModel(id)]);
    } else if (ref) {
      const kind = ref.dataset.refItem, id = ref.dataset.id, name = ref.dataset.name || '';
      const labels = {category:'الفئة', type:'نوع العتاد', brand:'العلامة التجارية', spec:'الخاصية'};
      actions.push(['✏️ تعديل ' + (labels[kind] || 'العنصر'), () => editHierarchyItem(kind, id)]);
      if (kind === 'brand') actions[actions.length - 1] = ['✏️ تعديل العلامة التجارية', () => refPanel(kind, id, name, ref.dataset)];
      if (kind === 'category' || kind === 'type') actions.push(['🗑 حذف ' + labels[kind], () => deleteHierarchyItem(kind, id)]);
      if (kind === 'brand') actions.push(['🗑 حذف العلامة التجارية', () => deleteBrand(id)]);
    } else return;
    contextMenu.replaceChildren();
    actions.forEach(([label, action]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.onclick = () => { closeContextMenu(); action(); };
      contextMenu.appendChild(button);
    });
    contextMenu.hidden = false;
    const rect = contextMenu.getBoundingClientRect();
    contextMenu.style.left = Math.max(8, Math.min(x, innerWidth - rect.width - 8)) + 'px';
    contextMenu.style.top = Math.max(8, Math.min(y, innerHeight - rect.height - 8)) + 'px';
  };
  tree.addEventListener('contextmenu', (event) => {
    const node = event.target.closest('[data-model-row],[data-ref-item]');
    if (!node || !tree.contains(node)) return;
    event.preventDefault();
    event.stopPropagation();
    showContextMenu(node, event.clientX, event.clientY);
  });
  let longPressTimer = null, longPressTarget = null;
  tree.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'touch') return;
    const node = event.target.closest('[data-model-row],[data-ref-item]');
    if (!node || !tree.contains(node)) return;
    longPressTarget = node;
    longPressTimer = window.setTimeout(() => {
      showContextMenu(longPressTarget, event.clientX || 20, event.clientY || 80);
      longPressTarget = null;
    }, 600);
  });
  ['pointerup','pointercancel','pointerleave'].forEach((type) => tree.addEventListener(type, () => {
    if (longPressTimer) window.clearTimeout(longPressTimer);
    longPressTimer = null;
  }));
  document.addEventListener('pointerdown', (event) => {
    if (!contextMenu.contains(event.target)) closeContextMenu();
  });

  const syncArrows = () => {
    tree.querySelectorAll('.tree-group').forEach((group) => {
      const node = group.querySelector(':scope > .tree-node');
      const arrow = node?.querySelector(':scope > .tree-toggle');
      if (!arrow) return;
      arrow.textContent = group.classList.contains('open') ? '⌄' : '›';
      node.setAttribute('aria-expanded', group.classList.contains('open') ? 'true' : 'false');
    });
  };

  tree.addEventListener('click', (event) => {
    const addForType = event.target.closest('[data-new-model-for-type]');
    if (addForType && tree.contains(addForType)) {
      event.preventDefault(); event.stopPropagation();
      openModelCreate(addForType.dataset.newModelForType); return;
    }
    const addForCategory = event.target.closest('[data-new-type-for-category]');
    if (addForCategory && tree.contains(addForCategory)) {
      event.preventDefault(); event.stopPropagation();
      openTypeCreate(addForCategory.dataset.newTypeForCategory); return;
    }
    const add = event.target.closest('[data-add],[data-new-ref]');
    if (add && tree.contains(add)) {
      event.preventDefault(); event.stopPropagation();
      const kind = add.dataset.add || add.dataset.newRef;
      if (kind === 'model') openModelCreate();
      else if (kind) refPanel(kind);
    }
  }, true);

  tree.addEventListener('click', (event) => {
    const toggle = event.target.closest('.tree-toggle');
    if (!toggle || !tree.contains(toggle)) return;
    const group = toggle.closest('.tree-group');
    if (!group) return;
    event.preventDefault(); event.stopPropagation(); group.classList.toggle('open'); syncArrows();
  }, true);

  tree.addEventListener('click', (event) => {
    const node = event.target.closest('.tree-node');
    if (!node || !tree.contains(node)) return;
    if (event.target.closest('.tree-toggle,[data-add],[data-new-ref],[data-new-model-for-type],[data-new-type-for-category],[data-delete],[data-tree-delete],[data-tree-edit],[data-copy],[data-tree-add]')) return;
    if (node.matches('[data-model-row]')) {
      window.MATERIEL_MODEL_WORKSPACE_SELECT?.(0);
      return;
    }
    if (node.matches('[data-model]')) {
      const section = node.dataset.section || 'basic';
      const sectionIndex = {basic:0, tires:1, positions:1, sizes:1, batteries:2, specs:3}[section] ?? 0;
      window.MATERIEL_MODEL_WORKSPACE_SELECT?.(sectionIndex, {focus:true});
      return;
    }
    if (node.matches('[data-ref]')) {
      event.preventDefault(); event.stopPropagation();
      if (typeof selectNode === 'function') selectNode(node);
      const labels = {categories:'الفئات',types:'أنواع العتاد',brands:'العلامات التجارية',specs:'الخصائص',models:'الطرازات'};
      if (typeof title === 'function') title(labels[node.dataset.ref] || node.textContent.trim());
    }
  }, true);

  const revealAncestors = (node) => {
    let group = node.parentElement?.closest('.tree-group');
    while (group && tree.contains(group)) {
      const parentNode = group.querySelector(':scope > .tree-node');
      if (parentNode) parentNode.hidden = false;
      group.classList.add('open');
      group = group.parentElement?.closest('.tree-group');
    }
  };
  const searchableNodes = () => Array.from(tree.querySelectorAll('.tree-node')).filter((node) => !node.matches('[data-add],[data-tree-add],[data-copy],[data-delete],[data-tree-edit],[data-tree-delete]'));
  const searchTree = (q) => {
    const query = String(q || '').trim().toLocaleLowerCase();
    const nodes = searchableNodes();
    if (!query) { nodes.forEach((node) => { node.hidden = false; }); syncArrows(); return; }
    nodes.forEach((node) => { node.hidden = !node.textContent.toLocaleLowerCase().includes(query); });
    nodes.forEach((node) => { if (!node.hidden) revealAncestors(node); });
    syncArrows();
  };
  const searchInput = document.getElementById('treeSearch');
  if (searchInput) searchInput.addEventListener('input', () => searchTree(searchInput.value));
  new MutationObserver(syncArrows).observe(tree, {subtree:true,attributes:true,attributeFilter:['class']});
  syncArrows();
})();
