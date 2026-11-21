/* Pochettes robustes : délai d'attente, sources de secours, mémoire des liens qui marchent.
   Fonctionne sur toutes les <img> du site, y compris celles ajoutées plus tard. */
(function(){
  var PH='data:image/svg+xml;utf8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><defs><radialGradient id="g" cx="30%" cy="30%"><stop offset="0" stop-color="#2a2233"/><stop offset="1" stop-color="#12141a"/></radialGradient></defs><rect width="200" height="200" fill="url(#g)"/><text x="100" y="118" text-anchor="middle" font-size="56" fill="#4a3f5e">♫</text></svg>');
  var KEY='pochettes-secours-v1', TIMEOUT=9000, MAXCACHE=1500;
  var cache={}; try{ cache=JSON.parse(localStorage.getItem(KEY)||'{}')||{}; }catch(e){}
  // pochettes devinées (recherche Deezer) et pochettes refusées par le propriétaire
  var KEY_DEV='pochettes-devinees-v1', KEY_REF='pochettes-refusees-v1', devinees={}, refusees={};
  try{ devinees=JSON.parse(localStorage.getItem(KEY_DEV)||'{}')||{}; refusees=JSON.parse(localStorage.getItem(KEY_REF)||'{}')||{}; }catch(e){}
  function saveDR(){ try{ localStorage.setItem(KEY_DEV,JSON.stringify(devinees)); localStorage.setItem(KEY_REF,JSON.stringify(refusees)); }catch(e){} }
  // miniatures copiées dans le dépôt par le robot (data/pochettes-map.json)
  var LOCAL={};
  function saveCache(){ try{ var k=Object.keys(cache); if(k.length>MAXCACHE) k.slice(0,k.length-MAXCACHE).forEach(function(x){ delete cache[x]; }); localStorage.setItem(KEY,JSON.stringify(cache)); }catch(e){} }

  // Fond affiché pendant le chargement (au lieu d'un carré noir)
  try{ document.documentElement.style.setProperty('--cover-ph','url("'+PH+'")'); }catch(e){}

  function isRemote(s){ return /^https?:\/\//i.test(s||''); }
  // Deezer renvoie une image noire quand le groupe ou l'album n'a pas d'image (hash vide)
  function isEmptyDeezer(s){ return /dzcdn\.net\/images\/(artist|cover)\/\//i.test(s||''); }

  function altUrls(src){
    var out=[];
    var m=src.match(/^(https?:\/\/coverartarchive\.org\/release(?:-group)?\/[0-9a-f-]+\/front)(?:-(\d+))?/i);
    if(m){ if(m[2]!=='250') out.push(m[1]+'-250'); out.push(m[1]+'-500'); }
    if(/cdn-images\.dzcdn\.net/i.test(src)) out.push(src.replace('cdn-images.dzcdn.net','e-cdns-images.dzcdn.net'));
    else if(/e-cdns-images\.dzcdn\.net/i.test(src)) out.push(src.replace('e-cdns-images.dzcdn.net','cdn-images.dzcdn.net'));
    return out.filter(function(u){ return u!==src; });
  }

  function norm(s){ return (s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/\(.*?\)|\[.*?\]/g,'').replace(/[^a-z0-9]+/g,' ').trim(); }
  var cbn=0;
  function jsonp(url, ok, ko){
    var cb='__cov'+(++cbn)+'_'+Date.now(), sc=document.createElement('script'), done=false;
    var t=setTimeout(function(){ fin(); ko(); },8000);
    function fin(){ if(done) return; done=true; clearTimeout(t); try{ delete window[cb]; }catch(e){ window[cb]=undefined; } if(sc.parentNode) sc.parentNode.removeChild(sc); }
    window[cb]=function(d){ fin(); ok(d); };
    sc.onerror=function(){ fin(); ko(); };
    sc.src=url+(url.indexOf('?')<0?'?':'&')+'output=jsonp&callback='+cb;
    document.head.appendChild(sc);
  }
  // Cherche la pochette sur Deezer à partir du groupe (+ album)
  function deezerLookup(g, a, cb, orig){ var refus=(orig&&refusees[orig])||[];
    if(!g){ cb(null); return; }
    if(!a){ jsonp('https://api.deezer.com/search/artist?q='+encodeURIComponent(g)+'&limit=5', function(r){
        var best=((r&&r.data)||[]).filter(function(x){ return norm(x.name)===norm(g) && !isEmptyDeezer(x.picture_medium); })[0];
        var u0=best ? (best.picture_big||best.picture_medium) : null; cb(u0 && refus.indexOf(u0)<0 ? u0 : null); }, function(){ cb(null); }); return; }
    jsonp('https://api.deezer.com/search/album?q='+encodeURIComponent('artist:"'+g+'" album:"'+a+'"')+'&limit=10', function(r){
      var list=(r&&r.data)||[], na=norm(a), ng=norm(g);
      list=list.filter(function(x){ return refus.indexOf(x.cover_big||x.cover_medium)<0; });
      var best=list.filter(function(x){ return norm(x.artist&&x.artist.name)===ng && norm(x.title)===na; })[0]
            || list.filter(function(x){ return norm(x.artist&&x.artist.name)===ng && (norm(x.title).indexOf(na)===0 || na.indexOf(norm(x.title))===0); })[0];
      var u=best && (best.cover_big||best.cover_medium);
      cb(u && !isEmptyDeezer(u) ? u : null);
    }, function(){ cb(null); });
  }

  function info(img){
    if(!img.__cov){
      var card=img.closest('[data-g]');
      img.__cov={orig:img.getAttribute('src')||'', tries:[], lookup:false, timer:0,
        g:img.getAttribute('data-g')||(card&&card.getAttribute('data-g'))||'',
        a:img.getAttribute('data-a')||(card&&card.getAttribute('data-a'))||''};
      img.__cov.tries=altUrls(img.__cov.orig);
    }
    return img.__cov;
  }

  function success(img){
    var c=img.__cov; if(!c) return; clearTimeout(c.timer);
    var cur=img.getAttribute('src')||'';
    if(c.orig && cur!==c.orig && cur!==PH && isRemote(cur)){ cache[c.orig]=cur; saveCache(); }
    if(c.orig && devinees[c.orig]===cur) flagDevinee(img, c.orig, cur); else unflag(img);
  }
  // Mode propriétaire : une pochette devinée porte un bouton ⚠ pour la refuser
  function hostOf(img){ return img.closest('.coverwrap') || (img.id==='cardImg' ? img.parentElement : null); }
  function unflag(img){ var h=hostOf(img), f=h&&h.querySelector('.cov-flag'); if(f) f.remove(); }
  function flagDevinee(img, orig, cur){ if(!document.body.classList.contains('owner')) return; var h=hostOf(img); if(!h || h.querySelector('.cov-flag')) return;
    if(getComputedStyle(h).position==='static') h.style.position='relative';
    var b=document.createElement('button'); b.type='button'; b.className='cov-flag'; b.textContent='⚠ auto'; b.title='Pochette trouvée automatiquement (l\'originale ne répond pas). Clique si ce n\'est pas la bonne.';
    b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation();
      if(!confirm('Cette pochette a été trouvée automatiquement sur Deezer, car l\'image enregistrée ne répond pas.\n\nOK = ce n\'est PAS la bonne : la refuser (le site affichera ♫ à la place).\n\nPour mettre la bonne pochette, utilise « Corriger » sur l\'album.')) return;
      (refusees[orig]=refusees[orig]||[]).push(cur); delete devinees[orig]; delete cache[orig]; saveDR(); saveCache(); b.remove(); img.setAttribute('data-cov','ph'); img.__covOwn=PH; img.src=PH; });
    h.appendChild(b); }

  function fail(img){
    var c=info(img); clearTimeout(c.timer);
    if(c.tries.length){ setSrc(img, c.tries.shift()); return; }
    if(!c.lookup && c.g){ c.lookup=true;
      deezerLookup(c.g, c.a, function(u){ if(u && u!==c.orig){ devinees[c.orig]=u; saveDR(); setSrc(img,u); } else giveUp(img); }, c.orig); return; }
    giveUp(img);
  }
  function giveUp(img){ var c=img.__cov; if(c){ clearTimeout(c.timer); if(c.orig && cache[c.orig]){ delete cache[c.orig]; saveCache(); } } img.setAttribute('data-cov','ph'); img.__covOwn=PH; img.src=PH; }

  function setSrc(img, u){
    info(img); img.__covOwn=u; img.src=u; watch(img);
  }
  function armTimer(img){
    var c=info(img); clearTimeout(c.timer);
    c.timer=setTimeout(function(){ if(!img.isConnected) return; if(!img.complete || !img.naturalWidth){ fail(img); } }, TIMEOUT);
  }

  // Le délai ne démarre que quand l'image est (presque) visible, à cause du chargement paresseux
  var io=null;
  if('IntersectionObserver' in window){
    io=new IntersectionObserver(function(entries){ entries.forEach(function(e){ if(e.isIntersecting){ io.unobserve(e.target); var img=e.target; if(!(img.complete && img.naturalWidth)) armTimer(img); } }); }, {rootMargin:'300px'});
  }
  function watch(img){ if(io) io.observe(img); else armTimer(img); }

  function prepare(img){
    var src=img.getAttribute('src')||'';
    if(src===img.__covOwn) return;                       // changement fait par ce module
    if(img.__cov && src===img.__cov.orig) return;        // déjà suivie
    if(img.__cov){ clearTimeout(img.__cov.timer); img.__cov=null; } // nouvelle image dans le même <img>
    img.removeAttribute('data-cov'); img.__covOwn=null;
    if(!isRemote(src) || img.closest('[data-cov-off]')) return;
    var c=info(img);
    if(isEmptyDeezer(src)){ c.tries=[]; fail(img); return; }
    if(LOCAL[src]){ c.tries=[src].concat(altUrls(src)); setSrc(img, LOCAL[src]); return; }
    if(cache[src] && cache[src]!==src){ setSrc(img, cache[src]); return; }
    if(img.complete && img.naturalWidth){ return; }
    watch(img);
  }

  // Erreurs et chargements de toutes les images (phase de capture : les événements img ne remontent pas)
  document.addEventListener('error', function(e){
    var img=e.target; if(!img || img.tagName!=='IMG') return;
    var src=img.getAttribute('src')||''; if((!isRemote(src) && !(img.__cov && src===img.__covOwn && src!==PH)) || img.closest('[data-cov-off]')) return;
    if(!img.__cov || (src!==img.__cov.orig && src!==img.__covOwn)){ prepare(img); if((img.getAttribute('src')||'')!==src) return; }
    e.stopImmediatePropagation(); img.onerror=null; // on remplace l'ancien repli direct vers le visuel générique
    fail(img);
  }, true);
  document.addEventListener('load', function(e){
    var img=e.target; if(!img || img.tagName!=='IMG' || !img.__cov || img.getAttribute('src')===PH) return;
    if(img.naturalWidth<=2){ fail(img); return; }   // image vide ou pixel de suivi
    success(img);
  }, true);

  function scan(root){ if(!root || !root.querySelectorAll) return; if(root.tagName==='IMG') prepare(root); else Array.prototype.forEach.call(root.querySelectorAll('img'), prepare); }
  var mo=new MutationObserver(function(muts){ muts.forEach(function(m){
    if(m.type==='attributes'){ if(m.target.tagName==='IMG') prepare(m.target); return; }
    Array.prototype.forEach.call(m.addedNodes, function(n){ if(n.nodeType===1) scan(n); });
  }); });
  function chargerLocal(){ try{ var x=new XMLHttpRequest(); x.open('GET','data/pochettes-map.json?_='+Math.floor(Date.now()/36e5)); x.onload=function(){ try{ LOCAL=(JSON.parse(x.responseText).ok)||{}; }catch(e){ LOCAL={}; }
      Array.prototype.forEach.call(document.querySelectorAll('img'),function(img){ var c=img.__cov, o=c?c.orig:(img.getAttribute('src')||''); if(!LOCAL[o] || img.closest('[data-cov-off]')) return; if(!c){ prepare(img); return; } if(img.getAttribute('src')===LOCAL[o]) return; c.tries=[o].concat(altUrls(o)); setSrc(img, LOCAL[o]); unflag(img); }); }; x.send(); }catch(e){} }
  function start(){ chargerLocal(); scan(document.body); mo.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['src']}); }
  if(document.body) start(); else document.addEventListener('DOMContentLoaded', start);

  window.Covers={PH:PH, clearCache:function(){ cache={}; saveCache(); devinees={}; refusees={}; saveDR(); }};
})();
