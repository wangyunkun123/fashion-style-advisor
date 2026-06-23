(function(){
  var hero=document.querySelector('#page-recommend');
  if(!hero)return;
  var isNew=hero.getAttribute('data-new-user')==='true';
  if(!isNew)return;
  // 清理其他用户的默认内容（穿搭卡片、历史推荐、日推未生成警告等）
  var oldCards=hero.querySelectorAll('.fav-card, .rec-card, .h-char-img-lg, .history-block, .other-recs, .daily-warning');
  oldCards.forEach(function(c){c.style.display='none'});
  // Hero 图片区：替换为引导语
  var heroImg=hero.querySelector('.h-char-img-lg');
  if(!heroImg)heroImg=hero.querySelector('.photo-slot');
  if(heroImg){
    heroImg.style.cssText='';
    heroImg.className='';
    heroImg.innerHTML='<div style="text-align:center;padding:48px 24px 32px"><div style="font-size:40px;margin-bottom:8px">👋</div><h2 style="font-size:16px;font-weight:700;margin-bottom:4px;color:var(--text)">AI 已就绪，开始你的第一套穿搭</h2><p style="font-size:12px;color:var(--sub);line-height:1.5;margin:0">在下方输入框描述需求<br>比如「今天要去约会」「上班通勤」</p></div>';
  }
  // 其他推荐：替换为 3 张正常风格卡片
  fetch('/api/explore/trends?user='+encodeURIComponent(USER_ID)).then(function(r){return r.json()}).then(function(d){
    var styles=(d.styles||[]).filter(function(s){return s.trend_category==='popular_trend'}).slice(0,3);
    if(!styles.length) styles=(d.styles||[]).slice(0,3);
    if(!styles.length)return;
    // 找到其他推荐区域
    var recSection=hero.querySelector('.other-recs');
    if(!recSection){
      // 创建推荐区域
      recSection=document.createElement('div');
      recSection.className='other-recs';
      // 插入在输入框之前
      var pageBottom=hero.querySelector('.page-bottom');
      if(pageBottom)hero.insertBefore(recSection,pageBottom);
      else hero.appendChild(recSection);
    }
    recSection.style.display='block';
    recSection.innerHTML='<div style="font-size:13px;font-weight:600;color:var(--sub);padding:0 16px;margin-bottom:10px">💡 其他推荐</div><div style="padding:0 12px;display:flex;gap:10px;overflow-x:auto">'+
      styles.map(function(s){
        var img=s.image||'';
        var imgHtml=img?'<img src="'+img+'" style="width:100%;height:100px;object-fit:cover;border-radius:8px 8px 0 0;background:#f0f4f8">':'<div style="width:100%;height:100px;border-radius:8px 8px 0 0;background:#f0f4f8;display:flex;align-items:center;justify-content:center;font-size:28px">'+s.name_zh.charAt(0)+'</div>';
        return '<div class="rec-card" onclick="document.getElementById(\'today-input\').value=\''+s.name_zh+'\';document.getElementById(\'today-input\').focus()" style="flex:0 0 140px;background:var(--white);border:1px solid var(--border);border-radius:10px;overflow:hidden;cursor:pointer"><div>'+imgHtml+'</div><div style="padding:8px 10px"><div style="font-size:13px;font-weight:600;color:var(--text)">'+s.name_zh+'</div><div style="font-size:10px;color:var(--muted);margin-top:2px">点击生成 »</div></div></div>';
      }).join('')+
    '</div>';
  }).catch(function(){});
})();
