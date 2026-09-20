/* Lecteur YouTube d'album, commun à toutes les pages.
   YTA.cache : { "groupe|album": {id, title, t, bad:[…]} | {none:1, t} } — mémorisé dans ce navigateur
   et, en mode propriétaire, publié dans data/mes-badges.json (clé "youtube") par la page. */
(function(){
  var KEY='youtube-key-v1', CACHE='youtube-playlists-v1';
  function ls(k,d){ try{ var v=localStorage.getItem(k); return v?JSON.parse(v):d; }catch(e){ return d; } }
  function save(){ try{ localStorage.setItem(CACHE, JSON.stringify(YTA.cache)); }catch(e){} }
  function norm(s){ return String(s==null?'':s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); }
  function key(g,a){ return norm(g)+'|'+norm(a).replace(/\b(deluxe|edition|bonus|remastered|remaster|digipak|version)\b/g,'').trim(); }
  function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  var YTA={
    cache: ls(CACHE,{}) || {},
    toast: function(m){ try{ console.log(m); }catch(e){} },
    persist: null,                      // fonction fournie par la page pour publier le cache
    getKey: function(){ return ls(KEY,''); },
    setKey: function(k){ if(k){ localStorage.setItem(KEY, JSON.stringify(k)); } else { localStorage.removeItem(KEY); } },
    norm: norm, key: key,
    merge: function(map){ var k; for(k in (map||{})){ var m=map[k], c=YTA.cache[k]; if(!c || (m.id && !c.id) || (m.t||0)>(c.t||0)) YTA.cache[k]=m; } save(); },
    known: function(g,a){ var c=YTA.cache[key(g,a)]; return !!(c&&c.id); },
    find: function(groupe, album, cb, force){
      var k=key(groupe,album), c=YTA.cache[k]||{}, bad=c.bad||[];
      if(!force && c.id){ cb(c.id); return; }
      if(!force && c.none && Date.now()-c.t<7*864e5){ cb(null,'Aucune playlist trouvée pour cet album (revérifié dans quelques jours).'); return; }
      if(!YTA.getKey()){ cb(null,'Ajoute une clé YouTube (bouton « Clé YouTube » dans Rechercher) pour chercher la playlist.'); return; }
      var x=new XMLHttpRequest(); x.open('GET','https://www.googleapis.com/youtube/v3/search?part=snippet&type=playlist&maxResults=10&q='+encodeURIComponent(groupe+' '+album+' full album')+'&key='+encodeURIComponent(YTA.getKey()));
      x.onload=function(){ try{ var js=JSON.parse(x.responseText);
        if(js.error){ var reason=js.error.errors&&js.error.errors[0]&&js.error.errors[0].reason; cb(null,'YouTube : '+(reason==='quotaExceeded'?'quota du jour épuisé, réessaie demain':js.error.message)); return; }
        var items=(js.items||[]).filter(function(it){ return bad.indexOf(it.id.playlistId)<0; }), ng=norm(groupe), na=norm(album);
        function scoreOf(it){ var t=norm(it.snippet.title), ch=norm(it.snippet.channelTitle||''); var sc=0; if(t.indexOf(na)>=0) sc+=4; if(t.indexOf(ng)>=0||ch.indexOf(ng)>=0) sc+=2; if(/topic$/.test(ch)) sc+=2; if(/full album|album complet/.test(t)) sc+=1; if(/live|cover|reaction|karaoke|instrumental|tribute|mix|best of|playthrough/.test(t)&&!/live|instrumental/.test(na)) sc-=3; return sc; }
        var ranked=items.map(function(it){ return {it:it, sc:scoreOf(it)}; }).sort(function(a,b){ return b.sc-a.sc; });
        var best=ranked[0];
        if(best && best.sc>=4){ YTA.cache[k]={id:best.it.id.playlistId,title:best.it.snippet.title,t:Date.now(),bad:bad}; save(); YTA.persist&&YTA.persist(); cb(best.it.id.playlistId); }
        else { YTA.cache[k]={none:1,t:Date.now(),bad:bad}; save(); cb(null,'Aucune playlist convaincante trouvée pour cet album.'); }
      }catch(e){ cb(null,'Réponse YouTube illisible.'); } };
      x.onerror=function(){ cb(null,'YouTube injoignable.'); }; x.send();
    },
    reject: function(groupe, album, cb){ var k=key(groupe,album), c=YTA.cache[k]||{}; var bad=(c.bad||[]).slice(); if(c.id && bad.indexOf(c.id)<0) bad.push(c.id); YTA.cache[k]={bad:bad,t:Date.now()}; save(); YTA.persist&&YTA.persist(); YTA.find(groupe, album, cb, true); },
    setManual: function(groupe, album, url){ var m=String(url||'').match(/[?&]list=([A-Za-z0-9_-]+)/); if(!m) return null; var k=key(groupe,album); YTA.cache[k]={id:m[1],title:'(lien saisi à la main)',t:Date.now(),bad:(YTA.cache[k]||{}).bad||[]}; save(); YTA.persist&&YTA.persist(); return m[1]; },
    markup: function(groupe, album){ return '<div class="yt"><button type="button" class="pbtn ytbtn" data-act="yt">▶ YouTube'+(YTA.known(groupe,album)?' (playlist trouvée)':'')+'</button></div>'; },
    bind: function(el, groupe, album){
      var b=el.querySelector('[data-act=yt]'), wrap=el.querySelector('.coverwrap'); if(!b||!wrap) return;
      function close(){ if(wrap.getAttribute('data-cover')!=null) wrap.innerHTML=wrap.getAttribute('data-cover'); b.classList.remove('on'); b.textContent='▶ YouTube'+(YTA.known(groupe,album)?' (playlist trouvée)':''); var ex=el.querySelector('.ytextra'); if(ex) ex.remove(); }
      function open(id){
        if(wrap.getAttribute('data-cover')==null) wrap.setAttribute('data-cover', wrap.innerHTML);
        document.querySelectorAll('audio').forEach(function(o){ o.pause(); }); document.querySelectorAll('.ytbtn.on').forEach(function(o){ if(o!==b) o.click(); });
        wrap.innerHTML='<iframe src="https://www.youtube-nocookie.com/embed/videoseries?list='+encodeURIComponent(id)+'&autoplay=1&rel=0" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen title="YouTube"></iframe>';
        b.classList.add('on'); b.textContent='⏹ Fermer YouTube';
        var old=el.querySelector('.ytextra'); if(old) old.remove();
        var ex=document.createElement('div'); ex.className='ytextra'; ex.innerHTML='<button type="button" class="ytmini" data-act="ytbad" title="Ce n\'est pas cet album : en chercher une autre">✗ Mauvaise playlist</button><button type="button" class="ytmini" data-act="ytlink" title="Coller le lien d\'une playlist YouTube">🔗 Autre lien</button>';
        b.parentNode.appendChild(ex);
        ex.querySelector('[data-act=ytbad]').addEventListener('click',function(e){ e.stopPropagation(); b.textContent='Recherche d\'une autre playlist…'; YTA.reject(groupe, album, function(id2,msg){ if(id2){ open(id2); YTA.toast('Autre playlist chargée'); } else { close(); YTA.toast(msg||'Aucune autre playlist trouvée'); } }); });
        ex.querySelector('[data-act=ytlink]').addEventListener('click',function(e){ e.stopPropagation(); var u=prompt('Colle le lien de la playlist YouTube de cet album (adresse contenant list=…) :',''); if(!u) return; var id3=YTA.setManual(groupe, album, u); if(id3){ open(id3); YTA.toast('Playlist enregistrée'); } else YTA.toast('Lien sans identifiant de playlist (list=…)'); });
      }
      b.addEventListener('click',function(e){ e.stopPropagation(); if(b.classList.contains('on')){ close(); return; }
        b.disabled=true; b.textContent='Recherche de la playlist…';
        YTA.find(groupe, album, function(id,msg){ b.disabled=false; if(!id){ b.textContent='▶ YouTube'; YTA.toast(msg||'Playlist introuvable'); if(!YTA.getKey()){ var u=prompt('Pas de clé YouTube. Tu peux coller directement le lien de la playlist de cet album (adresse avec list=…) :',''); if(u){ var id4=YTA.setManual(groupe, album, u); if(id4) open(id4); } } return; } open(id); });
      });
    }
  };
  window.YTA=YTA;
})();
