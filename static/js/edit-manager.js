/* Materiel Global Edit Manager: reliable DOM + registered JS state undo/redo/save. */
(function(global){
'use strict';
if(global.EditManager)return;

const MAX=100, DEBOUNCE=400, providers=new Map(), history=[], future=[], listeners=new Set();
let savedBaseline=null, lastSnapshot=null, restoring=false, saving=false, timer=null, saveHandler=null, initialized=false, sequence=Promise.resolve();

const clone=v=>codec.decode(codec.encode(v));
const stable=v=>JSON.stringify(codec.encode(v));
const equal=(a,b)=>stable(a)===stable(b);

const codec={
  encode(v,seen=new WeakSet()){
    if(v===undefined)return{__em_type:'undefined'};
    if(v===null||typeof v!=='object')return v;
    if(v instanceof Date)return{__em_type:'Date',value:v.toISOString()};
    if(v instanceof Set)return{__em_type:'Set',value:[...v].map(x=>codec.encode(x,seen))};
    if(v instanceof Map)return{__em_type:'Map',value:[...v].map(([k,x])=>[codec.encode(k,seen),codec.encode(x,seen)])};
    if(seen.has(v))throw new TypeError('EditManager cannot encode circular state');
    seen.add(v);
    if(Array.isArray(v))return v.map(x=>codec.encode(x,seen));
    const o={};Object.keys(v).forEach(k=>o[k]=codec.encode(v[k],seen));return o;
  },
  decode(v){
    if(Array.isArray(v))return v.map(codec.decode);
    if(!v||typeof v!=='object')return v;
    if(v.__em_type==='undefined')return undefined;
    if(v.__em_type==='Date')return new Date(v.value);
    if(v.__em_type==='Set')return new Set(v.value.map(codec.decode));
    if(v.__em_type==='Map')return new Map(v.value.map(([k,x])=>[codec.decode(k),codec.decode(x)]));
    const o={};Object.keys(v).forEach(k=>o[k]=codec.decode(v[k]));return o;
  }
};

function toast(message,kind='info'){
  if(!document.body)return;
  let box=document.getElementById('emToast');
  if(!box){
    box=document.createElement('div');box.id='emToast';box.setAttribute('role','status');
    box.style.cssText='position:fixed;right:18px;bottom:18px;z-index:10000;display:none;max-width:min(420px,calc(100vw - 36px));padding:11px 14px;border:1px solid #d8dee8;border-radius:10px;background:#fff;box-shadow:0 8px 28px rgba(15,23,42,.16);font-size:12px;font-weight:700;color:#26364a';
    document.body.appendChild(box);
  }
  box.textContent=message;box.dataset.kind=kind;box.style.display='';clearTimeout(box._timer);box._timer=setTimeout(()=>box.style.display='none',3500);
}

function ignored(el){
  if(!el||el.closest('[data-em-ignore],.app-workbar'))return true;
  if(el.matches('input[type="hidden"],input[type="password"],input[type="file"],input[type="button"],input[type="submit"],button'))return true;
  const hint=`${el.name||''} ${el.id||''} ${el.getAttribute('aria-label')||''} ${el.placeholder||''}`.toLowerCase();
  return !el.hasAttribute('data-em-track') && /(^|[-_ ])(search|filter|query|بحث|تصفية)([-_ ]|$)/i.test(hint);
}
function fields(){
  const roots=[...document.querySelectorAll('[data-em-root]')];
  const scope=roots.length?roots.flatMap(r=>[...r.querySelectorAll('input,select,textarea,[contenteditable="true"]')]):[...document.querySelectorAll('input,select,textarea,[contenteditable="true"]')];
  return scope.filter(el=>!ignored(el)&&(el.closest('form')||el.hasAttribute('data-em-track')));
}
function key(el,i){
  if(el.dataset.emTrack)return`track:${el.dataset.emTrack}`;
  const f=el.closest('form'),base=f?`form:${f.id||f.getAttribute('action')||i}`:`page:${i}`;
  return el.type==='radio'?`${base}:radio:${el.name||el.id||i}`:`${base}:${el.name||el.id||`${el.tagName.toLowerCase()}-${i}`}`;
}
function captureDom(){
  const out={};
  fields().forEach((el,i)=>{
    const k=key(el,i);
    if(el.type==='radio')out[k]=[...document.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name||'')}"]`)].map(x=>x.checked);
    else if(el.matches('[contenteditable="true"]'))out[k]={type:'contenteditable',value:el.innerHTML};
    else if(el.tagName==='SELECT'&&el.multiple)out[k]={type:'select-multiple',value:[...el.options].map(o=>o.selected)};
    else if(el.type==='checkbox')out[k]={type:'checkbox',value:el.checked};
    else out[k]={type:'value',value:el.value};
  });
  return out;
}
function findField(k){
  const fs=fields();for(let i=0;i<fs.length;i++)if(key(fs[i],i)===k)return fs[i];return null;
}
async function restoreDom(state){
  restoring=true;
  try{
    for(let pass=0;pass<3;pass++){
      Object.entries(state||{}).forEach(([k,d])=>{
        const el=findField(k);if(!el)return;
        if(el.type==='radio'){
          const g=[...document.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name||'')}"]`)];
          (d||[]).forEach((v,i)=>{if(g[i])g[i].checked=!!v});
        }else if(d?.type==='contenteditable')el.innerHTML=d.value;
        else if(d?.type==='checkbox')el.checked=!!d.value;
        else if(d?.type==='select-multiple')el.options.forEach((o,i)=>o.selected=!!d.value?.[i]);
        else el.value=d?.value??'';
        el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
      });
      if(pass<2)await new Promise(r=>setTimeout(r,50));
    }
  }finally{restoring=false}
}
providers.set('dom',{name:'dom',capture:captureDom,restore:restoreDom,label:'حقول الصفحة'});

