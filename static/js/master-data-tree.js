(() => {
  'use strict';

  const tree = document.getElementById('tree');
  if (!tree) return;

  const style = document.createElement('style');
  style.textContent = `
    #tree .tree-context{margin-right:6px;color:#64748b;font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #tree .tree-node[data-model-row]{min-height:38px}
    #tree .tree-node[data-model-row] .tree-toggle{font-size:14px}
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

  // Add the real classification path to every model without duplicating the model tree.
  // DATA is supplied by master_data_workspace.html and contains the persisted model/type/category ids.
  if (typeof DATA !== 'undefined') {
    tree.querySelectorAll('[data-model-row]').forEach((row) => {
      if (row.querySelector('.tree-context')) return;
      const id = String(row.dataset.modelRow);
      const model = DATA[id] || DATA[Number(id)];
      if (!model) return;
      const category = categories.get(String(model.category_id));
      const type = types.get(String(model.equipment_type_id));
      const parts = [category, type].filter(Boolean);
      if (!parts.length) return;
      const context = document.createElement('span');
      context.className = 'tree-context';
      context.textContent = `(${parts.join(' / ')})`;
      row.appendChild(context);
      row.title = `${row.textContent.trim()}`;
    });
  }

  // The arrow is the only control that expands/collapses a group.
  // Clicking the label of a model/section continues to open its workspace.
  tree.addEventListener('click', (event) => {
    const node = event.target.closest('.tree-node');
    if (!node || !tree.contains(node)) return;

    const toggle = event.target.closest('.tree-toggle');
    if (toggle) return; // Existing delegated handler owns the actual toggle.

    // Model and model-section labels are actionable workspace entries.
    if (node.matches('[data-model-row], [data-model]')) return;

    // Root/reference branch labels must never toggle just because they contain an arrow.
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

  const syncArrows = () => {
    tree.querySelectorAll('.tree-group').forEach((group) => {
      const node = group.querySelector(':scope > .tree-node');
      const arrow = node?.querySelector(':scope > .tree-toggle');
      if (!arrow) return;
      arrow.textContent = group.classList.contains('open') ? '⌄' : '›';
      node.setAttribute('aria-expanded', group.classList.contains('open') ? 'true' : 'false');
    });
  };

  new MutationObserver(syncArrows).observe(tree, { subtree: true, attributes: true, attributeFilter: ['class'] });
  syncArrows();
})();
