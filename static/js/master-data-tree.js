(() => {
  'use strict';
  const tree = document.getElementById('equipment-tree-container');
  if (!tree) return;
  const DATA = window.MATERIEL_MASTER_DATA || {};
  const CATEGORIES = window.MATERIEL_CATEGORIES || [];
  const TYPES = window.MATERIEL_TYPES || [];
  const BRANDS = window.MATERIEL_BRANDS || [];
  const DEFS = window.MATERIEL_SPEC_DEFS || [];
  const $ = id => document.getElementById(id);
  let currentModel = null;
  let dragged = null;
  let dragOrigin = null;

  const toast = (message, undo) => {
    const box = $('tree-toast'), msg = $('toast-message'), undoBtn = $('toast-undo-btn');
    if (!box || !msg) return;
    msg.textContent = message;
    if (undo && undoBtn) { undoBtn.hidden = false; undoBtn.onclick = () => { undo(); box.classList.add('hidden'); }; }
    else if (undoBtn) { undoBtn.hidden = true; undoBtn.onclick = null; }
    box.classList.remove('hidden'); box.classList.add('flex');
    clearTimeout(toast.timer); toast.timer = setTimeout(() => { box.classList.add('hidden'); box.classList.remove('flex'); }, 3200);
  };

  const selectSection = (index, options = {}) => {
    const boxes = [...document.querySelectorAll('#modelPanel [data-workspace-section]')];
    const tabs = [...document.querySelectorAll('[data-model-workspace-tab]')];
    const safeIndex = Math.max(0, Math.min(Number(index) || 0, boxes.length - 1));
    boxes.forEach((box, boxIndex) => { box.hidden = boxIndex !== safeIndex; });
    tabs.forEach((tab, tabIndex) => { const active = tabIndex === safeIndex; tab.classList.toggle('is-active', active); tab.setAttribute('aria-selected', active ? 'true' : 'false'); });
    if (options.focus) boxes[safeIndex]?.scrollIntoView({block:'nearest', behavior:'smooth'});
  };
  window.MATERIEL_MODEL_WORKSPACE_SELECT = selectSection;
  const sectionMap = {basic:0, tires:1, positions:1, sizes:1, batteries:2, specs:3};
  const selectNode = node => {
    tree.querySelectorAll('.tree-node.active').forEach(x => x.classList.remove('active'));
    node?.classList.add('active');
    const label = node?.dataset.name || node?.textContent?.trim();
    if (label && $('current-active-node-name')) $('current-active-node-name').textContent = label;
  };

  const showPanel = panel => {
    ['refPanel','modelViewPanel','modelPanel'].forEach(id => $(id)?.classList.add('hidden'));
    $('empty')?.classList.add('hidden');
    panel?.classList.remove('hidden');
  };

  const setTitle = (title, crumb='مركز البيانات الأساسية') => {
    if ($('title')) $('title').textContent = title;
    if ($('crumb')) $('crumb').textContent = crumb;
  };

  window.viewModel = id => {
    const d = DATA[String(id)] || DATA[id] || {};
    currentModel = Number(id);
    setTitle(d.name || 'عرض الطراز', 'الطراز');
    const map = {viewModelName:d.name||'—',viewModelCategory:CATEGORIES.find(x=>Number(x.id)===Number(d.category_id))?.name||'—',viewModelType:TYPES.find(x=>Number(x.id)===Number(d.equipment_type_id))?.name||'—',viewModelBrand:BRANDS.find(x=>Number(x.id)===Number(d.brand_id))?.name||'—',viewHasTires:d.has_tires?'نعم':'لا',viewTirePositions:d.tire_positions_required ?? '—',viewAxleCount:d.axle_count ?? '—',viewTireSize:d.tire_size||'—',viewHasBatteries:d.has_batteries?'نعم':'لا',viewBatteryCount:d.battery_count_required ?? '—',viewBatteryCapacity:d.battery_capacity_ah ?? '—'};
    Object.entries(map).forEach(([id,v]) => { if ($(id)) $(id).textContent = v; });
    if ($('viewPositionsBody')) $('viewPositionsBody').innerHTML=(d.positions||[]).map(x=>'<tr><td>'+ (x.axle_number??'—') +'</td><td>'+ (x.side==='right'?'يمين':'يسار') +'</td><td>'+({single:'مفرد',inner:'داخلي',outer:'خارجي'}[x.position_type||x.type]||'—')+'</td><td>'+(x.description||'—')+'</td></tr>').join('')||'<tr><td colspan="4">لا توجد بيانات</td></tr>';
    if ($('viewSizesBody')) $('viewSizesBody').innerHTML=(d.sizes||[]).map(x=>'<tr><td>'+(typeof x==='string'?x:x.size||'—')+'</td></tr>').join('')||'<tr><td>لا توجد مقاسات</td></tr>';
    if ($('viewSpecRows')) $('viewSpecRows').innerHTML=(d.specs||[]).map(x=>{const def=DEFS.find(y=>Number(y.id)===Number(x.definition_id));return def?'<div class="field"><span>'+def.name+(def.unit?' ('+def.unit+')':'')+'</span><strong>'+(x.value??'—')+'</strong></div>':''}).join('')||'<div class="field"><span>لا توجد خصائص</span></div>';
    showPanel($('modelViewPanel'));
  };

  const addPos = (x={}) => {
    const tr=document.createElement('tr'); tr.dataset.id=x.id||'';
    tr.innerHTML='<td><input class="p-axle" type="number" min="1" value="'+(x.axle_number||'')+'"></td><td><select class="p-side"><option value="right">يمين</option><option value="left">يسار</option></select></td><td><select class="p-type"><option value="single">مفرد</option><option value="inner">داخلي</option><option value="outer">خارجي</option></select></td><td><input class="p-desc" value="'+String(x.description||'').replace(/"/g,'&quot;')+'"></td><td><button type="button" class="btn danger" data-remove-pos>×</button></td>';
    if(x.side)tr.querySelector('.p-side').value=x.side; if(x.position_type||x.type)tr.querySelector('.p-type').value=x.position_type||x.type;
    tr.querySelector('[data-remove-pos]').onclick=()=>{tr.remove();sync();}; tr.querySelectorAll('input,select').forEach(e=>e.addEventListener('input',sync));
    $('positionsBody')?.appendChild(tr);
  };
  const addSize = v => { const tr=document.createElement('tr'); tr.innerHTML='<td><input class="s-size" value="'+String(typeof v==='string'?v:v?.size||'').replace(/"/g,'&quot;')+'"></td><td><button type="button" class="btn danger" data-remove-size>×</button></td>'; tr.querySelector('[data-remove-size]').onclick=()=>{tr.remove();sync();}; tr.querySelector('.s-size').addEventListener('input',sync); $('sizesBody')?.appendChild(tr); };
  const sync=()=>{ const pos=[...document.querySelectorAll('#positionsBody tr')].map((tr,i)=>({id:tr.dataset.id?Number(tr.dataset.id):null,axle_number:Number(tr.querySelector('.p-axle')?.value||0),side:tr.querySelector('.p-side')?.value||'left',position_type:tr.querySelector('.p-type')?.value||'single',description:tr.querySelector('.p-desc')?.value||'',sort_order:i})); if($('positionsJson'))$('positionsJson').value=JSON.stringify(pos); if($('sizesJson'))$('sizesJson').value=JSON.stringify([...document.querySelectorAll('#sizesBody .s-size')].map(x=>x.value.trim()).filter(Boolean)); if($('specsJson'))$('specsJson').value=JSON.stringify([...document.querySelectorAll('.spec-value')].map(x=>({definition_id:Number(x.dataset.definition),value:x.value})).filter(x=>x.value!==''); };
  const renderSpecs=d=>{const box=$('specRows'); if(!box)return; box.innerHTML=''; DEFS.forEach(def=>{const v=(d.specs||[]).find(x=>Number(x.definition_id)===Number(def.id)); const row=document.createElement('label'); row.className='field'; row.innerHTML='<span>'+def.name+(def.unit?' ('+def.unit+')':'')+'</span><input class="spec-value" data-definition="'+def.id+'" value="'+String(v?.value??'').replace(/"/g,'&quot;')+'">'; row.querySelector('input').addEventListener('input',sync); box.appendChild(row);}); sync();};

  window.editModel=id=>{
    const d=DATA[String(id)]||DATA[id]||{}; currentModel=Number(id);
    if($('modelForm'))$('modelForm').action='/equipment-types/models/'+id+'/update';
    if($('modelId'))$('modelId').value=id;
    [['modelName',d.name||''],['modelCategory',d.category_id??''],['modelType',d.equipment_type_id??''],['modelBrand',d.brand_id??''],['mobility',d.mobility_type||'mobile'],['tirePositionsRequired',d.tire_positions_required??0],['axleCount',d.axle_count??''],['tireSize',d.tire_size||''],['batteryCountRequired',d.battery_count_required??0],['batteryCapacityAh',d.battery_capacity_ah??''],['batteryVoltageV',d.battery_voltage_v??'']].forEach(([id,v])=>{if($(id))$(id).value=v;});
    if($('requiresDriver'))$('requiresDriver').checked=!!d.requires_driver; if($('hasTires'))$('hasTires').checked=!!d.has_tires; if($('hasBatteries'))$('hasBatteries').checked=!!d.has_batteries;
    if($('positionsBody')){$('positionsBody').innerHTML='';(d.positions||[]).forEach(addPos);} if($('sizesBody')){$('sizesBody').innerHTML='';(d.sizes||[]).forEach(addSize);} renderSpecs(d); setTitle(d.name||'تعديل الطراز','الطراز'); showPanel($('modelPanel')); sync();
  };

  const openModelCreate=()=>openNewModel();
  const openTypeCreate=categoryId=>refPanel('type',null,'',{categoryId});
  const openNewModel=()=>{ $('modelForm')?.reset(); if($('modelId'))$('modelId').value=''; if($('positionsBody'))$('positionsBody').innerHTML=''; if($('sizesBody'))$('sizesBody').innerHTML=''; renderSpecs({}); if($('modelForm'))$('modelForm').action='/equipment-types/models/create'; currentModel=null; setTitle('إضافة طراز','الطرازات'); showPanel($('modelPanel')); };

  const refPanel=(kind,id=null,name='',extra={})=>{
    const labels={category:'الفئة',type:'نوع العتاد',brand:'العلامة التجارية',spec:'الخاصية'};
    if($('refTitle'))$('refTitle').textContent=id?'تعديل '+labels[kind]:(labels[kind]||'إضافة');
    const body=$('refBody'); if(!body)return;
    const routes={category:id?'/equipment-types/categories/'+id+'/update':'/equipment-types/categories/create',type:id?'/equipment-types/'+id+'/update':'/equipment-types/create',brand:id?'/equipment-types/brands/'+id+'/update':'/equipment-types/brands/create',spec:'/equipment-types/specs/create'};
    if(kind==='type')body.innerHTML='<form class="ref-form" method="post" action="'+routes[kind]+'"><label>الاسم<input name="name" required value="'+String(name).replace(/"/g,'&quot;')+'"></label><label>وحدة القياس<select name="unit"><option value="">بدون وحدة</option><option>كم</option><option>م</option><option>لتر</option><option>ساعة</option></select></label><label>الفئة<select name="category_id"><option value="">غير محدد</option>'+CATEGORIES.map(c=>'<option value="'+c.id+'">'+c.name+'</option>').join('')+'</select></label><button type="submit" class="btn primary">حفظ</button></form>';
    else if(kind==='spec')body.innerHTML='<form class="ref-form" method="post" action="'+routes[kind]+'"><label>الاسم<input name="name" required value="'+String(name).replace(/"/g,'&quot;')+'"></label><label>النوع<select name="data_type"><option value="text">نص</option><option value="number">رقم</option><option value="boolean">نعم/لا</option></select></label><button type="submit" class="btn primary">حفظ</button></form>';
    else body.innerHTML='<form class="ref-form" method="post" action="'+routes[kind]+'"><label>الاسم<input name="name" required value="'+String(name).replace(/"/g,'&quot;')+'"></label><button type="submit" class="btn primary">حفظ</button></form>';
    showPanel($('refPanel'));
  };

  const revealAncestors = (node) => { let group=node.closest('.tree-group'); while(group){ const parentNode=group.querySelector(':scope > .tree-node'); if(parentNode) parentNode.hidden=false; group.classList.add('open'); group=group.parentElement?.closest('.tree-group'); } };
  const syncArrows = () => tree.querySelectorAll('.tree-group > .tree-node > .tree-toggle').forEach(toggle=>toggle.textContent=toggle.closest('.tree-group')?.classList.contains('open')?'⌄':'›');
  const renderTree=()=>{
    tree.innerHTML='';
    const refs=[['brands','🏷','العلامات التجارية'],['specs','⚙','الخصائص']];
    const addGroup=(ref,icon,label)=>{const g=document.createElement('div');g.className='tree-group open';const n=document.createElement('button');n.type='button';n.className='tree-node';n.dataset.ref=ref;n.dataset.name=label;n.innerHTML='<span class="tree-toggle">⌄</span><span>'+icon+' '+label+'</span><span class="tree-actions"><span class="tree-add" data-add="'+(ref==='brands'?'brand':'spec')+'">＋</span></span>';g.appendChild(n);const ch=document.createElement('div');ch.className='children';(ref==='brands'?BRANDS:DEFS).forEach(x=>{const b=document.createElement('button');b.type='button';b.className='tree-node';b.dataset.refItem=ref==='brands'?'brand':'spec';b.dataset.id=x.id;b.dataset.name=x.name;b.textContent='• '+x.name;ch.appendChild(b);});g.appendChild(ch);tree.appendChild(g);};
    refs.forEach(x=>addGroup(...x));
    const catRoot=document.createElement('div'); catRoot.className='tree-section-title';catRoot.textContent='الشجرة الهرمية';tree.appendChild(catRoot);
    const categories=[...CATEGORIES].sort((a,b)=>String(a.name).localeCompare(String(b.name),'ar'));
    categories.forEach(cat=>{const g=document.createElement('div');g.className='tree-group open';g.dataset.categoryId=cat.id;const n=document.createElement('button');n.type='button';n.className='tree-node';n.dataset.refItem='category';n.dataset.id=cat.id;n.dataset.name=cat.name;n.innerHTML='<span class="tree-toggle">⌄</span><span>📁 '+cat.name+'</span><span class="tree-actions"><span class="tree-add" data-add="type">＋</span></span>';g.appendChild(n);const ch=document.createElement('div');ch.className='children';TYPES.filter(t=>Number(t.category_id)===Number(cat.id)).forEach(t=>appendType(ch,t));g.appendChild(ch);tree.appendChild(g);});
    const orphan=TYPES.filter(t=>t.category_id==null);if(orphan.length){const g=document.createElement('div');g.className='tree-group open';const n=document.createElement('button');n.type='button';n.className='tree-node';n.innerHTML='<span class="tree-toggle">⌄</span><span>🗂 أنواع غير مصنفة</span>';g.appendChild(n);const ch=document.createElement('div');ch.className='children';orphan.forEach(t=>appendType(ch,t));g.appendChild(ch);tree.appendChild(g);}
    const models=Object.values(DATA); if($('tree-total-count'))$('tree-total-count').textContent=models.length;
    bindTree();
  };
  const appendType=(parent,t)=>{
    const g=document.createElement('div');g.className='tree-group master-type-group open';g.dataset.typeId=t.id;
    const n=document.createElement('button');n.type='button';n.className='tree-node';n.dataset.refItem='type';n.dataset.id=t.id;n.dataset.name=t.name;n.innerHTML='<span class="tree-toggle">⌄</span><span>🗂 '+t.name+'</span><span class="tree-actions"><span class="tree-add" data-add="model" data-new-model-for-type="'+t.id+'">＋</span></span>';g.appendChild(n);
    const ch=document.createElement('div');ch.className='children';const list=Object.values(DATA).filter(m=>Number(m.equipment_type_id)===Number(t.id));list.forEach(m=>{const mg=document.createElement('div');mg.className='tree-group model-group open';const row=document.createElement('button');row.type='button';row.className='tree-node model-row';row.draggable=true;row.dataset.modelRow=m.id;row.dataset.model=m.id;row.dataset.name=m.name;row.innerHTML='<span class="tree-toggle">⌄</span><span>🚙 '+m.name+'</span>';mg.appendChild(row);const mc=document.createElement('div');mc.className='children';[['basic','📄 البيانات الأساسية'],['tires','🛞 الإطارات'],['batteries','🔋 البطاريات'],['specs','⚙ الخصائص التابعة']].forEach(([s,l])=>{const b=document.createElement('button');b.type='button';b.className='tree-node';b.dataset.model=m.id;b.dataset.section=s;b.textContent=l;mc.appendChild(b);});mg.appendChild(mc);ch.appendChild(mg);});g.appendChild(ch);parent.appendChild(g);
  };

  const bindTree=()=>{
    tree.querySelectorAll('.tree-node').forEach(n=>n.addEventListener('click',e=>{
      const add=e.target.closest('[data-add]');if(add){e.stopPropagation();const k=add.dataset.add;if(add.dataset.newModelForType){openNewModel();if($('modelType'))$('modelType').value=add.dataset.newModelForType;}else if(k==='model')openNewModel();else refPanel(k);return;}
      const toggle=e.target.closest('.tree-toggle');if(toggle){e.stopPropagation();toggle.closest('.tree-group')?.classList.toggle('open');return;}
      const model=e.currentTarget.dataset.model||e.currentTarget.dataset.modelRow;if(model){selectNode(e.currentTarget);if(e.currentTarget.dataset.section)window.viewModel(model);else window.viewModel(model);return;}
      if(e.currentTarget.dataset.refItem){selectNode(e.currentTarget);refPanel(e.currentTarget.dataset.refItem,e.currentTarget.dataset.id,e.currentTarget.dataset.name);return;}
      if(e.currentTarget.dataset.ref){selectNode(e.currentTarget);e.currentTarget.closest('.tree-group')?.classList.toggle('open');}
    }));
    tree.querySelectorAll('.model-row').forEach(row=>{row.addEventListener('dragstart',e=>{dragged=row;dragOrigin=row.closest('.model-group');row.classList.add('dragging');tree.querySelectorAll('.master-type-group').forEach(x=>x.classList.remove('drop-target'));e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',row.dataset.modelRow);$('tree-root-dropzone')?.classList.remove('hidden');});row.addEventListener('dragend',()=>{row.classList.remove('dragging');dragged=null;dragOrigin=null;$('tree-root-dropzone')?.classList.add('hidden');tree.querySelectorAll('.drop-target').forEach(x=>x.classList.remove('drop-target'));});});
    tree.querySelectorAll('.master-type-group').forEach(g=>{g.addEventListener('dragover',e=>{if(!dragged)return;e.preventDefault();g.classList.add('drop-target');});g.addEventListener('dragleave',()=>g.classList.remove('drop-target'));g.addEventListener('drop',async e=>{e.preventDefault();g.classList.remove('drop-target');if(!dragged)return;const id=dragged.dataset.modelRow,typeId=g.dataset.typeId;if(Number((DATA[String(id)]||{}).equipment_type_id)===Number(typeId))return toast('الطراز موجود بالفعل داخل هذا النوع');const oldType=(DATA[String(id)]||{}).equipment_type_id;const fd=new FormData();fd.append('equipment_type_id',typeId);try{const r=await fetch('/equipment-types/models/'+encodeURIComponent(id)+'/move',{method:'POST',body:fd,credentials:'same-origin'});if(!r.ok)throw new Error();toast('تم نقل الطراز داخل الشجرة');setTimeout(()=>location.reload(),250);}catch(_){toast('تعذر نقل الطراز');}});});
  };

  $('tree-search-input')?.addEventListener('input',e=>{const query=e.target.value.trim().toLocaleLowerCase();tree.querySelectorAll('.tree-node').forEach(node=>{node.hidden=!node.textContent.toLocaleLowerCase().includes(query);if(!query)node.hidden=false;});if(query)tree.querySelectorAll('.tree-node').forEach(node=>{if(!node.hidden)revealAncestors(node);});syncArrows();});
  $('btn-tree-expand-all')?.addEventListener('click',()=>tree.querySelectorAll('.tree-group').forEach(g=>g.classList.add('open')));
  $('btn-tree-collapse-all')?.addEventListener('click',()=>tree.querySelectorAll('.tree-group').forEach(g=>g.classList.remove('open')));
  $('btn-add-root-category')?.addEventListener('click',()=>refPanel('category'));
  $('tree-root-dropzone')?.addEventListener('dragover',e=>{if(dragged)e.preventDefault();});
  $('btn-export-tree')?.addEventListener('click',()=>{const payload={categories:CATEGORIES,types:TYPES,models:Object.values(DATA),brands:BRANDS};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));a.download='materiel-master-tree.json';a.click();URL.revokeObjectURL(a.href);});
  $('editModelBtn')?.addEventListener('click',()=>currentModel&&window.editModel(currentModel));
  $('cancelModel')?.addEventListener('click',()=>currentModel?window.viewModel(currentModel):showPanel($('empty')));
  $('addPosition')?.addEventListener('click',()=>addPos());
  $('addSize')?.addEventListener('click',()=>addSize(''));
  $('modelForm')?.addEventListener('submit',e=>{sync();if(!$('modelBrand')?.value){e.preventDefault();alert('اختر العلامة التجارية.');}});
  window.viewModel = window.viewModel || (()=>{});
  $('modelType')?.addEventListener('change',()=>{const o=$('modelType').selectedOptions[0];if(o?.dataset.category&&$('modelCategory'))$('modelCategory').value=o.dataset.category;});
  const importExcel=target=>{const input=$('excelFile');if(!input)return;input.dataset.importTarget=target;input.value='';input.click();};
  ['importPositions','importSizes','importSpecs'].forEach(id=>$(id)?.addEventListener('click',()=>importExcel(id.replace('import','').toLowerCase())));
  $('excelFile')?.addEventListener('change',async e=>{const file=e.target.files?.[0];if(!file||typeof XLSX==='undefined')return;try{const wb=XLSX.read(await file.arrayBuffer(),{type:'array'});const ws=wb.Sheets[wb.SheetNames[0]];const rows=XLSX.utils.sheet_to_json(ws,{defval:''});const keys=Object.keys(rows[0]||{});const find=names=>keys.find(k=>names.includes(String(k).trim().toLowerCase()));const target=e.target.dataset.importTarget;if(target==='positions'){const a=find(['المحور','axle','axle_number']),s=find(['الجهة','side']),t=find(['النوع','type','position_type']),d=find(['الوصف','description']);renderPositions?.(rows.map(r=>({axle_number:r[a]||1,side:r[s]||'left',position_type:r[t]||'single',description:r[d]||''})));}else if(target==='sizes'){const k=find(['المقاس','size','tire size','tire_size']);if(k)rows.forEach(r=>addSize(r[k]));}sync();toast('تم تحميل بيانات Excel إلى المحرر.');}catch(err){toast('تعذر استيراد الملف');}});
  renderTree();
})();