function captureAll(){const s={};providers.forEach((p,n)=>s[n]=clone(p.capture()));return s}
function diff(a,b){
  const d={};providers.forEach((p,n)=>{if(!(p.equals||equal)(a?.[n],b?.[n]))d[n]={before:clone(a?.[n]),after:clone(b?.[n])}});return d;
}
function empty(d){return !Object.keys(d).length}
function state(){
  const live=captureAll();
  return {dirty:!!savedBaseline&&!empty(diff(savedBaseline,live)),canUndo:history.length>0,canRedo:future.length>0,saving,labels:{undo:history.at(-1)?.label||'',redo:future.at(-1)?.label||''}};
}
function emit(){const s=state();if(!document.body)return;document.dispatchEvent(new CustomEvent('edit-manager:change',{detail:s}));listeners.forEach(fn=>{try{fn(s)}catch(_){}});updateUI(s)}
function push(before,after,label,command){
  const d=diff(before,after);if(empty(d)&&!command)return false;
  history.push({label:label||'تعديل',diff:d,command});if(history.length>MAX)history.shift();future.length=0;emit();return true;
}
function commit(label='تعديل'){
  if(restoring)return false;
  const before=lastSnapshot||captureAll(),after=captureAll();lastSnapshot=clone(after);
  return push(before,after,label);
}
function schedule(label){clearTimeout(timer);timer=setTimeout(()=>commit(label),DEBOUNCE)}
async function apply(d,which){
  for(const[name,change] of Object.entries(d||{})){const p=providers.get(name);if(p)await p.restore(clone(which==='before'?change.before:change.after))}
}
async function undo(){
  if(!history.length)return false;
  const step=history.pop();
  try{if(step.command)await step.command.undo();else await apply(step.diff,'before');lastSnapshot=clone(captureAll());future.push(step);emit();return true}
  catch(e){history.push(step);toast(`تعذر التراجع: ${e.message||e}`,'danger');emit();return false}
}
async function redo(){
  if(!future.length)return false;
  const step=future.pop();
  try{if(step.command)await(step.command.redo?step.command.redo():step.command.do());else await apply(step.diff,'after');lastSnapshot=clone(captureAll());history.push(step);emit();return true}
  catch(e){future.push(step);toast(`تعذر الإعادة: ${e.message||e}`,'danger');emit();return false}
}
function markSaved(names){
  const live=captureAll();
  if(!savedBaseline)savedBaseline={};
  if(names==null)savedBaseline=clone(live);
  else (Array.isArray(names)?names:[names]).forEach(n=>savedBaseline[n]=clone(live[n]));
  emit();return true;
}
function markSavedForm(form){
  const live=captureDom(),base=savedBaseline?.dom||{};
  const next=clone(base);
  Object.keys(live).forEach(k=>{const f=findField(k)?.closest('form');if(f===form)next[k]=clone(live[k])});
  Object.keys(next).forEach(k=>{if(!findField(k))delete next[k]});
  if(!savedBaseline)savedBaseline={};savedBaseline.dom=next;emit();
}
function register(name,spec){
  if(!name||!spec||typeof spec.capture!=='function'||typeof spec.restore!=='function')throw new TypeError('EditManager.register requires capture and restore');
  providers.set(name,{name,capture:spec.capture,restore:spec.restore,save:spec.save,equals:spec.equals||equal,label:spec.label||name});
  if(savedBaseline)savedBaseline[name]=clone(spec.capture());
  lastSnapshot=clone(captureAll());emit();
  return()=>{providers.delete(name);if(savedBaseline)delete savedBaseline[name];lastSnapshot=clone(captureAll());emit()};
}
function setSaveHandler(fn){saveHandler=typeof fn==='function'?fn:null}
function modifiedProviders(){
  const live=captureAll();
  return [...providers.entries()].filter(([n,p])=>n!=='dom'&&!equal(savedBaseline?.[n],live[n]));
}
function dirtyForms(){
  const live=captureDom(),base=savedBaseline?.dom||{},keys=new Set([...Object.keys(live),...Object.keys(base)]),forms=new Set();
  keys.forEach(k=>{if(!equal(live[k],base[k])){const f=findField(k)?.closest('form');if(f)forms.add(f)}});return[...forms];
}
function installFetchBridge(){
  if(typeof global.fetch!=='function'||global.fetch.__materielEditManagerFetchWrapped)return;
  const original=global.fetch;
  function wrapped(input,init){
    const method=(init?.method||(input instanceof Request?input.method:'GET')).toUpperCase();
    const ctx=submitContext;
    const result=original(input,init);
    if(ctx&&ctx.promises.length===0&&!['GET','HEAD','OPTIONS'].includes(method)&&Date.now()-ctx.at<1500){
      ctx.promises.push(Promise.resolve(result).then(async res=>{
        if(!res.ok)throw new Error('رفض الخادم عملية الحفظ.');
        const type=res.headers?.get('content-type')||'';
        if(type.includes('application/json')){
          const data=await res.clone().json();
          if(data?.ok===false)throw new Error(data.error||data.detail||'رفض الخادم عملية الحفظ.');
        }
        return res;
      }));
    }
    return result;
  }
  wrapped.__materielEditManagerFetchWrapped=true;global.fetch=wrapped;
}
let submitContext=null;
function installSubmitBridge(){
  document.addEventListener('submit',e=>{
    const f=e.target;if(f instanceof HTMLFormElement)submitContext={form:f,at:Date.now(),promises:[]};
  },true);
}
async function save(){
  if(saving)return false;if(!state().dirty)return true;
  saving=true;emit();
  try{
    if(saveHandler){const r=await saveHandler();if(r===false)throw new Error('فشل الحفظ في الصفحة الحالية.');markSaved();return true}
    const mods=modifiedProviders();
    for(const[name,p]of mods){
      if(typeof p.save!=='function')throw new Error(`لا يوجد معالج حفظ للمزوّد: ${p.label||name}`);
      const r=await p.save(p.capture());if(r===false)throw new Error(`فشل حفظ ${p.label||name}`);
      markSaved(name);
    }
    if(!state().dirty)return true;
    const forms=dirtyForms();
    if(!forms.length){markSaved();return true}
    if(forms.length>1)throw new Error(`التعديلات غير المحفوظة موجودة في أكثر من نموذج: ${forms.map(f=>f.id||f.getAttribute('action')||'نموذج').join('، ')}`);
    const form=forms[0];
    if(!form.checkValidity()){form.reportValidity();throw new Error(`بيانات نموذج ${form.id||form.getAttribute('action')||''} غير صالحة.`)}
    submitContext={form,at:Date.now(),promises:[]};
    form.requestSubmit();
    const ctx=submitContext;
    if(ctx.promises.length){await Promise.all(ctx.promises);markSavedForm(form);return true}
    if((form.getAttribute('method')||'get').toLowerCase()==='post'&&!form.target){markSavedForm(form);return true}
    throw new Error('لم يتم رصد طلب حفظ من النموذج.');
  }catch(e){toast(e.message||'تعذر الحفظ.','danger');return false}
  finally{saving=false;emit()}
}
function updateUI(s){
  const u=document.querySelector('[data-em-action="undo"]'),r=document.querySelector('[data-em-action="redo"]'),b=document.querySelector('[data-em-action="save"]'),st=document.getElementById('emStatus');
  if(u){u.disabled=!s.canUndo;u.title=s.canUndo?`تراجع: ${s.labels.undo}`:'تراجع'}
  if(r){r.disabled=!s.canRedo;r.title=s.canRedo?`إعادة: ${s.labels.redo}`:'إعادة'}
  if(b){b.disabled=!s.dirty||s.saving;b.classList.toggle('has-work',s.dirty);b.title=s.saving?'جارٍ الحفظ...':'حفظ'}
  if(st){st.dataset.state=s.saving?'saving':s.dirty?'dirty':'clean';st.textContent=s.saving?'جارٍ الحفظ...':s.dirty?'تغييرات غير محفوظة':'نظيف'}
}
function initialize(){
  if(initialized)return;initialized=true;
  savedBaseline=clone(captureAll());lastSnapshot=clone(savedBaseline);emit();
  document.addEventListener('input',e=>{if(!restoring&&!ignored(e.target))schedule('تعديل حقل')});
  document.addEventListener('change',e=>{if(!restoring&&!ignored(e.target))schedule('تغيير حقل')});
  document.addEventListener('click',e=>{const b=e.target.closest('[data-em-action]');if(!b)return;e.preventDefault();const a=b.dataset.emAction;if(a==='undo')undo();else if(a==='redo')redo();else if(a==='save')save()});
  document.addEventListener('keydown',e=>{
    if(e.key==='s'&&(e.ctrlKey||e.metaKey)){e.preventDefault();save();return}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){if(history.length){e.preventDefault();undo()}return}
    if((e.ctrlKey||e.metaKey)&&(e.key.toLowerCase()==='y'||(e.shiftKey&&e.key.toLowerCase()==='z'))){if(future.length){e.preventDefault();redo()}}
  });
  global.addEventListener('beforeunload',e=>{if(state().dirty){e.preventDefault();e.returnValue='لديك تغييرات غير محفوظة.'}});
}
installFetchBridge();installSubmitBridge();
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initialize,{once:true});else initialize();
global.EditManager={register,commit,execute:async o=>{
  if(!o||typeof o.do!=='function'||typeof o.undo!=='function')throw new TypeError('execute requires do and undo');
  const run=async()=>{const before=captureAll();const result=await o.do();const after=captureAll();push(before,after,o.label||'عملية',o);lastSnapshot=clone(after);return result};
  const result=sequence.then(run,run);sequence=result.catch(()=>{});return result;
},undo,redo,save,markSaved,rebase:markSaved,reset:()=>{history.length=0;future.length=0;markSaved();lastSnapshot=clone(captureAll())},snapshot:()=>clone(captureAll()),restore:async snap=>{restoring=true;try{await apply(diff(captureAll(),snap),'after');lastSnapshot=clone(captureAll());emit()}finally{restoring=false}},isDirty:()=>state().dirty,subscribe:fn=>(listeners.add(fn),fn(state()),()=>listeners.delete(fn)),setSaveHandler,codec};
})(window);
