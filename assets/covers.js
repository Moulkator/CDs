/* Pochettes robustes : délai d'attente, sources de secours, mémoire des liens qui marchent.
   Fonctionne sur toutes les <img> du site, y compris celles ajoutées plus tard. */
(function(){
  var PH='data:image/svg+xml;utf8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><defs><radialGradient id="g" cx="30%" cy="30%"><stop offset="0" stop-color="#2a2233"/><stop offset="1" stop-color="#12141a"/></radialGradient></defs><rect width="200" height="200" fill="url(#g)"/><text x="100" y="118" text-anchor="middle" font-size="56" fill="#4a3f5e">♫</text></svg>');
  var KEY='pochettes-secours-v1', TIMEOUT=9000, MAXCACHE=1500;
  var cache={}; try{ cache=JSON.parse(localStorage.getItem(KEY)||'{}')||{}; }catch(e){}
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
  function deezerLookup(g, a, cb){
    if(!g){ cb(null); return; }
    if(!a){ jsonp('https://api.deezer.com/search/artist?q='+encodeURIComponent(g)+'&limit=5', function(r){
        var best=((r&&r.data)||[]).filter(function(x){ return norm(x.name)===norm(g) && !isEmptyDeezer(x.picture_medium); })[0];
        cb(best ? (best.picture_big||best.picture_medium) : null); }, function(){ cb(null); }); return; }
    jsonp('https://api.deezer.com/search/album?q='+encodeURIComponent('artist:"'+g+'" album:"'+a+'"')+'&limit=10', function(r){
      var list=(r&&r.data)||[], na=norm(a), ng=norm(g);
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
  }

  function fail(img){
    var c=info(img); clearTimeout(c.timer);
    if(c.tries.length){ setSrc(img, c.tries.shift()); return; }
    if(!c.lookup && c.g){ c.lookup=true;
      deezerLookup(c.g, c.a, function(u){ if(u && u!==c.orig){ setSrc(img,u); } else giveUp(img); }); return; }
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
    if(cache[src] && cache[src]!==src){ setSrc(img, cache[src]); return; }
    if(img.complete && img.naturalWidth){ return; }
    watch(img);
  }

  // Erreurs et chargements de toutes les images (phase de capture : les événements img ne remontent pas)
  document.addEventListener('error', function(e){
    var img=e.target; if(!img || img.tagName!=='IMG') return;
    var src=img.getAttribute('src')||''; if(!isRemote(src) || img.closest('[data-cov-off]')) return;
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
  function start(){ scan(document.body); mo.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['src']}); }
  if(document.body) start(); else document.addEventListener('DOMContentLoaded', start);

  window.Covers={PH:PH, clearCache:function(){ cache={}; saveCache(); }};
})();
