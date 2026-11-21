/* Boutons d'action sur la pochette (survol à la souris, toucher sur téléphone) + options repliées.
   Les boutons d'origine restent dans la carte (cachés) : on les déclenche, toute la logique existante est conservée. */
(function(){
  var COVERS = '#listGrid .cell .coverwrap, #gridSorties .card .coverwrap, #gridDecouvrir .card .coverwrap, #gridEcoute .card .coverwrap, #gridRecherche .card .coverwrap';
  var GRIDS = ['gridSorties','gridDecouvrir','gridEcoute','gridRecherche'];
  var FOLD = '.prev,.status,.ecoute,.links,.acts';
  var survol = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  function owner(){ return document.body.classList.contains('owner'); }
  function enEdition(){ return document.body.classList.contains('editing-mode'); }

  // Liste des actions proposées sur la pochette, selon le type de carte et l'état de l'album
  function actions(card){
    var q=function(s){ return card.querySelector(s); }, L=[];
    // YouTube : en mode invité, seulement si la playlist de l'album est déjà enregistrée (la recherche demande une clé)
    var yt=q('[data-act=yt]'), ga=groupeAlbum(card);
    if(yt && !yt.classList.contains('on') && (owner() || (window.YTA && ga && YTA.known(ga[0],ga[1])))) L.push(['▶ YouTube','yt',yt]);
    if(!owner()) return L;
    if(card.classList.contains('cell')){                       // liste de souhaits / collection (vue complète)
      if(document.body.classList.contains('collection-mode')) return L;
      var recuL=q('.cmd-recu'), addL=q('.cmd-add');
      if(recuL) L.push(['📦 Reçu → Collection','recu',recuL]); else if(addL) L.push(['🛒 Commandé','cmd',addL]);
      L.push(['📀 Possédé','coll',function(){ window.ListesAPI && window.ListesAPI.posseder(card); }]);
      return L;
    }
    var w=q('[data-act=wish]'), uw=q('[data-act=unwish]');
    if(w) L.push(['🎁 Liste de souhaits','wish',w]); else if(uw) L.push(['✓ Dans la liste de souhaits','wish on',uw]);
    var recu=q('[data-act=cmdrecu]'), ann=q('[data-act=cmdannul]');
    if(recu){ L.push(['📦 Reçu → Collection','recu',recu]); if(ann) L.push(['✕ Commande annulée','annul',ann]); return L; }
    var cm=q('[data-act=cmd]'); if(cm) L.push(['🛒 Commandé','cmd',cm]);
    var co=q('[data-act=coll]'), uc=q('[data-act=uncoll]');
    if(co) L.push(['📀 Possédé','coll',co]); else if(uc) L.push(['✓ Possédé','coll on',uc]);
    return L;
  }

  function groupeAlbum(card){ var img=card.querySelector('.coverwrap img[data-g]'); if(img) return [img.getAttribute('data-g'), img.getAttribute('data-a')||''];
    var g=card.querySelector('.g, .artistname'), a=card.querySelector('.a, .cap b'); return g&&a ? [g.textContent.trim(), a.textContent.trim()] : null; }
  function cacher(cw){ var b=cw.querySelector('.ov-box'); if(b) b.remove(); cw.classList.remove('ov-on'); }
  function cacherTout(sauf){ Array.prototype.forEach.call(document.querySelectorAll('.coverwrap.ov-on'),function(c){ if(c!==sauf) cacher(c); }); }
  function montrer(cw){
    if(enEdition() || cw.querySelector('iframe') || cw.querySelector('.ov-box')) return false;
    var card=cw.closest('.card, .cell'); if(!card) return false;
    var L=actions(card); if(!L.length) return false;
    var box=document.createElement('div'); box.className='ov-box';
    L.forEach(function(a){ var b=document.createElement('button'); b.type='button'; b.className='ov-b '+a[1].split(' ').map(function(x){ return 'ov-'+x; }).join(' '); b.textContent=a[0];
      b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); cacher(cw); if(typeof a[2]==='function') a[2](); else a[2].click(); });
      box.appendChild(b); });
    cw.appendChild(box); cw.classList.add('ov-on'); return true;
  }

  if(survol){
    document.addEventListener('mouseover',function(e){ var cw=e.target.closest && e.target.closest(COVERS); if(cw) montrer(cw); });
    document.addEventListener('mouseout',function(e){ var cw=e.target.closest && e.target.closest(COVERS); if(!cw) return; if(e.relatedTarget && cw.contains(e.relatedTarget)) return; cacher(cw); });
  } else {
    // écran tactile : un toucher sur la pochette ouvre / ferme les boutons (sans ouvrir l'album)
    document.addEventListener('click',function(e){
      if(!e.target.closest || e.target.closest('.ov-box')) return;
      var cw=e.target.closest(COVERS); cacherTout(cw);
      if(!cw || enEdition() || cw.querySelector('iframe')) return;
      if(cw.classList.contains('ov-on')){ cacher(cw); e.stopPropagation(); e.preventDefault(); return; }
      if(montrer(cw)){ e.stopPropagation(); e.preventDefault(); }
    }, true);
  }

  // Pendant qu'une vidéo joue dans la pochette : barre d'actions juste dessous (Fermer + les boutons de la pochette)
  var LISTES = '#listGrid, #gridSorties, #gridDecouvrir, #gridEcoute, #gridRecherche';
  function barre(card){
    var cw=card.querySelector('.coverwrap'), joue=cw && cw.querySelector('iframe'), old=card.querySelector('.ov-bar');
    if(!joue){ if(old) old.remove(); return; }
    var bar=document.createElement('div'); bar.className='ov-bar';
    var stop=card.querySelector('.ytbtn.on');
    var L=(stop?[['⏹ Fermer YouTube','stop',stop]]:[]).concat(actions(card));
    var ex=card.querySelector('.ytextra'), ouv=ex&&ex.querySelector('a.ytopen'), mv=ex&&ex.querySelector('[data-act=ytbad]'), li=ex&&ex.querySelector('[data-act=ytlink]');
    if(ouv) L.push(['↗ Ouvrir dans YouTube','ext',function(){ window.open(ouv.href,'_blank','noopener'); }]);
    if(owner()){ if(mv) L.push(['✗ Mauvaise version','ext',mv]); if(li) L.push(['🔗 Autre lien','ext',li]); }
    L.forEach(function(a){ var b=document.createElement('button'); b.type='button'; b.className='ov-b ov-mini '+a[1].split(' ').map(function(x){ return 'ov-'+x; }).join(' '); b.textContent=a[0];
      b.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); if(typeof a[2]==='function') a[2](); else a[2].click(); setTimeout(function(){ if(card.isConnected) barre(card); },60); });
      bar.appendChild(b); });
    if(old) old.replaceWith(bar); else cw.insertAdjacentElement('afterend', bar);
  }
  function suivreLectures(){
    Array.prototype.forEach.call(document.querySelectorAll(LISTES),function(g){
      new MutationObserver(function(muts){ var vues=[];
        muts.forEach(function(m){ var cw=m.target.closest && m.target.closest('.coverwrap'); if(!cw) return; var card=cw.closest('.card, .cell'); if(card && vues.indexOf(card)<0) vues.push(card); });
        vues.forEach(barre);
      }).observe(g,{childList:true,subtree:true});
    });
  }

  // Options repliées : bouton « ⋯ Plus » sous chaque carte
  function ajouterPli(card){
    if(card.querySelector(':scope > .fold-btn')) return;
    if(!card.querySelector(':scope > :is('+FOLD+')')) return;
    var b=document.createElement('button'); b.type='button'; b.className='fold-btn'; b.textContent='⋯ Plus';
    b.addEventListener('click',function(e){ e.stopPropagation(); var on=card.classList.toggle('unfold'); b.textContent=on?'▴ Moins':'⋯ Plus'; });
    card.appendChild(b);
  }
  function scanGrille(g){ Array.prototype.forEach.call(g.querySelectorAll(':scope > .card'), ajouterPli); }
  function demarrer(){ suivreLectures();
    GRIDS.forEach(function(id){ var g=document.getElementById(id); if(!g) return; scanGrille(g);
      new MutationObserver(function(){ scanGrille(g); }).observe(g,{childList:true}); });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',demarrer); else demarrer();
})();
