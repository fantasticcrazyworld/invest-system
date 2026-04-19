function loadFins(){
  var code=(document.getElementById('fins-code-input')||{}).value||'';
  code=code.trim();
  if(!code){alert('銘柄コードを入力してください');return;}
  var found=allData.find(function(x){return x.code===code;});
  var fd=window._finsData||{};
  var records=fd[code];
  if(!records||!records.length){
    document.getElementById('fins-error').style.display='block';
    document.getElementById('fins-error').textContent='業績データがありません: '+code+' （年初来高値圏/監視/PF銘柄のみ対応。Claude Desktopで export_fins_data(extra_codes=\"'+code+'\") を実行すると追加できます）';
    return;
  }
  document.getElementById('fins-error').style.display='none';
  document.getElementById('fins-stock-name').textContent=code+' '+(found?found.name:'')+' | 業績推移';

  // Separate FY and quarterly records (deduplicate: keep latest record per fy)
  var fyRecords=dedupFY(records.filter(function(r){return r.period==='FY';}));
  var qRecords=records.filter(function(r){return r.period!=='FY';}).sort(function(a,b){return(a.fy+a.period).localeCompare(b.fy+b.period);});

  // Get latest FY record for forecasts
  var latestQ=records.sort(function(a,b){return b.date.localeCompare(a.date);})[0]||{};

  var h='';

  // --- Annual (FY) Table ---
  h+='<div class="fins-section"><div class="fins-section-title">通期業績（過去5年）</div>';
  h+='<div class="table-wrap"><table class="fins-table"><thead><tr><th>決算期</th><th>売上高</th><th>営業利益</th><th>純利益</th><th>EPS</th><th>BPS</th><th>配当</th><th>自己資本比率</th></tr></thead><tbody>';
  var last5=fyRecords.slice(-5);
  for(var i=0;i<last5.length;i++){
    var r=last5[i];var prev=i>0?last5[i-1]:null;
    h+='<tr>';
    h+='<td>'+r.fy+'</td>';
    h+='<td class="'+growthClass(r.sales,prev?prev.sales:null)+'">'+fmtYen(r.sales)+'</td>';
    h+='<td class="'+growthClass(r.op,prev?prev.op:null)+'">'+fmtYen(r.op)+'</td>';
    h+='<td class="'+growthClass(r.np,prev?prev.np:null)+'">'+fmtYen(r.np)+'</td>';
    h+='<td class="'+growthClass(r.eps,prev?prev.eps:null)+'">'+fmtNum(r.eps,1)+'</td>';
    h+='<td>'+fmtNum(r.bps,0)+'</td>';
    h+='<td>'+(r.div!=null?fmtNum(r.div,0):'-')+'</td>';
    h+='<td>'+(r.eq_ratio!=null?(r.eq_ratio*100).toFixed(1)+'%':'-')+'</td>';
    h+='</tr>';
  }
  // Forecast row
  if(latestQ.f_sales||latestQ.f_eps){
    h+='<tr class="forecast"><td>'+latestQ.fy+'予</td>';
    h+='<td>'+fmtYen(latestQ.f_sales)+'</td>';
    h+='<td>'+fmtYen(latestQ.f_op)+'</td>';
    h+='<td>'+fmtYen(latestQ.f_np)+'</td>';
    h+='<td>'+fmtNum(latestQ.f_eps,1)+'</td>';
    h+='<td>-</td><td>-</td><td>-</td></tr>';
  }
  if(latestQ.nf_sales||latestQ.nf_eps){
    var nfFy=latestQ.fy?((parseInt(latestQ.fy)+1)+latestQ.fy.slice(4)):'次期';
    h+='<tr class="forecast"><td>'+nfFy+'予</td>';
    h+='<td>'+fmtYen(latestQ.nf_sales)+'</td>';
    h+='<td>'+fmtYen(latestQ.nf_op)+'</td>';
    h+='<td>'+fmtYen(latestQ.nf_np)+'</td>';
    h+='<td>'+fmtNum(latestQ.nf_eps,1)+'</td>';
    h+='<td>-</td><td>-</td><td>-</td></tr>';
  }
  h+='</tbody></table></div></div>';

  // --- EPS bar chart (simple HTML bars) ---
  var allEps=last5.map(function(r){return{label:r.fy.slice(2),value:r.eps||0};});
  if(latestQ.f_eps)allEps.push({label:'予',value:latestQ.f_eps});
  var maxEps=Math.max.apply(null,allEps.map(function(e){return Math.abs(e.value);}));
  if(maxEps>0){
    h+='<div class="fins-section"><div class="fins-section-title">EPS推移</div>';
    h+='<div style="display:flex;align-items:flex-end;gap:8px;height:120px;padding:0 8px">';
    allEps.forEach(function(e){
      var pct=Math.abs(e.value)/maxEps*100;
      var color=e.value>=0?'#3fb950':'#f85149';
      if(e.label==='予')color='#f0b429';
      h+='<div style="flex:1;text-align:center"><div style="background:'+color+';height:'+pct+'px;border-radius:3px 3px 0 0;min-height:2px"></div><div style="font-size:10px;color:#8b949e;margin-top:4px">'+e.label+'</div><div style="font-size:10px;color:#e6edf3">'+fmtNum(e.value,0)+'</div></div>';
    });
    h+='</div></div>';
  }

  // --- Quarterly Table (last 2 FY) ---
  var recentFYs=fyRecords.slice(-2).map(function(r){return r.fy;});
  var recentQ=qRecords.filter(function(r){return recentFYs.indexOf(r.fy)>=0;});
  if(recentQ.length>0){
    h+='<div class="fins-section"><div class="fins-section-title">四半期業績</div>';
    h+='<div class="table-wrap"><table class="fins-table"><thead><tr><th>期/Q</th><th>売上高</th><th>営業利益</th><th>純利益</th><th>EPS</th></tr></thead><tbody>';
    recentQ.forEach(function(r){
      var label=r.fy.slice(2)+' '+r.period;
      h+='<tr><td>'+label+'</td>';
      h+='<td>'+fmtYen(r.sales)+'</td>';
      h+='<td>'+fmtYen(r.op)+'</td>';
      h+='<td>'+fmtYen(r.np)+'</td>';
      h+='<td>'+fmtNum(r.eps,1)+'</td>';
      h+='</tr>';
    });
    h+='</tbody></table></div></div>';
  }

  // --- Growth Summary ---
  if(last5.length>=2){
    var first=last5[0],last=last5[last5.length-1];
    h+='<div class="fins-section"><div class="fins-section-title">成長性サマリー</div>';
    h+='<div class="detail-grid">';
    var items=[
      {label:'売上CAGR',calc:function(){if(!first.sales||!last.sales||first.sales<=0)return null;return(Math.pow(last.sales/first.sales,1/(last5.length-1))-1)*100;}},
      {label:'EPS CAGR',calc:function(){if(!first.eps||!last.eps||first.eps<=0)return null;return(Math.pow(last.eps/first.eps,1/(last5.length-1))-1)*100;}},
      {label:'営業利益率',calc:function(){if(!last.sales||!last.op)return null;return(last.op/last.sales)*100;}},
      {label:'ROE概算',calc:function(){if(!last.eps||!last.bps||last.bps<=0)return null;return(last.eps/last.bps)*100;}},
    ];
    items.forEach(function(item){
      var v=item.calc();
      var cls=v==null?'muted':v>0?'green':'red';
      h+='<div class="detail-card"><div class="detail-card-label">'+item.label+'</div><div class="detail-card-value '+cls+'">'+(v!=null?v.toFixed(1)+'%':'-')+'</div></div>';
    });
    h+='</div></div>';
  }

  document.getElementById('fins-content').innerHTML=h;
  initSim(code,records);
}
function openFins(code){
  showPage('fins',document.querySelectorAll('.nav-btn')[2]);
  document.getElementById('fins-code-input').value=code;
  loadFins();
}

// Watchlist add/remove (localStorage-based)
