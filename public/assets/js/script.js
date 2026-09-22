(()=>{
  const root=document.documentElement;
  const header=document.querySelector('.site-header');
  const btn=document.querySelector('.menu-button');
  const menu=document.querySelector('.mobile-menu');
  const themeBtn=document.querySelector('.theme-toggle');
  const themeMeta=document.querySelector('meta[name="theme-color"]');
  const media=matchMedia('(prefers-color-scheme: dark)');

  const currentTheme=()=>root.dataset.theme==='dark'?'dark':'light';
  const savedTheme=()=>{try{return localStorage.getItem('hara-theme')}catch(e){return null}};
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

  media.addEventListener?.('change',event=>{
    if(savedTheme()) return;
    root.dataset.theme=event.matches?'dark':'light';
    syncThemeUI();
  });

  const head=()=>header?.classList.toggle('scrolled',scrollY>8);
  head();
  addEventListener('scroll',head,{passive:true});

  const closeMenu=(restoreFocus=false)=>{
    btn?.setAttribute('aria-expanded','false');
    menu?.classList.remove('open');
    menu?.setAttribute('aria-hidden','true');
    if(restoreFocus) btn?.focus();
  };
  const openMenu=()=>{
    btn?.setAttribute('aria-expanded','true');
    menu?.classList.add('open');
    menu?.setAttribute('aria-hidden','false');
  };

  btn?.addEventListener('click',()=>{
    const open=btn.getAttribute('aria-expanded')==='true';
    open?closeMenu():openMenu();
  });
  menu?.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>closeMenu()));
  addEventListener('keydown',event=>{
    if(event.key==='Escape'&&btn?.getAttribute('aria-expanded')==='true') closeMenu(true);
  });
  addEventListener('resize',()=>{
    if(innerWidth>1100&&btn?.getAttribute('aria-expanded')==='true') closeMenu();
  },{passive:true});
  document.addEventListener('pointerdown',event=>{
    if(btn?.getAttribute('aria-expanded')!=='true') return;
    if(header?.contains(event.target)) return;
    closeMenu();
  });

  const normalizePath=(value)=>{
    const url=new URL(value,location.href);
    let path=url.pathname.replace(/^\/dev(?=\/|$)/,'')||'/';
    path=path.replace(/\/index\.html$/,'/');
    if(path.length>1&&!path.endsWith('/')) path+='/';
    return path;
  };
  const here=normalizePath(location.href);
  document.querySelectorAll('.main-nav a,.mobile-menu a,.footer-col a').forEach(link=>{
    try{
      if(new URL(link.href,location.href).origin!==location.origin) return;
      if(normalizePath(link.href)===here) link.setAttribute('aria-current','page');
    }catch(e){}
  });

  const els=document.querySelectorAll('.reveal');
  const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(reduceMotion){
    els.forEach(e=>e.classList.add('in-view'));
  }else if('IntersectionObserver'in window){
    const io=new IntersectionObserver(es=>es.forEach(e=>{
      if(e.isIntersecting){e.target.classList.add('in-view');io.unobserve(e.target)}
    }),{threshold:.1});
    els.forEach(e=>io.observe(e));
  }else els.forEach(e=>e.classList.add('in-view'));
})();
