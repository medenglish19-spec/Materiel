(function(){
  window.MaterielRefresh=window.MaterielRefresh||{};
  window.MaterielRefresh.currentPage=async function(){
    const container=document.querySelector('.app-main > .container');
    if(!container)throw new Error('تعذر تحديث محتوى الصفحة');
    const response=await fetch(window.location.href,{credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'XMLHttpRequest'}});
    if(!response.ok)throw new Error('تم الحفظ، لكن تعذر تحديث البيانات المعروضة');
    const markup=await response.text(),parsed=new DOMParser().parseFromString(markup,'text/html');
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
  };
})();
