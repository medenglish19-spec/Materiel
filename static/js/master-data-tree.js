(() => {
  'use strict';

  const tree = document.getElementById('tree');
  if (!tree) return;

  const style = document.createElement('style');
  style.textContent = `
    /* Professional Admin workspace: hierarchy left, selected workspace right. */
    .mdx .layout{direction:ltr;grid-template-columns:minmax(320px,380px) minmax(0,1fr);gap:16px;align-items:stretch}
    .mdx .tree-card,.mdx .editor{direction:rtl}
    .mdx .tree-card{background:#fbfcfe;border-color:#dbe3ec;box-shadow:0 8px 24px rgba(15,23,42,.06);padding:14px;min-width:0}
    .mdx .editor{background:#fff;border-color:#dbe3ec;box-shadow:0 8px 28px rgba(15,23,42,.07);min-width:0}
    .mdx .tree-head{padding:5px 4px 13px;border-bottom:1px solid #dfe6ee;color:#172b4d}
    .mdx .tree-head strong{font-size:14px;letter-spacing:-.1px}
    .mdx .tree-head .muted{font-size:11px;background:#eef3f8;color:#53657d;padding:4px 8px;border-radius:999px}
    .mdx .tree-search{margin:12px 0 13px;background:#fff;border-color:#cfd9e5;box-shadow:0 1px 2px rgba(15,23,42,.03);height:40px;color:#1e293b}
    .mdx .tree-search::placeholder{color:#8a98aa}
    .mdx .tree-search:focus{outline:none;border-color:#5b8db8;box-shadow:0 0 0 3px rgba(91,141,184,.12)}
    #tree .tree-context{margin-right:6px;color:#64748b;font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #tree .tree-node[data-model-row]{min-height:38px}
    #tree .tree-node[data-model-row] .tree-toggle{font-size:14px}
    #tree .master-hierarchy-group{margin-bottom:3px}
    #tree .master-hierarchy-group>.children{padding-right:20px}
    #tree .master-category-types-label,#tree .master-type-models-label{font-weight:800;color:#475569}
    #tree .master-uncategorized{margin-top:8px;padding-top:6px;border-top:1px dashed #cbd5e1}
    #tree .master-unassigned-models{margin-top:8px;padding-top:6px;border-top:1px dashed #cbd5e1}
    #tree .master-reference-group{margin-top:6px}
    #tree .master-reference-label{font-size:11px;color:#94a3b8;font-weight:800;padding:5px 8px}
    #tree .master-inline-add{margin:4px 0 4px}
    .mdx #tree{font-size:13px;color:#25364d}
    .mdx #tree .tree-node{min-height:36px;padding:7px 8px;gap:7px;color:#26384e;font-weight:600;transition:background .12s ease,border-color .12s ease,color .12s ease}
    .mdx #tree .tree-node:hover{background:#edf4fa;color:#173b63}
    .mdx #tree .tree-node.active{background:#e7f0f8;color:#173b63;box-shadow:inset -3px 0 0 #3f729f;font-weight:800}
    .mdx #tree .tree-toggle{color:#64748b;font-weight:800}
    .mdx #tree .tree-actions{opacity:.9;margin-right:auto;display:flex;gap:3px}
    .mdx #tree .tree-node:hover .tree-actions,.mdx #tree .tree-node.active .tree-actions{opacity:1}
    .mdx #tree .tree-add,.mdx #tree .tree-more,.mdx #tree .tree-action{color:#315f88;border:0;background:transparent;border-radius:6px;padding:3px 6px;font-weight:900;cursor:pointer}
    .mdx #tree .tree-add:hover,.mdx #tree .tree-more:hover,.mdx #tree .tree-action:hover{background:#dbeafe}
    .mdx #tree .tree-more[data-delete]{color:#a33b3b}
    .mdx #tree .children{padding-right:18px;margin-right:8px;border-right:1px solid #e2e8f0}
    .mdx #tree>.master-reference-block{padding:7px 0 12px;margin-bottom:9px;border-bottom:1px solid #dfe6ee}
    .mdx .master-reference-heading{color:#66778c;font-size:11px;letter-spacing:.15px;padding:5px 8px;text-transform:none}
    .mdx .editor-head{padding:18px 22px 16px;background:linear-gradient(to bottom,#fff,#fbfcfe);border-bottom:1px solid #dfe6ee}
    .mdx .editor-head small{display:block;color:#728197;font-size:11px;margin-bottom:5px}
    .mdx .editor-head h2{font-size:21px;letter-spacing:-.25px;color:#173b63}
    .mdx .body{padding:20px 22px;background:#fbfcfe;min-height:640px}
    .mdx .panel.active{animation:mdxPanelIn .14s ease-out}
    .mdx .box{background:#fff;border-color:#dfe6ee;border-radius:12px;box-shadow:0 2px 8px rgba(15,23,42,.035)}
    .mdx .box-head{background:#f7f9fb;padding:11px 14px;border-bottom-color:#dfe6ee}
    .mdx .box-head h3{color:#203c5c;font-size:14px}
    .mdx .box-body{padding:15px}
    .mdx .field{color:#33465d}
    .mdx .field input,.mdx .field select,.mdx .ref-form input,.mdx .ref-form select,.mdx .tbl input,.mdx .tbl select{background:#fff;color:#26384e;border-color:#ccd7e3}
    .mdx .field input:focus,.mdx .field select:focus,.mdx .ref-form input:focus,.mdx .ref-form select:focus,.mdx .tbl input:focus,.mdx .tbl select:focus{outline:none;border-color:#5b8db8;box-shadow:0 0 0 3px rgba(91,141,184,.1)}
    .mdx .check{color:#33465d;background:#f8fafc;border-color:#dfe6ee}
    .mdx .tbl th{background:#f5f7fa;color:#5b6b80;font-weight:800}
    .mdx .tbl td{color:#33465d}
    .mdx .muted{color:#68788d}
    .mdx .empty{min-height:520px;background:#fff;border:1px dashed #d4dee9;border-radius:12px;color:#64748b;padding:30px}
    .mdx .soft{background:#edf3f8;color:#234f75;border:1px solid #d6e2ec}
    .mdx .primary{background:#234f75;color:#fff;box-shadow:0 2px 5px rgba(35,79,117,.16)}
    .mdx .danger{border:1px solid #fecaca}
    .mdx .model-workspace-nav{position:sticky;top:10px;z-index:5;display:flex;gap:6px;align-items:center;overflow:auto;padding:7px;margin:0 0 14px;background:rgba(255,255,255,.96);border:1px solid #dfe6ee;border-radius:11px;box-shadow:0 4px 14px rgba(15,23,42,.05);scrollbar-width:thin}
    .mdx .model-workspace-nav:before{content:'أقسام الطراز';font-size:11px;font-weight:800;color:#718096;padding:0 7px;white-space:nowrap;border-left:1px solid #e2e8f0}
    .mdx .model-workspace-tab{border:1px solid transparent;background:transparent;color:#52657b;border-radius:8px;padding:8px 11px;white-space:nowrap;font:inherit;font-size:12px;font-weight:800;cursor:pointer;transition:all .12s ease}
    .mdx .model-workspace-tab:hover{background:#edf4fa;color:#234f75}
    .mdx .model-workspace-tab.active{background:#e7f0f8;color:#173b63;border-color:#cbdbea;box-shadow:0 1px 2px rgba(15,23,42,.04)}
    .mdx .model-workspace-tab .tab-icon{margin-left:5px}
    .mdx .model-workspace-box{scroll-margin-top:78px}
    .mdx .model-workspace-box.workspace-focus{outline:2px solid #b7d0e6;outline-offset:2px}
    .mdx .model-workspace-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 12px;padding:10px 13px;background:#f5f8fb;border:1px solid #dfe7ef;border-radius:10px;color:#53657a;font-size:12px}
    .mdx .model-workspace-summary strong{color:#234f75;font-size:13px}
    @keyframes mdxPanelIn{from{opacity:.65;transform:translateY(2px)}to{opacity:1;transform:none}}
    @media(max-width:1000px){.mdx .layout{direction:rtl;grid-template-columns:1fr}.mdx .tree-card{order:1}.mdx .editor{order:2}}
    @media(max-width:760px){.mdx .model-workspace-nav{top:4px}.mdx .model-workspace-nav:before{display:none}.mdx .model-workspace-tab{padding:7px 9px}}
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

    const addType = typeChildren.querySelector('[data-new-ref="type"]');
    const addModel = modelChildren.querySelector('[data-new-ref="model"]');
    if (addType) addType.remove();
    if (addModel) addModel.remove();

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
    let hasTypes = false;
    const typeNodes = Array.from(typeChildren.querySelectorAll(':scope > [data-ref-item="type"]'));

    const getTypeCategoryId = (typeNode) => {
      const id = String(typeNode.dataset.id || '');
      return typeCategoryMap.get(id)
        || String(typeNode.dataset.categoryId || typeNode.dataset.category || '');
    };

    typeNodes.forEach((typeNode) => {
      const typeId = String(typeNode.dataset.id || '');
      if (!typeId) return;
      hasTypes = true;
      const categoryId = getTypeCategoryId(typeNode);
      const categoryNode = categoryId ? findCategoryNode(categoryId) : null;
      const categoryGroup = categoryNode?.closest('.tree-group');
      const destination = categoryGroup?.querySelector(':scope > .children') || uncategorizedChildren;
      if (!categoryNode) hasUncategorized = true;

      let typeSection = destination.querySelector(':scope > .master-category-types-section');
      if (!typeSection) {
        typeSection = document.createElement('div');
        typeSection.className = 'master-category-types-section';
        destination.appendChild(typeSection);
        const label = document.createElement('div');
        label.className = 'tree-node master-category-types-label';
        label.textContent = '🗂 أنواع العتاد';
        typeSection.appendChild(label);
        const typeList = document.createElement('div');
        typeList.className = 'children';
        typeSection.appendChild(typeList);
      }
      const typeList = typeSection.querySelector(':scope > .children');

      const typeGroup = document.createElement('div');
      typeGroup.className = 'tree-group master-hierarchy-group open';
      const typeClone = typeNode.cloneNode(true);
      const typeNested = document.createElement('div');
      typeNested.className = 'children';
      typeGroup.append(typeClone, typeNested);
      typeList.appendChild(typeGroup);
      typeNode.remove();
      typeGroupsById.set(typeId, typeGroup);

      const modelSection = document.createElement('div');
      modelSection.className = 'master-type-models-section';
      const modelLabel = document.createElement('div');
      modelLabel.className = 'tree-node master-type-models-label';
      modelLabel.textContent = '🚙 الطرازات';
      modelSection.appendChild(modelLabel);
      const modelList = document.createElement('div');
      modelList.className = 'children';
      modelSection.appendChild(modelList);
      typeNested.appendChild(modelSection);

      const addForType = document.createElement('button');
      addForType.className = 'tree-node master-inline-add';
      addForType.type = 'button';
      addForType.dataset.newModelForType = typeId;
      addForType.textContent = '＋ إضافة طراز';
      modelList.appendChild(addForType);
    });

    if (hasUncategorized) categoryChildren.appendChild(uncategorizedGroup);

    const modelGroups = Array.from(modelChildren.querySelectorAll(':scope > .model-group'));
    let allModelsMoved = true;
    modelGroups.forEach((modelGroup) => {
      const row = modelGroup.querySelector(':scope > [data-model-row]');
      if (!row) { allModelsMoved = false; return; }
      const id = String(row.dataset.modelRow || '');
      const model = DATA[id] || DATA[Number(id)];
      if (!model) { allModelsMoved = false; return; }
      const typeGroup = typeGroupsById.get(String(model.equipment_type_id));
      const modelSection = typeGroup?.querySelector(':scope > .children > .master-type-models-section');
      const modelList = modelSection?.querySelector(':scope > .children');
      if (!modelList) { allModelsMoved = false; return; }
      modelList.appendChild(modelGroup);
    });

    if (hasTypes && addModel) {
      addModel.dataset.globalModelFallback = '1';
      addModel.style.display = 'none';
      modelChildren.appendChild(addModel);
    } else if (!hasTypes && addModel) {
      modelChildren.appendChild(addModel);
    }

    const remainingTypes = typeChildren.querySelectorAll(':scope > [data-ref-item="type"]');
    const remainingModels = modelChildren.querySelectorAll(':scope > .model-group');
    if (remainingTypes.length === 0) typeRoot.remove();
    if (remainingModels.length === 0 && allModelsMoved) modelRoot.remove();
    categoryRoot.dataset.hierarchyBuilt = '1';
  };

  buildRealHierarchy();

  const setupModelWorkspace = () => {
    const panel = document.getElementById('modelPanel');
    if (!panel || panel.dataset.workspaceReady === '1') return;
    const boxes = Array.from(panel.children).filter((child) => child.classList?.contains('box'));
    if (!boxes.length) return;
    const nav = document.createElement('nav');
    nav.className = 'model-workspace-nav';
    nav.setAttribute('aria-label', 'أقسام الطراز');
    const icons = ['📄', '🛞', '🔋', '⚙'];
    boxes.forEach((box, index) => {
      box.classList.add('model-workspace-box');
      box.dataset.workspaceSection = String(index);
      const heading = box.querySelector(':scope > .box-head h3');
      const text = heading?.textContent.trim() || `القسم ${index + 1}`;
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.className = 'model-workspace-tab';
      tab.dataset.workspaceTarget = String(index);
      tab.innerHTML = `<span class="tab-icon">${icons[index] || '•'}</span>${text}`;
      tab.addEventListener('click', () => {
        box.scrollIntoView({behavior:'smooth', block:'start'});
        boxes.forEach((item) => item.classList.remove('workspace-focus'));
        box.classList.add('workspace-focus');
        nav.querySelectorAll('.model-workspace-tab').forEach((item) => item.classList.toggle('active', item === tab));
        window.setTimeout(() => box.classList.remove('workspace-focus'), 900);
      });
      nav.appendChild(tab);
    });
    const summary = document.createElement('div');
    summary.className = 'model-workspace-summary';
    summary.innerHTML = '<strong>مساحة عمل الطراز</strong><span>البيانات والإطارات والبطاريات والخصائص التابعة في صفحة واحدة</span>';
    panel.insertBefore(summary, boxes[0]);
    panel.insertBefore(nav, boxes[0]);
    panel.dataset.workspaceReady = '1';
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
    document.getElementById('modelPanel')?.scrollIntoView({behavior:'smooth', block:'start'});
  };

  const deleteModel = (id) => {
    if (!id) return;
    if (!window.confirm('حذف الطراز؟ سيتم تطبيق حماية النظام الحالية ولن يتم حذف طراز مرتبط ببيانات تمنع الحذف.')) return;
    const form = document.createElement('form');
    form.method = 'post';
    form.action = `/equipment-types/models/${encodeURIComponent(id)}/delete`;
    form.style.display = 'none';
    document.body.appendChild(form);
    form.submit();
  };

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
      event.preventDefault();
      event.stopPropagation();
      openModelCreate(addForType.dataset.newModelForType);
      return;
    }
    const add = event.target.closest('[data-add="model"],[data-new-ref="model"]');
    if (add && tree.contains(add)) {
      event.preventDefault();
      event.stopPropagation();
      openModelCreate();
      return;
    }
    const del = event.target.closest('[data-delete]');
    if (del && tree.contains(del)) {
      event.preventDefault();
      event.stopPropagation();
      deleteModel(del.dataset.delete);
    }
  }, true);

  tree.addEventListener('click', (event) => {
    const toggle = event.target.closest('.tree-toggle');
    if (!toggle || !tree.contains(toggle)) return;
    const group = toggle.closest('.tree-group');
    if (!group) return;
    event.preventDefault();
    event.stopPropagation();
    group.classList.toggle('open');
    syncArrows();
  }, true);

  tree.addEventListener('click', (event) => {
    const node = event.target.closest('.tree-node');
    if (!node || !tree.contains(node)) return;
    if (event.target.closest('.tree-toggle,[data-add],[data-new-ref],[data-new-model-for-type],[data-delete],[data-copy],[data-tree-add]')) return;
    if (node.matches('[data-model-row],[data-model]')) return;
    if (node.matches('[data-ref]')) {
      event.preventDefault();
      event.stopPropagation();
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

  const searchableNodes = () => Array.from(tree.querySelectorAll('.tree-node')).filter((node) => !node.matches('[data-add],[data-tree-add],[data-copy],[data-delete]'));
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