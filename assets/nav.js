/* Barre de navigation commune + mode propriétaire (jeton GitHub, stocké dans ce navigateur). */
(function(){
  var KEY_TOKEN='gh-token-v1', KEY_REPO='gh-repo-v1';
  var PAGES=[
    {id:'wishlist',   label:'Liste de souhaits',   href:'index.html#wishlist'},
    {id:'collection', label:'Collection',          href:'index.html#collection'},
    {id:'sorties',    label:'Sorties à surveiller',href:'sorties.html#sorties'},
    {id:'decouvrir',  label:'À découvrir',         href:'sorties.html#decouvrir'},
    {id:'recherche',  label:'Rechercher',          href:'sorties.html#recherche'},
    {id:'aleatoire',  label:'Album aléatoire',     href:'sorties.html#aleatoire'}
  ];
  function ls(k,def){ try{ var v=localStorage.getItem(k); return v?JSON.parse(v):def; }catch(e){ return def; } }
  function detectRepo(){ var m=location.hostname.match(/^([^.]+)\.github\.io$/); var seg=location.pathname.split('/').filter(Boolean); if(m&&seg.length&&seg[0].indexOf('.')<0) return {owner:m[1],repo:seg[0]}; return null; }
  var Owner={
    isOn:function(){ return !!(ls(KEY_TOKEN,'') && (ls(KEY_REPO,null)||detectRepo())); },
    token:function(){ return ls(KEY_TOKEN,''); },
    repo:function(){ return ls(KEY_REPO,null)||detectRepo(); },
    activate:function(){
      var repo=Owner.repo();
      if(!repo){ var r=prompt('Dépôt GitHub (ex : Moulkator/CDs) :',''); if(!r||r.indexOf('/')<0) return; repo={owner:r.split('/')[0].trim(),repo:r.split('/')[1].trim()}; }
      var t=prompt('Colle ton jeton GitHub (fine-grained token, droit Contents : écriture sur ce dépôt).\nIl reste uniquement dans ce navigateur.','');
      if(!t) return; t=t.trim();
      var x=new XMLHttpRequest(); x.open('GET','https://api.github.com/repos/'+repo.owner+'/'+repo.repo+'/contents/data/watchlist-manuel.json?ref=main&_='+Date.now());
      x.setRequestHeader('Authorization','Bearer '+t); x.setRequestHeader('Accept','application/vnd.github+json');
      x.onload=function(){ if(x.status>=200&&x.status<300){ localStorage.setItem(KEY_TOKEN,JSON.stringify(t)); localStorage.setItem(KEY_REPO,JSON.stringify(repo)); render(); fire(true); }
        else alert(x.status===401?'Jeton refusé : vérifie qu\'il est valide (401).':x.status===403?'Jeton sans droit d\'écriture sur ce dépôt (403).':x.status===404?'Dépôt introuvable : '+repo.owner+'/'+repo.repo:'Échec ('+x.status+').'); };
      x.onerror=function(){ alert('Impossible de joindre GitHub.'); };
      x.send();
    },
    deactivate:function(){ if(!confirm('Désactiver le mode propriétaire sur cet appareil ? (le jeton sera oublié ici)')) return; localStorage.removeItem(KEY_TOKEN); render(); fire(false); }
  };
  function fire(on){ try{ document.dispatchEvent(new CustomEvent('owner-changed',{detail:{owner:on}})); }catch(e){} }
  function currentPage(){ var f=location.pathname.split('/').pop()||'index.html', hsh=(location.hash||'').replace('#',''); if(f==='sorties.html') return (hsh==='decouvrir'||hsh==='ecouter')?'decouvrir':hsh==='recherche'?'recherche':hsh==='aleatoire'?'aleatoire':'sorties'; return hsh==='collection'?'collection':'wishlist'; }
  function render(){
    var nav=document.getElementById('topnav'); if(!nav) return;
    var cur=currentPage(), on=Owner.isOn();
    nav.innerHTML='<a class="brand" href="index.html#wishlist">♫ MES CD</a><div class="navlinks">'+PAGES.map(function(p){ return '<a href="'+p.href+'" data-page="'+p.id+'" class="'+(p.id===cur?'active':'')+'">'+p.label+'</a>'; }).join('')+'</div>'+
      '<button type="button" class="owner '+(on?'on':'')+'" title="'+(on?'Mode propriétaire actif sur cet appareil — cliquer pour désactiver':'Activer le mode propriétaire (jeton GitHub)')+'"><span class="ico">'+(on?'🔓':'🔑')+'</span><span class="lbl"> '+(on?'Propriétaire':'Mode propriétaire')+'</span></button>';
    nav.querySelector('.owner').addEventListener('click',function(){ on?Owner.deactivate():Owner.activate(); });
    document.body.classList.toggle('owner',on);
    setNavHeight();
    var act=nav.querySelector('.navlinks a.active'); if(act&&act.scrollIntoView){ try{ act.scrollIntoView({inline:'center',block:'nearest'}); }catch(e){} }
  }
  function setNavHeight(){ var nav=document.getElementById('topnav'); if(nav) document.documentElement.style.setProperty('--nav-h', nav.offsetHeight+'px'); }
  window.addEventListener('resize',setNavHeight);
  window.OwnerMode=Owner; window.renderTopNav=render;
  window.addEventListener('hashchange',render);
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',render); else render();
})();
