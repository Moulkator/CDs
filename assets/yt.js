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
  // pays d'écoute : France d'abord ; Jersey = pays du VPN. On préfère les versions lisibles partout,
  // à défaut une version lisible en France.
  var PAYS=['FR','JE'], MIN_ALBUM=12*60;
  function dureeSec(iso){ var m=/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(iso||''); return m?((+m[1]||0)*3600+(+m[2]||0)*60+(+m[3]||0)):0; }
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
    /* ---- Vérification : public, intégrable, pas bloqué en France, assez long (vidéo) / assez de morceaux lisibles (playlist) ---- */
    _jouable: function(v, pays){ var st=v.status||{}, rr=(v.contentDetails||{}).regionRestriction||{}; pays=pays||[PAYS[0]];
      if(st.privacyStatus && st.privacyStatus!=='public' && st.privacyStatus!=='unlisted') return false;
      if(st.embeddable===false) return false; if(st.uploadStatus && st.uploadStatus!=='processed') return false;
      return pays.every(function(p){ return !(rr.blocked && rr.blocked.indexOf(p)>=0) && !(rr.allowed && rr.allowed.indexOf(p)<0); }); },
    _videos: function(ids, cb){ if(!ids.length){ cb({}); return; } YTA.api('videos?part=status,contentDetails,snippet&maxResults=50&id='+ids.slice(0,50).join(','), function(js){ var m={}; ((js&&js.items)||[]).forEach(function(v){ m[v.id]=v; }); cb(m, !js); }); },
    _validerPlaylist: function(id, cb){ YTA.api('playlistItems?part=contentDetails&maxResults=50&playlistId='+encodeURIComponent(id), function(js){
        if(!js){ cb(false); return; } var ids=(js.items||[]).map(function(it){ return it.contentDetails&&it.contentDetails.videoId; }).filter(Boolean);
        if(ids.length<2){ cb(false); return; }
        YTA._videos(ids, function(m, err){ if(err){ cb(true, true); return; }
          function taux(pays){ var ok=ids.filter(function(x){ return m[x] && YTA._jouable(m[x], pays); }).length; return ok>=2 && ok/ids.length>=0.6; }
          cb(taux([PAYS[0]]), taux(PAYS)); }); }); },
    _valider: function(c, cb){ if(!c||!c.id){ cb(false); return; }
      if(c.video){ YTA._videos([c.id], function(m, err){ if(err){ cb(true, true); return; } var v=m[c.id], ok=!!v && dureeSec(v.contentDetails&&v.contentDetails.duration)>=MIN_ALBUM; cb(ok && YTA._jouable(v), ok && YTA._jouable(v, PAYS)); }); }
      else YTA._validerPlaylist(c.id, cb); },
    _accepter: function(k, cand, bad, rest, cb){ YTA.cache[k]={id:cand.id, video:!!cand.video, title:cand.title||'', t:Date.now(), bad:bad, v:3, partout:cand.partout!==false, cands:(rest||[]).filter(function(x){ return x.id!==cand.id && bad.indexOf(x.id)<0; }).slice(0,6), topic:!!cand.topic};
      save(); try{ YTA.persist&&YTA.persist(); }catch(e){} cb(cand.id); },
    find: function(groupe, album, cb, force){
      var k=key(groupe,album), c=YTA.cache[k]||{}, bad=(c.bad||[]).slice();
      if(!force && c.id){
        if(c.v===3 || !YTA.getKey() || YTA.quotaOut()){ cb(c.id); return; }
        // trouvaille d'avant la vérification : on la contrôle (2-3 unités de quota) avant de la lire
        YTA._valider(c, function(ok, partout){ if(ok){ var cc=YTA.cache[k]; if(cc&&cc.id===c.id){ cc.v=3; cc.partout=!!partout; save(); try{ YTA.persist&&YTA.persist(); }catch(e){} } cb(c.id); return; }
          if(bad.indexOf(c.id)<0) bad.push(c.id); YTA.cache[k]={bad:bad,t:Date.now(),cands:c.cands||[]}; save(); YTA.find(groupe, album, cb, true); });
        return; }
      if(!force && c.none && Date.now()-c.t<7*864e5){ cb(null,'Ni vidéo ni playlist lisible trouvée pour cet album (revérifié dans quelques jours).'); return; }
      // candidats déjà vérifiés lors de la dernière recherche : on passe au suivant sans nouvelle recherche
      var cands=(c.cands||[]).filter(function(x){ return bad.indexOf(x.id)<0; });
      if(force && cands.length){ YTA._accepter(k, cands[0], bad, cands.slice(1), cb); return; }
      if(!YTA.getKey()){ cb(null,'Ajoute une clé YouTube (bouton « Clé YouTube » dans Rechercher) pour chercher l\'album.'); return; }
      if(YTA.quotaOut()){ cb(null,'YouTube : quota du jour épuisé (retour à 9h).'); return; }
      var albumQ=cleanTitle(album)||album, na0=norm(albumQ);
      // 1. playlist officielle de la chaîne « Groupe – Topic » (économe), vérifiée
      YTA.artistPlaylists(groupe, function(a){
        var m=null;
        if(a && a.playlists){ a.playlists.forEach(function(pl){ if(m||bad.indexOf(pl.id)>=0) return; if(norm(cleanTitle(pl.title))===na0) m=pl; });
          if(!m) a.playlists.forEach(function(pl){ if(m||bad.indexOf(pl.id)>=0) return; var t=norm(cleanTitle(pl.title)); if(na0.length>6 && (t.indexOf(na0)===0 || na0.indexOf(t)===0)) m=pl; }); }
        if(!m){ YTA._findSearch(groupe, album, albumQ, k, bad, cb); return; }
        YTA._validerPlaylist(m.id, function(ok, partout){ if(ok && partout){ YTA._accepter(k, {id:m.id,title:m.title,topic:true,partout:true}, bad, [], cb); return; }
          if(ok){ YTA._findSearch(groupe, album, albumQ, k, bad, cb, {id:m.id,title:m.title,topic:true,partout:false,sc:9}); return; }   // lisible en France seulement : on cherche mieux, on la garde en réserve
          bad.push(m.id); YTA._findSearch(groupe, album, albumQ, k, bad, cb); });
      });
    },
    _findSearch: function(groupe, album, albumQ, k, bad, cb, reserve){
      if(YTA.quotaOut()){ if(reserve){ YTA._accepter(k, reserve, bad, [], cb); return; } cb(null,'YouTube : quota du jour épuisé (retour à 9h).'); return; }
      var ng=norm(groupe), na=norm(albumQ);
      function ordre(a,b){ return ((b.partout?1:0)-(a.partout?1:0)) || (b.sc-a.sc); }   // lisible partout d'abord, puis meilleur titre
      function scoreOf(title, chan){ var t=norm(title), ch=norm(chan||''); var sc=0;
        // le nom de l'album doit figurer dans le titre (en entier, ou ses 70 premiers % pour un titre long)
        if(t.indexOf(na)>=0) sc+=4; else if(na.length>12 && t.indexOf(na.slice(0,Math.floor(na.length*0.7)))>=0) sc+=3; else return -99; if(t.indexOf(ng)>=0||ch.indexOf(ng)>=0) sc+=2; if(/topic$/.test(ch)) sc+=2; if(/full album|album complet|full ep/.test(t)) sc+=1; if(/live|cover|reaction|karaoke|instrumental|tribute|mix|best of|playthrough|lesson|tutorial|review|8 ?bit|lyrics? video/.test(t)&&!/live|instrumental/.test(na)) sc-=3; return sc; }
      // 2. une vidéo « album complet » (souvent la plus fiable), vérifiée
      YTA.api('search?part=snippet&type=video&maxResults=15&q='+encodeURIComponent(groupe+' '+albumQ+' full album'), function(js,msg){
        if(!js){ if(reserve){ YTA._accepter(k, reserve, bad, [], cb); return; } cb(null,msg); return; }
        var ids=(js.items||[]).map(function(it){ return it.id&&it.id.videoId; }).filter(function(x){ return x && bad.indexOf(x)<0; });
        YTA._videos(ids, function(mv){
          var vids=ids.map(function(id){ var v=mv[id]; if(!v || !YTA._jouable(v)) return null; var d=dureeSec(v.contentDetails&&v.contentDetails.duration); if(d<MIN_ALBUM) return null;
              return {id:id, video:true, title:v.snippet.title, partout:YTA._jouable(v, PAYS), sc:scoreOf(v.snippet.title, v.snippet.channelTitle)+(d>=25*60?1:0)}; })
            .filter(function(x){ return x && x.sc>=4; }).sort(ordre);
          if(vids.length && vids[0].sc>=6 && vids[0].partout){ YTA._accepter(k, vids[0], bad, vids.slice(1).concat(reserve?[reserve]:[]), cb); return; }   // groupe + album dans le titre, lisible partout : suffisant
          // 3. sinon des playlists, vérifiées une par une (les 4 meilleures)
          YTA.api('search?part=snippet&type=playlist&maxResults=10&q='+encodeURIComponent(groupe+' '+albumQ+' full album'), function(j2){
            var pls=((j2&&j2.items)||[]).map(function(it){ return {id:it.id.playlistId, title:it.snippet.title, sc:scoreOf(it.snippet.title, it.snippet.channelTitle)}; })
              .filter(function(x){ return x.id && x.sc>=4 && bad.indexOf(x.id)<0; }).sort(function(a,b){ return b.sc-a.sc; }).slice(0,4);
            var bons=[], i=0;
            (function suivant(){ if(i>=pls.length){ fin(); return; } var pl=pls[i++]; YTA._validerPlaylist(pl.id, function(ok, partout){ if(ok){ pl.partout=!!partout; bons.push(pl); } else bad.push(pl.id); suivant(); }); })();
            function fin(){ var tous=bons.concat(vids).concat(reserve?[reserve]:[]).sort(ordre);
              if(tous.length){ YTA._accepter(k, tous[0], bad, tous.slice(1), cb); return; }
              YTA.cache[k]={none:1,t:Date.now(),bad:bad}; save(); cb(null,'Ni vidéo « album complet » ni playlist lisible trouvée pour cet album.'); }
          });
        });
      });
    },
    isVideo: function(g,a){ var c=YTA.cache[key(g,a)]; return !!(c&&c.id&&c.video); },
    embedUrl: function(g,a){ var c=YTA.cache[key(g,a)]||{}; if(!c.id) return ''; return c.video ? 'https://www.youtube-nocookie.com/embed/'+encodeURIComponent(c.id)+'?autoplay=1&rel=0' : 'https://www.youtube-nocookie.com/embed/videoseries?list='+encodeURIComponent(c.id)+'&autoplay=1&rel=0'; },
    watchUrl: function(g,a){ var c=YTA.cache[key(g,a)]||{}; if(!c.id) return ''; return c.video ? 'https://www.youtube.com/watch?v='+encodeURIComponent(c.id) : 'https://www.youtube.com/playlist?list='+encodeURIComponent(c.id); },
    // « Mauvaise playlist » : l'actuelle est écartée ; on passe au candidat vérifié suivant, sinon nouvelle recherche
    reject: function(groupe, album, cb){ var k=key(groupe,album), c=YTA.cache[k]||{}; var bad=(c.bad||[]).slice(); if(c.id && bad.indexOf(c.id)<0) bad.push(c.id); YTA.cache[k]={bad:bad,t:Date.now(),cands:c.cands||[]}; save(); YTA.persist&&YTA.persist(); YTA.find(groupe, album, cb, true); },
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
        var ex=document.createElement('div'); ex.className='ytextra'; ex.innerHTML='<a class="ytmini ytopen" href="'+YTA.watchUrl(groupe,album)+'" target="_blank" rel="noopener" title="Ouvrir dans l\'application YouTube (lecture en arrière-plan avec Premium)">↗ Ouvrir dans YouTube</a><button type="button" class="ytmini" data-act="ytbad" title="Ce n\'est pas cet album : en chercher une autre">✗ Mauvaise version</button><button type="button" class="ytmini" data-act="ytlink" title="Coller le lien d\'une playlist YouTube">🔗 Autre lien</button>';
        b.parentNode.appendChild(ex);
        ex.querySelector('[data-act=ytbad]').addEventListener('click',function(e){ e.stopPropagation(); b.textContent='Recherche d\'une autre version…'; YTA.reject(groupe, album, function(id2,msg){ if(id2){ open(id2); YTA.toast('Autre playlist chargée'); } else { close(); YTA.toast(msg||'Aucune autre playlist trouvée'); } }); });
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
