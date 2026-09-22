(()=>{
  const root=document.documentElement;
  const header=document.querySelector('.site-header');
  const btn=document.querySelector('.menu-button');
  const menu=document.querySelector('.mobile-menu');
  const themeBtn=document.querySelector('.theme-toggle');
  const themeMeta=document.querySelector('meta[name="theme-color"]');

  const currentTheme=()=>root.dataset.theme==='dark'?'dark':'light';
  const syncThemeUI=()=>{
    const dark=currentTheme()==='dark';
    if(themeBtn){
      themeBtn.setAttribute('aria-pressed',String(dark));
      themeBtn.setAttribute('aria-label',dark?'Ativar modo claro':'Ativar modo escuro');
      themeBtn.title=dark?'Modo claro':'Modo escuro';
    }
    if(themeMeta) themeMeta.setAttribute('content',dark?'#061721':'#eef8fd');
    root.style.colorScheme=dark?'dark':'light';
  };
  syncThemeUI();

  themeBtn?.addEventListener('click',()=>{
    const next=currentTheme()==='dark'?'light':'dark';
    root.dataset.theme=next;
    try{localStorage.setItem('hara-theme',next)}catch(e){}
    syncThemeUI();
  });

  const head=()=>header?.classList.toggle('scrolled',scrollY>8);
  head();
  addEventListener('scroll',head,{passive:true});

  btn?.addEventListener('click',()=>{
    const open=btn.getAttribute('aria-expanded')==='true';
    btn.setAttribute('aria-expanded',String(!open));
    menu?.classList.toggle('open',!open);
    menu?.setAttribute('aria-hidden',String(open));
  });
  menu?.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{
    btn?.setAttribute('aria-expanded','false');
    menu.classList.remove('open');
    menu.setAttribute('aria-hidden','true');
  }));

  const els=document.querySelectorAll('.reveal');
  if('IntersectionObserver'in window){
    const io=new IntersectionObserver(es=>es.forEach(e=>{
      if(e.isIntersecting){e.target.classList.add('in-view');io.unobserve(e.target)}
    }),{threshold:.1});
    els.forEach(e=>io.observe(e));
  }else els.forEach(e=>e.classList.add('in-view'));
})();