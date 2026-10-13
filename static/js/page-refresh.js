(function(){
  if(window.__materielPageRefreshReady)return;
  window.__materielPageRefreshReady=true;
  window.MaterielRefresh=window.MaterielRefresh||{};
  async function replaceContent(markup){
    const container=document.querySelector('.app-main > .container');
    if(!container)throw new Error('تعذر تحديث محتوى الصفحة');
    const parsed=new DOMParser().parseFromString(markup,'text/html');
    const fresh=parsed.querySelector('.app-main > .container');
    if(!fresh)throw new Error('تم الحفظ، لكن تعذر قراءة محتوى الصفحة المحدث');
    const nav=container.querySelector('.module-nav');
    container.replaceChildren(...Array.from(fresh.childNodes).map(node=>document.importNode(node,true)));
    if(nav)container.prepend(nav);
    container.querySelectorAll('script').forEach(old=>{
      const script=document.createElement('script');
      for(const attr of old.attributes)script.setAttribute(attr.name,attr.value);
      script.textContent=old.textContent;
      old.replaceWith(script);
    });
    document.dispatchEvent(new CustomEvent('materiel:page-refreshed'));
  }
  window.MaterielRefresh.currentPage=async function(){
    const response=await fetch(window.location.href,{credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'XMLHttpRequest'}});
    if(!response.ok)throw new Error('تم الحفظ، لكن تعذر تحديث البيانات المعروضة');
    await replaceContent(await response.text());
  };
  document.addEventListener('submit',event=>{
    const form=event.target;
    if(!(form instanceof HTMLFormElement)||event.defaultPrevented||form.dataset.noAjaxRefresh==='true'||form.target)return;
    const method=(form.method||'get').toUpperCase();
    if(!['POST','PUT','PATCH','DELETE'].includes(method))return;
    const submitter=event.submitter;
    const action=submitter?.formAction||form.action||window.location.href;
    const target=new URL(action,window.location.href);
    if(target.origin!==window.location.origin)return;
    event.preventDefault();
    const button=submitter instanceof HTMLButtonElement||submitter instanceof HTMLInputElement?submitter:null;
    if(button)button.disabled=true;
    (async()=>{
      try{
        const options={method,credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest','Accept':'text/html, application/json'}};
        if(method!=='GET')options.body=new FormData(form,submitter);
        const response=await fetch(target.href,options);
        if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||data.message||'تعذر حفظ التغييرات');}
        const finalUrl=new URL(response.url||target.href,window.location.href);
        if(finalUrl.origin!==window.location.origin)throw new Error('تعذر تحديث الصفحة بعد الحفظ');
        if(response.headers.get('content-type')?.includes('application/json')){
          await window.MaterielRefresh.currentPage();
        }else{
          const markup=await response.text();
          if(!markup.includes('class="app-main"')){window.location.assign(finalUrl.href);return;}
          if(finalUrl.href!==window.location.href){window.history.pushState({},'',finalUrl.href);document.title=new DOMParser().parseFromString(markup,'text/html').title||document.title;}
          await replaceContent(markup);
        }
      }catch(error){window.alert(error.message||'تعذر حفظ التغييرات أو تحديث البيانات');}
      finally{if(button?.isConnected)button.disabled=false;}
    })();
  });
})();
