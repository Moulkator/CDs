/* Lecteur YouTube d'album, commun à toutes les pages.
   YTA.cache : { "groupe|album": {id, title, t, bad:[…]} | {none:1, t} } — mémorisé dans ce navigateur
   et, en mode propriétaire, publié dans data/mes-badges.json (clé "youtube") par la page. */
(function(){
  var KEY='youtube-key-v1', CACHE='youtube-playlists-v1';
  function ls(k,d){ try{ var v=localStorage.getItem(k); return v?JSON.parse(v):d; }catch(e){ return d; } }
  function save(){ try{ localStorage.setItem(CACHE, JSON.stringify(YTA.cache)); }catch(e){} }
  function norm(s){ return String(s==null?'':s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); }
  function key(g,a){ return norm(g)+'|'+norm(a).replace(/\b(deluxe|edition|bonus|remastered|remaster|digipak|version)\b/g,'').trim(); }
  function cleanTitle(a){ return String(a||'').replace(/\((?:[^)]*(?:si possible|deluxe|digipak|reissue|re-recorded|remaster|normal|edition|version|bonus)[^)]*)\)/ig,'').replace(/\s+/g,' ').trim(); }
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
    quotaOut: function(){ var q=ls('youtube-quota-out',0); return q && Date.now()<q; },
    _quotaHit: function(){ var d=new Date(); d.setUTCHours(7,5,0,0); if(d.getTime()<Date.now()) d.setUTCDate(d.getUTCDate()+1); localStorage.setItem('youtube-quota-out', JSON.stringify(d.getTime())); },
    api: function(path, cb){ var x=new XMLHttpRequest(); x.open('GET','https://www.googleapis.com/youtube/v3/'+path+'&key='+encodeURIComponent(YTA.getKey())); x.onload=function(){ var js; try{ js=JSON.parse(x.responseText); }catch(e){ cb(null,'Réponse YouTube illisible ('+x.status+').'); return; } if(js.error){ var reason=js.error.errors&&js.error.errors[0]&&js.error.errors[0].reason; if(reason==='quotaExceeded') YTA._quotaHit(); cb(null,'YouTube : '+(reason==='quotaExceeded'?'quota du jour épuisé (retour à 9h)':js.error.message)); return; } cb(js); }; x.onerror=function(){ cb(null,'YouTube injoignable.'); }; x.send(); },
    /* Chaîne « Groupe – Topic » et ses playlists d'albums : 1 recherche par groupe, puis 1 unité par page de 50 playlists */
    artistPlaylists: function(groupe, cb){
      var ak='@artist|'+norm(groupe), a=YTA.cache[ak];
      if(a && a.playlists && Date.now()-(a.t||0)<30*864e5){ cb(a); return; }
      if(a && a.none && Date.now()-(a.t||0)<7*864e5){ cb(null); return; }
      var ng=norm(groupe);
      YTA.api('search?part=snippet&type=channel&maxResults=5&q='+encodeURIComponent(groupe+' topic'), function(js,msg){
        if(!js){ cb(null,msg); return; }
        var items=js.items||[], hit=null;
        items.forEach(function(it){ var t=norm(it.snippet.channelTitle||it.snippet.title||''); if(!hit && (t===ng+' topic')) hit=it; });
        if(!hit) items.forEach(function(it){ var t=norm(it.snippet.channelTitle||it.snippet.title||''); if(!hit && /topic$/.test(t) && t.replace(/ topic$/,'')===ng) hit=it; });
        if(!hit){ YTA.cache[ak]={none:1,t:Date.now()}; save(); cb(null); return; }
        var channelId=hit.snippet.channelId||(hit.id&&hit.id.channelId), pls=[];
        function page(tok){ YTA.api('playlists?part=snippet&maxResults=50&channelId='+encodeURIComponent(channelId)+(tok?'&pageToken='+encodeURIComponent(tok):''), function(p2,msg2){ if(!p2){ cb(null,msg2); return; } (p2.items||[]).forEach(function(pl){ pls.push({id:pl.id,title:pl.snippet.title||''}); }); if(p2.nextPageToken && pls.length<200) page(p2.nextPageToken); else { YTA.cache[ak]={channelId:channelId,playlists:pls,t:Date.now()}; save(); YTA.persist&&YTA.persist(); cb(YTA.cache[ak]); } }); }
        page(null);
      });
    },
    find: function(groupe, album, cb, force){
      var k=key(groupe,album), c=YTA.cache[k]||{}, bad=c.bad||[];
      if(!force && c.id){ cb(c.id); return; }
      if(!force && c.none && Date.now()-c.t<7*864e5){ cb(null,'Aucune playlist trouvée pour cet album (revérifié dans quelques jours).'); return; }
      if(!YTA.getKey()){ cb(null,'Ajoute une clé YouTube (bouton « Clé YouTube » dans Rechercher) pour chercher la playlist.'); return; }
      if(YTA.quotaOut()){ cb(null,'YouTube : quota du jour épuisé (retour à 9h).'); return; }
      var albumQ=cleanTitle(album)||album, na0=norm(albumQ);
      // 1. playlists de la chaîne Topic du groupe (économe)
      YTA.artistPlaylists(groupe, function(a){
        if(a && a.playlists){ var m=null; a.playlists.forEach(function(pl){ if(m||bad.indexOf(pl.id)>=0) return; var t=norm(cleanTitle(pl.title)); if(t===na0) m=pl; }); if(!m) a.playlists.forEach(function(pl){ if(m||bad.indexOf(pl.id)>=0) return; var t=norm(cleanTitle(pl.title)); if(na0.length>6 && (t.indexOf(na0)===0 || na0.indexOf(t)===0)) m=pl; });
          if(m){ YTA.cache[k]={id:m.id,title:m.title,t:Date.now(),bad:bad,topic:true}; save(); YTA.persist&&YTA.persist(); cb(m.id); return; } }
        if(YTA.quotaOut()){ cb(null,'YouTube : quota du jour épuisé (retour à 9h).'); return; }
        YTA._findSearch(groupe, album, albumQ, k, bad, cb);
      });
    },
    _findSearch: function(groupe, album, albumQ, k, bad, cb){
      var x=new XMLHttpRequest(); x.open('GET','https://www.googleapis.com/youtube/v3/search?part=snippet&type=playlist&maxResults=10&q='+encodeURIComponent(groupe+' '+albumQ+' full album')+'&key='+encodeURIComponent(YTA.getKey()));
      x.onload=function(){ var js; try{ js=JSON.parse(x.responseText); }catch(e){ cb(null,'Réponse YouTube illisible ('+x.status+').'); return; }
        if(js.error){ var reason=js.error.errors&&js.error.errors[0]&&js.error.errors[0].reason; if(reason==='quotaExceeded') YTA._quotaHit(); cb(null,'YouTube : '+(reason==='quotaExceeded'?'quota du jour épuisé (retour à 9h)':js.error.message)); return; }
        try{
        var items=(js.items||[]).filter(function(it){ return bad.indexOf(it.id.playlistId)<0; }), ng=norm(groupe), na=norm(albumQ);
        function scoreOf(it){ var t=norm(it.snippet.title), ch=norm(it.snippet.channelTitle||''); var sc=0; if(t.indexOf(na)>=0) sc+=4; if(t.indexOf(ng)>=0||ch.indexOf(ng)>=0) sc+=2; if(/topic$/.test(ch)) sc+=2; if(/full album|album complet/.test(t)) sc+=1; if(/live|cover|reaction|karaoke|instrumental|tribute|mix|best of|playthrough/.test(t)&&!/live|instrumental/.test(na)) sc-=3; return sc; }
        var ranked=items.map(function(it){ return {it:it, sc:scoreOf(it)}; }).sort(function(a,b){ return b.sc-a.sc; });
        var best=ranked[0];
        }catch(e){ cb(null,'Résultat YouTube inattendu : '+e.message); return; }
        if(best && best.sc>=4){ YTA.cache[k]={id:best.it.id.playlistId,title:best.it.snippet.title,t:Date.now(),bad:bad}; save(); try{ YTA.persist&&YTA.persist(); }catch(e){} cb(best.it.id.playlistId); return; }
        // pas de playlist : une vidéo « album complet » ?
        var y=new XMLHttpRequest(); y.open('GET','https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&videoDuration=long&maxResults=10&q='+encodeURIComponent(groupe+' '+albumQ+' full album')+'&key='+encodeURIComponent(YTA.getKey()));
        y.onload=function(){ var j2, r2; try{ j2=JSON.parse(y.responseText); if(j2.error){ var rs=j2.error.errors&&j2.error.errors[0]&&j2.error.errors[0].reason; if(rs==='quotaExceeded') YTA._quotaHit(); cb(null,'YouTube : '+(rs==='quotaExceeded'?'quota du jour épuisé (retour à 9h)':j2.error.message)); return; } var vids=(j2.items||[]).filter(function(it){ return it.id&&it.id.videoId&&bad.indexOf(it.id.videoId)<0; });
          r2=vids.map(function(it){ return {it:it, sc:scoreOf(it)}; }).sort(function(a,b){ return b.sc-a.sc; })[0]; }catch(e){ cb(null,'Réponse YouTube illisible ('+y.status+').'); return; }
          if(r2 && r2.sc>=4){ YTA.cache[k]={id:r2.it.id.videoId,video:true,title:r2.it.snippet.title,t:Date.now(),bad:bad}; save(); try{ YTA.persist&&YTA.persist(); }catch(e){} cb(r2.it.id.videoId); }
          else { YTA.cache[k]={none:1,t:Date.now(),bad:bad}; save(); cb(null,'Ni playlist ni vidéo « album complet » trouvée pour cet album.'); }
        };
        y.onerror=function(){ cb(null,'YouTube injoignable.'); }; y.send();
      };
      x.onerror=function(){ cb(null,'YouTube injoignable.'); }; x.send();
    },
    isVideo: function(g,a){ var c=YTA.cache[key(g,a)]; return !!(c&&c.id&&c.video); },
    embedUrl: function(g,a){ var c=YTA.cache[key(g,a)]||{}; if(!c.id) return ''; return c.video ? 'https://www.youtube-nocookie.com/embed/'+encodeURIComponent(c.id)+'?autoplay=1&rel=0' : 'https://www.youtube-nocookie.com/embed/videoseries?list='+encodeURIComponent(c.id)+'&autoplay=1&rel=0'; },
    watchUrl: function(g,a){ var c=YTA.cache[key(g,a)]||{}; if(!c.id) return ''; return c.video ? 'https://www.youtube.com/watch?v='+encodeURIComponent(c.id) : 'https://www.youtube.com/playlist?list='+encodeURIComponent(c.id); },
    reject: function(groupe, album, cb){ var k=key(groupe,album), c=YTA.cache[k]||{}; var bad=(c.bad||[]).slice(); if(c.id && bad.indexOf(c.id)<0) bad.push(c.id); YTA.cache[k]={bad:bad,t:Date.now()}; save(); YTA.persist&&YTA.persist(); YTA.find(groupe, album, cb, true); },
    setManual: function(groupe, album, url){ var u=String(url||''); var k=key(groupe,album), bad=(YTA.cache[k]||{}).bad||[]; var m=u.match(/[?&]list=([A-Za-z0-9_-]+)/); if(m){ YTA.cache[k]={id:m[1],title:'(lien saisi à la main)',t:Date.now(),bad:bad}; save(); YTA.persist&&YTA.persist(); return m[1]; } var v=u.match(/[?&]v=([A-Za-z0-9_-]{6,})/)||u.match(/youtu\.be\/([A-Za-z0-9_-]{6,})/)||u.match(/\/embed\/([A-Za-z0-9_-]{6,})/); if(v){ YTA.cache[k]={id:v[1],video:true,title:'(vidéo saisie à la main)',t:Date.now(),bad:bad}; save(); YTA.persist&&YTA.persist(); return v[1]; } return null; },
    markup: function(groupe, album){ return '<div class="yt"><button type="button" class="pbtn ytbtn" data-act="yt">▶ YouTube'+(YTA.known(groupe,album)?(YTA.isVideo(groupe,album)?' (vidéo trouvée)':' (playlist trouvée)'):'')+'</button></div>'; },
    bind: function(el, groupe, album){
      var b=el.querySelector('[data-act=yt]'), wrap=el.querySelector('.coverwrap'); if(!b||!wrap) return;
      function close(){ if(wrap.getAttribute('data-cover')!=null) wrap.innerHTML=wrap.getAttribute('data-cover'); b.classList.remove('on'); b.textContent='▶ YouTube'+(YTA.known(groupe,album)?(YTA.isVideo(groupe,album)?' (vidéo trouvée)':' (playlist trouvée)'):''); var ex=el.querySelector('.ytextra'); if(ex) ex.remove(); }
      function open(id){
        if(wrap.getAttribute('data-cover')==null) wrap.setAttribute('data-cover', wrap.innerHTML);
        document.querySelectorAll('audio').forEach(function(o){ o.pause(); }); document.querySelectorAll('.ytbtn.on').forEach(function(o){ if(o!==b) o.click(); });
        wrap.innerHTML='<iframe src="'+YTA.embedUrl(groupe,album)+'" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen title="YouTube"></iframe>';
        b.classList.add('on'); b.textContent='⏹ Fermer YouTube';
        var old=el.querySelector('.ytextra'); if(old) old.remove();
        var ex=document.createElement('div'); ex.className='ytextra'; ex.innerHTML='<a class="ytmini ytopen" href="'+YTA.watchUrl(groupe,album)+'" target="_blank" rel="noopener" title="Ouvrir dans l\'application YouTube (lecture en arrière-plan avec Premium)">↗ Ouvrir dans YouTube</a><button type="button" class="ytmini" data-act="ytbad" title="Ce n\'est pas cet album : en chercher une autre">✗ Mauvaise playlist</button><button type="button" class="ytmini" data-act="ytlink" title="Coller le lien d\'une playlist YouTube">🔗 Autre lien</button>';
        b.parentNode.appendChild(ex);
        ex.querySelector('[data-act=ytbad]').addEventListener('click',function(e){ e.stopPropagation(); b.textContent='Recherche d\'une autre playlist…'; YTA.reject(groupe, album, function(id2,msg){ if(id2){ open(id2); YTA.toast('Autre playlist chargée'); } else { close(); YTA.toast(msg||'Aucune autre playlist trouvée'); } }); });
        ex.querySelector('[data-act=ytlink]').addEventListener('click',function(e){ e.stopPropagation(); askLink(); });
      }
      function askLink(){ var u=prompt('Colle le lien YouTube de cet album : une playlist (adresse avec list=…) ou une vidéo « album complet » (watch?v=…) :',''); if(!u) return; var id3=YTA.setManual(groupe, album, u); if(id3){ open(id3); YTA.toast('Lien enregistré'); } else YTA.toast('Lien non reconnu (il faut list=… ou v=…)'); }
      b.addEventListener('click',function(e){ e.stopPropagation(); if(b.classList.contains('on')){ close(); return; }
        b.disabled=true; b.textContent='Recherche…';
        YTA.find(groupe, album, function(id,msg){ b.disabled=false; if(!id){ b.textContent='▶ YouTube'; YTA.toast(msg||'Introuvable'); var old=el.querySelector('.ytextra'); if(old) old.remove(); var ex=document.createElement('div'); ex.className='ytextra'; ex.innerHTML='<button type="button" class="ytmini" data-act="ytlink">🔗 Coller un lien YouTube (playlist ou vidéo)</button><button type="button" class="ytmini" data-act="ytretry">↻ Rechercher à nouveau</button>'; b.parentNode.appendChild(ex); ex.querySelector('[data-act=ytlink]').addEventListener('click',function(e2){ e2.stopPropagation(); askLink(); }); ex.querySelector('[data-act=ytretry]').addEventListener('click',function(e2){ e2.stopPropagation(); ex.remove(); b.textContent='Recherche…'; b.disabled=true; YTA.find(groupe, album, function(id5,msg5){ b.disabled=false; if(id5) open(id5); else { b.textContent='▶ YouTube'; YTA.toast(msg5||'Toujours rien'); b.parentNode.appendChild(ex); } }, true); }); return; } open(id); });
      });
    }
  };
  window.YTA=YTA;
})();
