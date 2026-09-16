(() => {
  'use strict';

  const tree = document.getElementById('tree');
  if (!tree) return;

  const style = document.createElement('style');
  style.textContent = `
    #tree .tree-context{margin-right:6px;color:#64748b;font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #tree .tree-node[data-model-row]{min-height:38px}
    #tree .tree-node[data-model-row] .tree-toggle{font-size:14px}
    #tree .master-hierarchy-group{margin-bottom:3px}
    #tree .master-hierarchy-group>.children{padding-right:20px}
    #tree .master-models-label{font-weight:800;color:#475569}
    #tree .master-reference-root{margin-top:8px;padding-top:8px;border-top:1px solid #e5e7eb}
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

  // Build the visible hierarchy from the real persisted relations:
  // category -> equipment type -> model. Brands and spec definitions remain
  // independent reference data and are never attached to a category.
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
    if (addType) categoryChildren.appendChild(addType);

    const typeNodes = Array.from(typeChildren.querySelectorAll(':scope > [data-ref-item="type"]'));
    typeNodes.forEach((typeNode) => {
      const typeId = String(typeNode.dataset.id || '');
      let categoryId = typeCategoryMap.get(typeId) || '';
      if (!categoryId) {
        const model = Object.values(DATA).find((m) => String(m.equipment_type_id) === typeId);
        categoryId = model?.category_id ? String(model.category_id) : '';
      }
      const categoryNode = categoryId ? findCategoryNode(categoryId) : null;
      if (!categoryNode) return;

      const categoryGroup = categoryNode.closest('.tree-group');
      const categoryNested = categoryGroup?.querySelector(':scope > .children');
      if (!categoryNested) return;

      let typeGroup = document.createElement('div');
      typeGroup.className = 'tree-group master-hierarchy-group open';
      const typeButton = typeNode.cloneNode(true);
      typeGroup.appendChild(typeButton);
      const nested = document.createElement('div');
      nested.className = 'children';
      typeGroup.appendChild(nested);
      categoryNested.appendChild(typeGroup);
      typeNode.remove();
    });

    const modelGroups = Array.from(modelChildren.querySelectorAll(':scope > .model-group'));
    modelGroups.forEach((modelGroup) => {
      const row = modelGroup.querySelector(':scope > [data-model-row]');
      if (!row) return;
      const id = String(row.dataset.modelRow);
      const model = DATA[id] || DATA[Number(id)];
      if (!model) return;

      const typeNode = findTypeNode(model.equipment_type_id);
      const typeGroup = typeNode?.closest('.master-hierarchy-group');
      const nested = typeGroup?.querySelector(':scope > .children');
      if (!nested) return;

      let modelsLabel = nested.querySelector(':scope > .master-models-label');
      if (!modelsLabel) {
        modelsLabel = document.createElement('div');
        modelsLabel.className = 'tree-node master-models-label';
        modelsLabel.textContent = '🚙 الطرازات';
        nested.appendChild(modelsLabel);
      }
      nested.appendChild(modelGroup);
    });

    // Brands and specs remain separate top-level reference groups.
    typeRoot.classList.add('master-reference-root');
    modelRoot.remove();
    categoryRoot.dataset.hierarchyBuilt = '1';
  };

  buildRealHierarchy();

  // Restore the historical measurement-unit selector. These are the exact values
  // used by the previous Master Data implementation; no new unit source is created.
  const restoreMeasurementUnitSelect = () => {
    const input = document.querySelector('#refBody input[name="measurement_unit"]');
    if (!input || document.querySelector('#refBody select[name="measurement_unit"]')) return;
    const select = document.createElement('select');
    select.name = 'measurement_unit';
    select.required = true;
    [['km', 'كم'], ['hours', 'ساعات']].forEach(([value, label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });
    const previous = input.value;
    input.replaceWith(select);
    if (previous === 'km' || previous === 'hours') select.value = previous;
  };

  tree.addEventListener('click', (event) => {
    if (event.target.closest('[data-ref-item="type"], [data-new-ref="type"], [data-add="type"]')) {
      setTimeout(restoreMeasurementUnitSelect, 0);
    }
  }, true);
  setTimeout(restoreMeasurementUnitSelect, 0);

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

    if (event.target.closest('.tree-toggle')) return;
    if (node.matches('[data-model-row], [data-model]')) return;

    if (node.matches('[data-ref]')) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof selectNode === 'function') selectNode(node);
      const labels = {
        categories: 'الفئات',
        types: 'أنواع العتاد',
        brands: 'العلامات التجارية',
        specs: 'الخصائص',
        models: 'الطرازات',
      };
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

  const searchableNodes = () => Array.from(tree.querySelectorAll('.tree-node')).filter((node) => {
    return !node.matches('[data-add], [data-tree-add], [data-copy], [data-delete]');
  });

  const searchTree = (q) => {
    const query = String(q || '').trim().toLocaleLowerCase();
    const nodes = searchableNodes();

    if (!query) {
      nodes.forEach((node) => { node.hidden = false; });
      syncArrows();
      return;
    }

    nodes.forEach((node) => {
      node.hidden = !node.textContent.toLocaleLowerCase().includes(query);
    });

    nodes.forEach((node) => {
      if (!node.hidden) revealAncestors(node);
    });

    syncArrows();
  };

  const searchInput = document.getElementById('treeSearch');
  if (searchInput) {
    searchInput.addEventListener('input', () => searchTree(searchInput.value));
  }

  new MutationObserver(syncArrows).observe(tree, {
    subtree: true,
    attributes: true,
    attributeFilter: ['class'],
  });
  syncArrows();
})();
