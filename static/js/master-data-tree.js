(() => {
  'use strict';

  const tree = document.getElementById('tree');
  if (!tree) return;

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
    if (options.focus && typeof window !== 'undefined') {
      const target = sections[safeIndex];
      if (target) target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  };

  window.MATERIEL_MODEL_WORKSPACE_SELECT = selectSection;

  const openTypeCreate = (categoryId) => {
    if (typeof resetModel === 'function') resetModel();
    if (typeof refPanel === 'function') {
      refPanel('type', null, '', { categoryId: String(categoryId || '') });
    }
    const form = document.querySelector('#refBody form');
    if (form) {
      const categoryInput = form.querySelector('[name="category_id"]');
      if (categoryInput && categoryId !== undefined && categoryId !== null && categoryId !== '') {
        categoryInput.value = String(categoryId);
      }
    }
  };

  const openModelCreate = (typeId) => {
    if (typeof resetModel === 'function') resetModel();
    const typeSelect = document.getElementById('modelType');
    const categorySelect = document.getElementById('modelCategory');
    const option = typeSelect && typeId !== undefined && typeId !== null
      ? typeSelect.querySelector(`option[value="${CSS.escape(String(typeId))}"]`)
      : null;
    if (typeSelect && option) {
      typeSelect.value = String(typeId);
      if (categorySelect && option.dataset.category) {
        categorySelect.value = option.dataset.category;
      }
    }
    if (typeof title === 'function') title('إضافة طراز', 'الطرازات');
    if (typeof show === 'function') show(document.getElementById('modelPanel'));
  };

  const syncModelWorkspace = () => {
    const panels = Array.from(document.querySelectorAll('#modelPanel [data-workspace-section]'));
    if (!panels.length) return;
    panels.forEach((panel, index) => {
      panel.hidden = index !== 0;
    });
    const tabs = Array.from(document.querySelectorAll('[data-model-workspace-tab]'));
    tabs.forEach((tab, index) => {
      tab.classList.toggle('is-active', index === 0);
      tab.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
    });
  };

  const style = document.createElement('style');
  style.textContent = `
    .master-context-menu{position:fixed;z-index:99999;min-width:190px;padding:5px;background:#fff;border:1px solid #dbe3ec;border-radius:10px;box-shadow:0 10px 30px rgba(15,23,42,.16);direction:rtl}
    .master-context-menu button{display:block;width:100%;border:0;background:transparent;text-align:right;padding:9px 11px;border-radius:7px;font:inherit;font-size:13px;font-weight:700;color:#26384a;cursor:pointer}
    .master-context-menu button:hover{background:#edf4fa;color:#173b63}
    .mdx .layout{display:grid;grid-template-columns:minmax(300px,390px) minmax(0,1fr);gap:16px;align-items:start}
    .mdx .tree-card{padding:0;overflow:hidden}
    .mdx .tree-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid #e8edf3;background:#f8fafc}
    .mdx .tree-search{width:100%;padding:10px 12px;border:1px solid #dfe7f0;border-radius:10px;margin:12px 16px 8px;background:#fff}
    .mdx .tree-group{border-top:1px solid #edf2f7}
    .mdx .tree-node{display:flex;align-items:center;gap:8px;width:100%;padding:9px 14px;border:0;background:transparent;color:#183a5d;font-weight:700;text-align:right;cursor:pointer}
    .mdx .tree-node.active{background:#eaf3ff;color:#0b3d72}
    .mdx .tree-toggle{display:inline-flex;width:18px;justify-content:center;color:#64748b;font-size:14px}
    .mdx .tree-actions{margin-inline-start:auto;display:flex;align-items:center;gap:8px}
    .mdx .tree-add{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:7px;border:1px solid #d0deee;background:#fff;color:#0d5ec7;font-weight:700;cursor:pointer}
    .mdx .children{padding:0 0 0 0}
    .mdx .children .tree-node{padding-right:28px}
    .mdx .children .children .tree-node{padding-right:42px}
    .mdx [data-workspace-section]{padding:18px;border-radius:12px;background:#fff;border:1px solid #e7edf6}
    [data-model-workspace-tab].is-active{background:#0d5ec7;color:#fff}
    @media (max-width: 900px){ .mdx .layout{grid-template-columns:1fr}.mdx .tree-card{min-height:auto}.mdx .tree-head{padding:12px 14px}.mdx .tree-search{margin:10px 12px 6px;width:calc(100% - 24px)} }
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
      const labels = {category:'الفئة', type:'نوع العتاد', brand:'العلامة التجارية', spec:'الخاصية'};
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
    } else {
      return;
    }

    menu.replaceChildren();
    actions.forEach(([label, action]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.addEventListener('click', () => {
        closeMenu();
        action();
      });
      menu.appendChild(button);
    });

    menu.hidden = false;
    const rect = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(Number(x) || 8, innerWidth - rect.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(Number(y) || 8, innerHeight - rect.height - 8)) + 'px';
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

  if (typeof syncModelWorkspace === 'function') syncModelWorkspace();

  tree.addEventListener('click', (event) => {
    const addTarget = event.target.closest('[data-add]');
    if (addTarget) {
      event.preventDefault();
      event.stopPropagation();
      const kind = addTarget.dataset.add;
      if (kind === 'category') {
        if (typeof refPanel === 'function') refPanel('category');
      } else if (kind === 'type') {
        const categoryId = addTarget.dataset.categoryId || addTarget.dataset.category || addTarget.dataset.newTypeForCategory;
        if (categoryId) openTypeCreate(categoryId);
      } else if (kind === 'model') {
        const typeId = addTarget.dataset.typeId || addTarget.dataset.modelType || addTarget.dataset.newModelForType;
        if (typeId) openModelCreate(typeId);
      } else if (kind) {
        if (typeof refPanel === 'function') refPanel(kind);
      }
      return;
    }

    const refTarget = event.target.closest('[data-new-ref]');
    if (refTarget) {
      event.preventDefault();
      event.stopPropagation();
      const kind = refTarget.dataset.newRef;
      if (kind === 'type' && refTarget.dataset.newTypeForCategory) {
        openTypeCreate(refTarget.dataset.newTypeForCategory);
        return;
      }
      if (kind === 'model' && refTarget.dataset.newModelForType) {
        openModelCreate(refTarget.dataset.newModelForType);
        return;
      }
      if (kind === 'model') openModelCreate();
      else if (kind) {
        if (typeof refPanel === 'function') refPanel(kind);
      }
      return;
    }

    const treeAdd = event.target.closest('[data-tree-add]');
    if (treeAdd) {
      event.preventDefault();
      event.stopPropagation();
      const modelNode = event.target.closest('[data-model]') || event.target.closest('[data-model-row]');
      if (modelNode && typeof editModel === 'function') {
        const section = treeAdd.dataset.treeAdd === 'position' ? 'positions' : treeAdd.dataset.treeAdd === 'size' ? 'sizes' : (treeAdd.dataset.treeAdd || 'basic');
        editModel(modelNode.dataset.model || modelNode.dataset.modelRow, section);
        if (treeAdd.dataset.treeAdd === 'position') {
          if (typeof addPos === 'function') addPos();
        } else if (treeAdd.dataset.treeAdd === 'size') {
          if (typeof addSize === 'function') addSize();
        }
      }
      return;
    }

    const toggle = event.target.closest('.tree-toggle');
    if (toggle) {
      event.preventDefault();
      event.stopPropagation();
      const group = toggle.closest('.tree-group');
      if (group) group.classList.toggle('open');
      return;
    }

    const modelRow = event.target.closest('[data-model-row]');
    if (modelRow) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof selectNode === 'function') selectNode(modelRow);
      if (typeof expandGroup === 'function') expandGroup(modelRow);
      if (typeof viewModel === 'function') viewModel(modelRow.dataset.modelRow);
      return;
    }

    const model = event.target.closest('[data-model]');
    if (model) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof selectNode === 'function') selectNode(model);
      const section = model.dataset.section || 'basic';
      if (typeof viewModel === 'function') viewModel(model.dataset.model);
      if (window.MATERIEL_MODEL_WORKSPACE_SELECT) {
        const map = { basic: 0, tires: 1, positions: 1, sizes: 1, batteries: 2, specs: 3 };
        window.MATERIEL_MODEL_WORKSPACE_SELECT(map[section] ?? 0, { focus: true });
      }
      return;
    }

    const item = event.target.closest('[data-ref-item]');
    if (item) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof selectNode === 'function') selectNode(item);
      if (typeof refPanel === 'function') refPanel(item.dataset.refItem, item.dataset.id, item.dataset.name, item.dataset);
      return;
    }

    const treeNode = event.target.closest('.tree-node');
    if (treeNode) {
      event.preventDefault();
      event.stopPropagation();
      if (typeof selectNode === 'function') selectNode(treeNode);
      const group = treeNode.closest('.tree-group');
      if (group && treeNode.querySelector('.tree-toggle')) {
        group.classList.toggle('open');
      }
    }
  });

  if (typeof setupModelWorkspace === 'function') {
    setupModelWorkspace();
  }
  if (typeof window !== 'undefined' && typeof window.MATERIEL_MODEL_WORKSPACE_SELECT === 'function') {
    window.MATERIEL_MODEL_WORKSPACE_SELECT(0);
  }
})();
